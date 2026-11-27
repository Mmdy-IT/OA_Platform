import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  CodeOutlined,
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  FileProtectOutlined,
  InfoCircleOutlined,
  PlusOutlined,
  SaveOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import {
  Alert,
  AutoComplete,
  Button,
  Collapse,
  Drawer,
  Input,
  Result,
  Select,
  Skeleton,
  Switch,
  Tag,
  message,
} from "antd";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { Editor } from "@tiptap/react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { ContractPaper } from "../components/ContractPaper";
import { PageHeader } from "../components/PageHeader";
import { RichTextEditor } from "../components/RichTextEditor";
import {
  CONTRACT_NUMBER_PLACEHOLDER,
  FINAL_PAYMENT_PLACEHOLDER,
  FIELD_KEY_RE,
  PREPAYMENT_PLACEHOLDER,
  extractPlaceholderKeys,
  hasRichContent,
  htmlToPlainText,
  isAutoPlaceholderKey,
  isSystemPlaceholderKey,
} from "../richtext";
import {
  AUTO_FILL_OPTIONS,
  ensureSystemPartyFields,
  isSystemPartyField,
  normalizeAutoFill,
  resolveAutoFill,
} from "../party";
import {
  ensureSystemAmountFields,
  isSystemAmountField,
} from "../money";
import type {
  TemplateField,
  TemplateFieldType,
  TemplateImportDraft,
  TemplatePayload,
} from "../types";
import { FIELD_TYPE_OPTIONS, fieldTypeLabel } from "../utils";

const DEFAULT_CATEGORIES = [
  "采购类",
  "服务类",
  "保密类",
  "劳动人事",
  "通用",
  "通用类",
];

function isSystemTemplateField(field: TemplateField): boolean {
  return isSystemPartyField(field) || isSystemAmountField(field);
}

function ensureTemplateSystemFields(fields: TemplateField[]): TemplateField[] {
  return ensureSystemAmountFields(ensureSystemPartyFields(fields));
}

function sanitizeFieldKey(value: string): string {
  const cleaned = value
    .trim()
    .replace(/\s+/g, "")
    .replace(/[^A-Za-z0-9_\u3400-\u4dbf\u4e00-\u9fff]/g, "")
    .slice(0, 40);
  if (!cleaned) return "";
  return /^[A-Za-z_\u3400-\u4dbf\u4e00-\u9fff]/.test(cleaned) ? cleaned : `字段${cleaned}`.slice(0, 40);
}

const SKELETON_FIELDS: TemplateField[] = [
  { key: "甲方", label: "甲方名称", type: "text", required: true, hint: "从主体库选择甲方后，其余甲方信息会自动带出。", placeholder: "", options: [], auto_fill: "party_a_name" },
  { key: "乙方", label: "乙方名称", type: "text", required: true, hint: "从主体库选择乙方后，其余乙方信息会自动带出。", placeholder: "", options: [], auto_fill: "party_b_name" },
  { key: "合作内容", label: "合作内容", type: "textarea", required: true, hint: "具体描述合作范围、服务内容或采购标的。", placeholder: "", options: [] },
  { key: "合同金额", label: "合同金额（元）", type: "currency", required: true, hint: "填写含税总价，仅填写数字。", placeholder: "", options: [] },
  { key: "金额大写", label: "金额大写", type: "text", required: true, hint: "填写人民币金额大写，须与小写金额一致。", placeholder: "", options: [] },
  { key: "权利义务", label: "权利义务", type: "textarea", required: true, hint: "明确双方主要权利义务及交付要求。", placeholder: "", options: [] },
  { key: "违约责任", label: "违约责任", type: "textarea", required: false, hint: "补充逾期、质量不达标等违约责任。", placeholder: "", options: [] },
  { key: "签署日期", label: "签署日期", type: "date", required: true, hint: "填写双方实际签署日期。", placeholder: "", options: [] },
];

const SKELETON_CONTENT = `
<h2 style="text-align: center">合同名称</h2>
<p>合同编号：{{合同编号}}</p>
<p>甲方（委托方）：{{甲方}}</p>
<p>乙方（服务方）：{{乙方}}</p>
<p>根据《中华人民共和国民法典》及相关法律法规，双方本着平等自愿、诚实信用的原则，就合作事宜达成如下协议：</p>
<h2>第一条 合作内容</h2>
<p>{{合作内容}}</p>
<h2>第二条 合同金额</h2>
<p>本合同含税总金额为人民币（大写）{{金额大写}}（¥{{合同金额}}）。</p>
<h2>第三条 双方权利义务</h2>
<p>{{权利义务}}</p>
<h2>第四条 违约责任</h2>
<p>{{违约责任}}</p>
<h2>第五条 其他</h2>
<p>5.1 本合同自双方签字盖章之日起生效。</p>
<p>5.2 本合同一式贰份，双方各执壹份，具有同等法律效力。</p>
<p>甲方（盖章）：{{甲方}}</p>
<p>乙方（盖章）：{{乙方}}</p>
<p>签署日期：{{签署日期}}</p>
`.trim();

export function TemplateEditorPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const isEdit = !!id;
  const editorRef = useRef<Editor | null>(null);
  const fieldListRef = useRef<HTMLDivElement>(null);
  const importDraft = (location.state as { importDraft?: TemplateImportDraft } | null)?.importDraft;
  const [loading, setLoading] = useState(isEdit);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [activeFields, setActiveFields] = useState<string[]>([]);
  const [templateStatus, setTemplateStatus] = useState<"active" | "archived">("active");
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [storedCategories, setStoredCategories] = useState<string[]>([]);
  const [version, setVersion] = useState("V1.0");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [content, setContent] = useState("");
  const [fields, setFields] = useState<TemplateField[]>(() => ensureTemplateSystemFields([]));
  const [importSource, setImportSource] = useState<TemplateImportDraft["source"] | null>(
    importDraft?.source ?? null,
  );

  useEffect(() => {
    let active = true;
    api
      .templateCategories()
      .then((result) => {
        if (active) setStoredCategories(result.items);
      })
      .catch(() => {
        if (active) setStoredCategories([]);
      });
    return () => {
      active = false;
    };
  }, []);

  const categoryOptions = useMemo(
    () =>
      Array.from(
        new Set([...DEFAULT_CATEGORIES, category, ...storedCategories].filter(Boolean)),
      ),
    [category, storedCategories],
  );

  useEffect(() => {
    if (isEdit || !importDraft) return;
    setName(importDraft.name);
    setCategory("");
    setDescription(importDraft.description || "");
    setInstructions(importDraft.instructions || "");
    setContent(importDraft.content);
    setFields(ensureTemplateSystemFields(importDraft.fields));
    setImportSource(importDraft.source);
  }, [isEdit, importDraft]);

  useEffect(() => {
    if (!isEdit) return;
    let active = true;
    api
      .template(id || "")
      .then((template) => {
        if (!active) return;
        setName(template.name);
        setCategory(template.category);
        setVersion(template.version);
        setDescription(template.description);
        setInstructions(template.instructions);
        setContent(template.content);
        setFields(ensureTemplateSystemFields(template.fields));
        setTemplateStatus(template.status);
      })
      .catch((caught) => {
        if (active) setError(caught instanceof ApiError ? caught.message : "模板加载失败");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [id, isEdit]);

  const placeholderKeys = useMemo(() => extractPlaceholderKeys(content), [content]);
  const fieldKeys = fields.map((field) => field.key);
  const missingDefinitions = placeholderKeys.filter(
    (key) =>
      !isSystemPlaceholderKey(key) &&
      !isAutoPlaceholderKey(key) &&
      !fieldKeys.includes(key),
  );
  const unusedFields = fields.filter(
    (field) => !isSystemTemplateField(field) && !placeholderKeys.includes(field.key),
  );
  const visibleFieldEntries = useMemo(
    () =>
      fields
        .map((field, index) => ({ field, index }))
        .filter(({ field }) => !isSystemTemplateField(field)),
    [fields],
  );
  const duplicateKeys = fieldKeys.filter((key, index) => key && fieldKeys.indexOf(key) !== index);
  const invalidKeys = fields.filter((field) => !FIELD_KEY_RE.test(field.key)).map((field) => field.label || field.key);
  const reservedFields = fields.filter((field) => isSystemPlaceholderKey(field.key));

  useLayoutEffect(() => {
    const container = fieldListRef.current?.querySelector<HTMLElement>(".field-collapse");
    if (container) container.scrollTop = container.scrollHeight;
  }, [visibleFieldEntries.length]);

  const updateField = (index: number, patch: Partial<TemplateField>) => {
    setFields((current) =>
      current.map((field, fieldIndex) => {
        if (fieldIndex !== index) return field;
        const next = { ...field, ...patch };
        if (Object.prototype.hasOwnProperty.call(patch, "label")) {
          const autoKey = sanitizeFieldKey(field.label);
          if (!field.key.trim() || field.key === autoKey) {
            next.key = sanitizeFieldKey(next.label);
          }
        }
        return next;
      }),
    );
  };

  const addField = () => {
    let suffix = fields.filter((field) => !isSystemTemplateField(field)).length + 1;
    let label = `空白项${suffix}`;
    while (fields.some((field) => field.key === label || field.label === label)) {
      suffix += 1;
      label = `空白项${suffix}`;
    }
    const newField: TemplateField = {
      key: label,
      label,
      type: "text",
      required: true,
      hint: "",
      placeholder: "",
      options: [],
    };
    setFields((current) => [...current, newField]);
    setActiveFields((current) => [...current, String(fields.length)]);
  };

  const removeField = (index: number) => {
    if (isSystemTemplateField(fields[index])) {
      message.warning("系统生成的空白项不可删除");
      return;
    }
    setFields((current) => current.filter((_, fieldIndex) => fieldIndex !== index));
    setActiveFields([]);
  };

  const insertToken = (key: string) => {
    if (!key) {
      message.warning("请先填写字段标识");
      return;
    }
    const token = `{{${key}}}`;
    const editor = editorRef.current;
    if (!editor) {
      setContent((current) => `${current}${token}`);
      return;
    }
    editor.chain().focus().insertContent(token).run();
  };

  const insertPlaceholder = (field: TemplateField) => insertToken(field.key);

  const loadSkeleton = () => {
    if (
      hasRichContent(content) ||
      fields.some((field) => !isSystemTemplateField(field))
    ) {
      message.info("当前已有模板内容，基础骨架仅用于空白模板。");
      return;
    }
    setContent(SKELETON_CONTENT);
    setFields(ensureTemplateSystemFields(SKELETON_FIELDS));
    message.success("已载入基础合同骨架，请按需调整");
  };

  const validate = (): TemplatePayload | null => {
    if (!name.trim()) {
      message.error("请填写合同名称");
      return null;
    }
    if (!category.trim()) {
      message.error("请选择或输入合同分类");
      return null;
    }
    if (!hasRichContent(content)) {
      message.error("请填写合同正文");
      return null;
    }
    if (fields.some((field) => !field.label.trim())) {
      message.error("每个空白项都需要填写显示名称");
      return null;
    }
    if (invalidKeys.length) {
      message.error(`字段标识格式不正确：${invalidKeys.join("、")}`);
      return null;
    }
    if (duplicateKeys.length) {
      message.error(`字段标识不能重复：${duplicateKeys[0]}`);
      return null;
    }
    if (missingDefinitions.length) {
      message.error(`正文中的空白项尚未配置：${missingDefinitions.join("、")}`);
      return null;
    }
    if (reservedFields.length) {
      message.error(`${CONTRACT_NUMBER_PLACEHOLDER}由系统自动生成，无需配置空白项`);
      return null;
    }
    return {
      name: name.trim(),
      contract_code: "HT",
      category: category.trim(),
      description: description.trim(),
      instructions: instructions.trim(),
      content,
      fields: ensureTemplateSystemFields(fields).map((field) => ({
        ...field,
        key: field.key.trim(),
        label: field.label.trim(),
        hint: field.hint.trim(),
        placeholder: field.placeholder.trim(),
        options: field.type === "select" ? field.options : [],
        auto_fill: normalizeAutoFill(field),
      })),
    };
  };

  const save = async () => {
    const payload = validate();
    if (!payload) return;
    setSaving(true);
    try {
      if (isEdit) {
        const result = await api.updateTemplate(id || "", payload);
        message.success(`模板已更新至 ${result.version}`);
      } else {
        const result = await api.createTemplate(payload);
        message.success(`模板已创建（${result.version}）`);
      }
      navigate("/templates");
    } catch (caught) {
      message.error(caught instanceof ApiError ? caught.message : "保存失败，请稍后重试");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="page-stack">
        <Skeleton active paragraph={{ rows: 3 }} />
        <div className="panel"><Skeleton active paragraph={{ rows: 14 }} /></div>
      </div>
    );
  }

  if (error) {
    return <Result status="error" title="模板加载失败" subTitle={error} extra={<Button onClick={() => navigate("/templates")}>返回模板库</Button>} />;
  }

  return (
    <div className="page-stack template-editor-page">
      <PageHeader
        eyebrow={isEdit ? "EDIT TEMPLATE" : "NEW TEMPLATE"}
        title={isEdit ? "编辑合同模板" : "新建合同模板"}
        description="像 Word 一样排版合同正文，空白项占位符支持中文，例如 {{甲方}}。"
        back={false}
        actions={
          <>
            <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/templates")}>返回</Button>
            <Button icon={<EyeOutlined />} onClick={() => setPreviewOpen(true)}>预览</Button>
            <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={save}>保存模板</Button>
          </>
        }
      />

      {templateStatus === "archived" && (
        <Alert
          type="warning"
          showIcon
          message="该模板已归档"
          description="你可以继续查看或调整模板，但归档状态不会自动恢复，业务人员仍无法选择此模板新建合同。"
        />
      )}

      {importSource && !isEdit && (
        <Alert
          type="info"
          showIcon
          message={`已从 ${importSource.filename} 导入模板草稿`}
          description={
            <div className="import-draft-desc">
              <span>
                自动识别到 {importSource.placeholder_count} 个占位符。请核对正文排版与空白项后再保存，
                保存后才会出现在业务人员的模板列表中。
              </span>
              {importSource.warnings.map((warning) => (
                <span key={warning} className="import-warning">{warning}</span>
              ))}
            </div>
          }
          closable
          onClose={() => setImportSource(null)}
        />
      )}

      <div className="panel editor-meta-panel">
        <div className="editor-panel-title">
          <div><span className="panel-eyebrow">TEMPLATE PROFILE</span><h3>基本信息</h3></div>
          <span className="editor-status"><span className="status-dot" />{templateStatus === "active" ? "有效模板" : "已归档"}</span>
        </div>
        <div className="editor-meta-grid">
          <div className="composer-field">
            <label htmlFor="template-name">合同名称 <em>*</em></label>
            <Input id="template-name" size="large" value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：标准采购合同" maxLength={120} />
          </div>
          <div className="composer-field">
            <label htmlFor="template-category">合同分类</label>
            <AutoComplete
              id="template-category"
              size="large"
              className="template-category-select"
              popupClassName="template-category-dropdown"
              value={category}
              onChange={setCategory}
              options={categoryOptions.map((item) => ({ value: item }))}
              placeholder="例如：采购类"
              filterOption={(input, option) => (option?.value || "").toLowerCase().includes(input.toLowerCase())}
            />
          </div>
          <div className="composer-field">
            <label>版本号</label>
            <div className="auto-version-field">
              <Tag color="blue" bordered={false}>{isEdit ? version : "V1.0"}</Tag>
              {!isEdit && <span>新建模板自动从 V1.0 开始</span>}
            </div>
          </div>
          <div className="composer-field editor-description-field">
            <label htmlFor="template-description">合同说明</label>
            <Input id="template-description" size="large" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="说明合同适用的业务场景" maxLength={1000} />
          </div>
        </div>
        <div className="composer-field">
          <label htmlFor="template-instructions"><InfoCircleOutlined /> 通用填写要求</label>
          <Input.TextArea
            id="template-instructions"
            rows={3}
            value={instructions}
            onChange={(event) => setInstructions(event.target.value)}
            placeholder="填写业务人员在使用该模板时需要遵守的通用要求，例如金额、付款节点、主体名称等要求。"
            maxLength={5000}
            showCount
          />
        </div>
      </div>

      <div className="template-editor-layout">
        <div className="editor-main-column">
          <div className="panel content-editor-panel">
            <div className="editor-panel-title">
              <div><span className="panel-eyebrow">CONTRACT BODY</span><h3>合同正文</h3></div>
              <div className="editor-toolbar">
                <Button size="small" icon={<ThunderboltOutlined />} onClick={loadSkeleton}>载入基础骨架</Button>
                <span className="char-counter">{htmlToPlainText(content).length.toLocaleString()} 字符</span>
              </div>
            </div>
            <div className="placeholder-toolbar">
              <span><CodeOutlined /> 插入空白项</span>
              <div>
                <button type="button" onClick={() => insertToken(CONTRACT_NUMBER_PLACEHOLDER)}>
                  {CONTRACT_NUMBER_PLACEHOLDER}（系统）
                </button>
                <button type="button" onClick={() => insertToken(PREPAYMENT_PLACEHOLDER)}>
                  {PREPAYMENT_PLACEHOLDER}（系统自动计算）
                </button>
                <button type="button" onClick={() => insertToken(FINAL_PAYMENT_PLACEHOLDER)}>
                  {FINAL_PAYMENT_PLACEHOLDER}（系统自动计算）
                </button>
                {fields.length ? (
                  fields.map((field) => (
                    <button type="button" key={field.key} onClick={() => insertPlaceholder(field)}>
                      {field.label || field.key}
                    </button>
                  ))
                ) : (
                  <small>请先在右侧添加空白项</small>
                )}
              </div>
            </div>
            <RichTextEditor
              value={content}
              onChange={setContent}
              onReady={(instance) => {
                editorRef.current = instance;
              }}
            />
            <div className="content-editor-foot">
              <span>
                占位格式：<code>{'{{甲方}}'}</code>，支持中文名称；<code>{'{{合同编号}}'}</code>
                由系统自动填充，<code>{'{{预付款}}'}</code>/<code>{'{{尾款}}'}</code>
                按合同总额自动计算并显示大写金额
              </span>
              <span>{placeholderKeys.length} 个占位符已使用</span>
            </div>
            {missingDefinitions.length > 0 && (
              <Alert
                type="error"
                showIcon
                message="存在未配置的空白项"
                description={`正文中使用了 ${missingDefinitions.join("、")}，请在右侧添加对应字段后再保存。`}
              />
            )}
            {unusedFields.length > 0 && (
              <Alert
                type="warning"
                showIcon
                message="部分字段尚未出现在正文中"
                description={`${unusedFields.map((field) => field.label).join("、")} 尚未插入占位符，业务人员仍可在表单中填写，但不会显示在合同正文。`}
              />
            )}
          </div>
        </div>

        <div className="editor-side-column">
          <div className="panel fields-config-panel">
            <div className="editor-panel-title">
              <div><span className="panel-eyebrow">BLANK FIELDS</span><h3>空白项配置</h3></div>
              <Button type="primary" ghost size="small" icon={<PlusOutlined />} onClick={addField}>添加空白项</Button>
            </div>
            <p className="fields-config-help">
              每个空白项对应业务表单中的一个输入控件，并可单独设置填写要求。甲方、乙方主体信息由系统自动生成，选择主体名称后会带出信用代码、地址、开户行等信息；联系人和联系方式由业务人员手动填写。总金额和总金额（大写）由表格「总额（元）」列自动计算。
            </p>

            {visibleFieldEntries.length ? (
              <div ref={fieldListRef}>
                <Collapse
                  activeKey={activeFields}
                  onChange={(keys) => setActiveFields(keys as string[])}
                  className="field-collapse"
                  items={visibleFieldEntries.map(({ field, index }, visibleIndex) => ({
                    key: String(index),
                    label: (
                      <div className="field-collapse-label">
                        <span className="field-order">
                          {String(visibleIndex + 1).padStart(2, "0")}
                        </span>
                        <strong>{field.label || "未命名空白项"}</strong>
                        <code>{'{{'}{field.key}{'}}'}</code>
                        {field.required && <Tag color="red" bordered={false}>必填</Tag>}
                        {resolveAutoFill(field) ? (
                          <Tag color="blue" bordered={false}>
                            {resolveAutoFill(field).startsWith("warehouse_") ? "仓库" : "主体库"}
                          </Tag>
                        ) : null}
                        <span className="field-type-mini">{fieldTypeLabel(field.type)}</span>
                      </div>
                    ),
                    children: (
                      <FieldConfig
                        field={field}
                        onChange={(patch) => updateField(index, patch)}
                        onInsert={() => insertPlaceholder(field)}
                        onRemove={() => removeField(index)}
                      />
                    ),
                  }))}
                />
              </div>
            ) : (
              <div className="fields-empty">
                <FileProtectOutlined />
                <strong>还没有空白项</strong>
                <span>添加空白项后，业务人员即可在表单中填写对应内容。</span>
                <Button type="primary" icon={<PlusOutlined />} onClick={addField}>添加第一个空白项</Button>
              </div>
            )}
          </div>

          <div className="panel editor-check-panel">
            <div className="panel-head"><div><span className="panel-eyebrow">CHECKLIST</span><h3>模板检查</h3></div></div>
            <div className="check-row"><CheckCircleOutlined className={name.trim() ? "ok" : ""} /><span>已填写合同名称</span></div>
            <div className="check-row"><CheckCircleOutlined className={hasRichContent(content) ? "ok" : ""} /><span>已填写合同正文</span></div>
            <div className="check-row"><CheckCircleOutlined className={fields.length ? "ok" : ""} /><span>已配置空白项</span></div>
            <div className="check-row"><CheckCircleOutlined className={!missingDefinitions.length && !duplicateKeys.length && !invalidKeys.length ? "ok" : ""} /><span>占位符与字段定义一致</span></div>
            <div className="editor-check-note">保存后，模板即出现在业务人员的模板选择列表中。</div>
          </div>
        </div>
      </div>

      <Drawer
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
        width={900}
        title={`模板预览 · ${name || "未命名模板"}`}
        className="template-preview-drawer"
        extra={<Button type="primary" icon={<EditOutlined />} onClick={() => setPreviewOpen(false)}>继续编辑</Button>}
      >
        <div className="drawer-template-meta">
          <Tag>{category}</Tag><span>{version}</span><span>{fields.length} 个空白项</span>
        </div>
        {instructions && (
          <div className="drawer-instructions"><strong>填写要求</strong><p>{instructions}</p></div>
        )}
        <div className="drawer-paper-stage">
          <ContractPaper
            title={name || "未命名模板"}
            content={content}
            values={{}}
            fields={fields}
            templateName={`${name || "未命名模板"} · ${version}`}
            highlight={false}
          />
        </div>
      </Drawer>
    </div>
  );
}

function FieldConfig({
  field,
  onChange,
  onInsert,
  onRemove,
}: {
  field: TemplateField;
  onChange: (patch: Partial<TemplateField>) => void;
  onInsert: () => void;
  onRemove: () => void;
}) {
  const autoFillRole = resolveAutoFill(field);
  const systemPartyField = isSystemPartyField(field);
  const systemAmountField = isSystemAmountField(field);
  const systemField = systemPartyField || systemAmountField;
  return (
    <div className="field-config-body">
      <div className="field-config-grid">
        <div className="composer-field">
          <label>显示名称 <em>*</em></label>
          <Input
            value={field.label}
            onChange={(event) => onChange({ label: event.target.value })}
            placeholder="例如：甲方名称"
            maxLength={80}
            disabled={systemField}
          />
        </div>
        <div className="composer-field">
          <label>字段标识 <em>*</em></label>
          <Input
            value={field.key}
            onChange={(event) => onChange({ key: event.target.value })}
            placeholder="默认与显示名称一致，可手动修改"
            maxLength={40}
            className="code-input"
            addonBefore="{{"
            addonAfter="}}"
            disabled={systemField}
          />
          <span className="field-help-inline">
            {systemAmountField
              ? "系统自动计算字段，字段标识和类型固定，可在正文中直接引用。"
              : systemPartyField
                ? "系统生成的主体字段，字段标识固定，便于正文占位符稳定引用。"
              : "新增空白项时自动取显示名称；支持中文，业务人员看到的就是这个名称。"}
          </span>
        </div>
        <div className="composer-field">
          <label>输入类型</label>
          <Select
            value={field.type}
            options={FIELD_TYPE_OPTIONS}
            onChange={(value: TemplateFieldType) => onChange({ type: value })}
            disabled={!!autoFillRole || systemField}
          />
        </div>
        <div className="composer-field">
          <label>数据来源</label>
          <Select
            value={autoFillRole}
            options={AUTO_FILL_OPTIONS}
            onChange={(value: TemplateField["auto_fill"]) => onChange({ auto_fill: value || "" })}
            disabled={systemField}
          />
          <span className="field-help-inline">
            {systemAmountField
              ? "该字段由系统自动计算，无需配置数据来源。"
              : systemPartyField
                ? "由系统从主体库自动生成。选择甲方/乙方主体名称后，同侧信用代码、地址、开户行等信息会自动带出；联系人和联系方式需手动填写。"
              : "选择「主体名称（下拉选择）」可从 mmdy_party_info 选择主体并带出同侧信息；选择「仓库简称（下拉选择并填充地址）」可从 mmdy_warehouse_info 选择仓库，正文填充该仓库的完整地址。"}
          </span>
        </div>
        <div className="composer-field required-switch-field">
          <label>是否必填</label>
          <div className="required-switch">
            <Switch checked={field.required} onChange={(checked) => onChange({ required: checked })} />
            <span>{field.required ? "业务人员必须填写" : "业务人员可跳过"}</span>
          </div>
        </div>
        <div className="composer-field">
          <label>占位提示</label>
          <Input value={field.placeholder} onChange={(event) => onChange({ placeholder: event.target.value })} placeholder="输入框中的提示文字" maxLength={200} />
        </div>
        {field.type === "select" && (
          <div className="composer-field field-options-field">
            <label>下拉选项</label>
            <Select
              mode="tags"
              className="field-options-tags"
              value={field.options}
              onChange={(values: string[]) =>
                onChange({
                  options: Array.from(new Set(values.map((item) => item.trim()).filter(Boolean))),
                })
              }
              tokenSeparators={[",", "，", "、", ";", "；"]}
              placeholder="输入一个选项后按回车，也可用逗号或顿号分隔多个选项"
              notFoundContent={null}
            />
          </div>
        )}
        <div className="composer-field field-hint-field">
          <label>填写要求</label>
          <Input.TextArea
            rows={3}
            value={field.hint}
            onChange={(event) => onChange({ hint: event.target.value })}
            placeholder="针对该空白项的具体填写要求，例如金额须与报价单一致。"
            maxLength={500}
            showCount
          />
        </div>
      </div>
      <div className="field-config-actions">
        <Button type="link" icon={<CodeOutlined />} onClick={onInsert}>插入到正文</Button>
        {!systemField && (
          <Button type="link" danger icon={<DeleteOutlined />} onClick={onRemove}>删除此项</Button>
        )}
      </div>
    </div>
  );
}
