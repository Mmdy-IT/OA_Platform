import {
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  FileProtectOutlined,
  FileTextOutlined,
  PlusOutlined,
  SearchOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { Button, Drawer, Empty, Input, Modal, Skeleton, Tag, message } from "antd";
import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api";
import { ContractPaper } from "../components/ContractPaper";
import { PageHeader } from "../components/PageHeader";
import type { Template } from "../types";
import { formatDate, formatRelative } from "../utils";

const CATEGORY_TONES: Record<string, string> = {
  采购类: "teal",
  服务类: "blue",
  保密类: "violet",
  通用: "slate",
  通用类: "slate",
};

type TemplateFilter = "all" | "active" | "archived";

export function TemplatesPage() {
  const navigate = useNavigate();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<TemplateFilter>("all");
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<Template | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    try {
      const result = await api.templates();
      setTemplates(result.items);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "模板列表加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const activeCount = templates.filter((item) => item.status === "active").length;
  const archivedCount = templates.filter((item) => item.status === "archived").length;
  const fieldsCount = templates.reduce((sum, item) => sum + item.fields.length, 0);
  const usageCount = templates.reduce((sum, item) => sum + item.usage_count, 0);

  const filtered = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return templates.filter((template) => {
      if (filter === "active" && template.status !== "active") return false;
      if (filter === "archived" && template.status !== "archived") return false;
      if (!keyword) return true;
      return [template.name, template.category, template.description]
        .join(" ")
        .toLowerCase()
        .includes(keyword);
    });
  }, [templates, filter, query]);

  const archive = (template: Template) => {
    Modal.confirm({
      title: "归档这个合同模板？",
      icon: <DeleteOutlined style={{ color: "#d64545" }} />,
      content: (
        <div className="confirm-copy">
          <p>归档后业务人员将无法再选择该模板新建合同。</p>
          <p className="muted-text">已创建的合同保存了模板快照，不受此次归档影响。</p>
        </div>
      ),
      okText: "确认归档",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: async () => {
        try {
          await api.archiveTemplate(template.id);
          message.success("模板已归档，历史合同不受影响");
          setTemplates((current) =>
            current.map((item) =>
              item.id === template.id ? { ...item, status: "archived" as const } : item,
            ),
          );
        } catch (caught) {
          message.error(caught instanceof ApiError ? caught.message : "归档失败");
        }
      },
    });
  };

  const removePermanently = (template: Template) => {
    Modal.confirm({
      title: "永久删除这个合同模板？",
      icon: <DeleteOutlined style={{ color: "#d64545" }} />,
      content: (
        <div className="confirm-copy">
          <p>删除后模板将从模板库中彻底移除，无法恢复。</p>
          <p className="muted-text">已创建的合同保存了完整模板快照，不受此次删除影响。</p>
        </div>
      ),
      okText: "确认删除",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: async () => {
        try {
          await api.permanentlyDeleteTemplate(template.id);
          message.success("模板已永久删除");
          setTemplates((current) => current.filter((item) => item.id !== template.id));
          setPreview((current) => (current?.id === template.id ? null : current));
        } catch (caught) {
          message.error(caught instanceof ApiError ? caught.message : "删除失败");
        }
      },
    });
  };

  const handleImport = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!/\.(docx|pdf)$/i.test(file.name)) {
      message.error("仅支持 Word（.docx）或 PDF 文件");
      return;
    }
    if (file.size > 12 * 1024 * 1024) {
      message.error("文件超过 12MB，请压缩或精简后重试");
      return;
    }
    setUploading(true);
    try {
      const draft = await api.importTemplate(file);
      message.success(`已识别 ${draft.source.placeholder_count} 个占位符，请核对后保存`);
      navigate("/templates/new", { state: { importDraft: draft } });
    } catch (caught) {
      message.error(caught instanceof ApiError ? caught.message : "模板导入失败，请稍后重试");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="TEMPLATE LIBRARY"
        title="合同模板"
        description="支持上传 Word/PDF 后在线排版，也支持新建模板。模板更新不影响已创建合同。"
        actions={
          <>
            <input
              ref={fileInputRef}
              type="file"
              accept=".docx,.pdf"
              hidden
              onChange={handleImport}
            />
            <Button
              size="large"
              icon={<UploadOutlined />}
              loading={uploading}
              onClick={() => fileInputRef.current?.click()}
            >
              上传 Word / PDF
            </Button>
            <Button type="primary" size="large" icon={<PlusOutlined />} onClick={() => navigate("/templates/new")}>
              新建模板
            </Button>
          </>
        }
      />

      <div className="template-stat-strip">
        <div><span>有效模板</span><strong>{activeCount}</strong><small>业务可选择</small></div>
        <div><span>已归档</span><strong>{archivedCount}</strong><small>仅保留历史</small></div>
        <div><span>空白项总数</span><strong>{fieldsCount}</strong><small>全部模板字段</small></div>
        <div><span>累计使用</span><strong>{usageCount}</strong><small>已创建合同</small></div>
      </div>

      <div className="panel templates-library-panel">
        <div className="contracts-toolbar">
          <div className="filter-pills">
            <button type="button" className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>
              全部 <span>{templates.length}</span>
            </button>
            <button type="button" className={filter === "active" ? "active" : ""} onClick={() => setFilter("active")}>
              有效 <span>{activeCount}</span>
            </button>
            <button type="button" className={filter === "archived" ? "active" : ""} onClick={() => setFilter("archived")}>
              已归档 <span>{archivedCount}</span>
            </button>
          </div>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索模板名称或分类"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="contract-search"
          />
        </div>

        {error && <div className="inline-error">{error}</div>}

        {loading ? (
          <div className="template-card-grid template-grid-in-panel">
            {Array.from({ length: 3 }).map((_, index) => (
              <div className="template-card" key={index}><Skeleton active paragraph={{ rows: 5 }} /></div>
            ))}
          </div>
        ) : filtered.length ? (
          <div className="template-card-grid template-grid-in-panel">
            {filtered.map((template) => {
              const tone = CATEGORY_TONES[template.category] || "slate";
              return (
                <article
                  className={`template-card template-${tone} ${template.status === "archived" ? "is-archived" : ""}`}
                  key={template.id}
                >
                  <div className="template-card-top">
                    <div className="template-card-icon"><FileProtectOutlined /></div>
                    <div className="template-card-badges">
                      <Tag bordered={false}>{template.category}</Tag>
                      <span>{template.version}</span>
                      {template.status === "archived" && <Tag color="default">已归档</Tag>}
                    </div>
                  </div>
                  <h3>{template.name}</h3>
                  <p>{template.description || "暂无合同说明"}</p>
                  <div className="template-field-preview">
                    {template.fields.slice(0, 4).map((field) => (
                      <span key={field.key} className={field.required ? "required" : ""}>{field.label}</span>
                    ))}
                    {template.fields.length > 4 && <span>+{template.fields.length - 4}</span>}
                  </div>
                  <div className="template-meta-grid">
                    <div><span>空白项</span><strong>{template.fields.length}</strong></div>
                    <div><span>使用次数</span><strong>{template.usage_count}</strong></div>
                    <div><span>更新</span><strong>{formatRelative(template.updated_at)}</strong></div>
                  </div>
                  <div className="template-card-foot template-card-actions">
                    <span className="updated-date">更新于 {formatDate(template.updated_at)}</span>
                    <div>
                      <Button type="text" size="small" icon={<EyeOutlined />} onClick={() => setPreview(template)}>预览</Button>
                      <Button
                        type="text"
                        size="small"
                        icon={<EditOutlined />}
                        onClick={() => navigate(`/templates/${template.id}/edit`)}
                      >
                        编辑
                      </Button>
                      {template.status === "active" ? (
                        <Button type="text" size="small" danger icon={<DeleteOutlined />} onClick={() => archive(template)}>
                          归档
                        </Button>
                      ) : (
                        <Button type="text" size="small" danger icon={<DeleteOutlined />} onClick={() => removePermanently(template)}>
                          删除
                        </Button>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的合同模板">
            {!query && filter === "all" && <Button type="primary" onClick={() => navigate("/templates/new")}>新建模板</Button>}
          </Empty>
        )}
      </div>

      <Drawer
        open={!!preview}
        onClose={() => setPreview(null)}
        width={860}
        title={preview ? `模板预览 · ${preview.name}` : "模板预览"}
        extra={
          preview && (
            <>
              {preview.status === "archived" && (
                <Button danger icon={<DeleteOutlined />} onClick={() => removePermanently(preview)}>
                  删除
                </Button>
              )}
              <Button type="primary" icon={<EditOutlined />} onClick={() => navigate(`/templates/${preview.id}/edit`)}>
                编辑模板
              </Button>
            </>
          )
        }
        className="template-preview-drawer"
      >
        {preview && (
          <>
            <div className="drawer-template-meta">
              <Tag>{preview.category}</Tag>
              <span>{preview.version}</span>
              <span><FileTextOutlined /> {preview.fields.length} 个空白项</span>
              <span>更新于 {formatDate(preview.updated_at)}</span>
            </div>
            {preview.instructions && (
              <div className="drawer-instructions">
                <strong>填写要求</strong>
                <p>{preview.instructions}</p>
              </div>
            )}
            <div className="drawer-paper-stage">
              <ContractPaper
                title={preview.name}
                content={preview.content}
                values={{}}
                fields={preview.fields}
                templateName={`${preview.name} · ${preview.version}`}
                highlight={false}
              />
            </div>
          </>
        )}
      </Drawer>
    </div>
  );
}
