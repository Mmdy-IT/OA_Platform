import {
  ArrowLeftOutlined,
  ArrowRightOutlined,
  FileProtectOutlined,
  FileTextOutlined,
  SearchOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { Alert, Button, Empty, Input, Skeleton, Tag, message } from "antd";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { ContractComposer } from "../components/ContractComposer";
import { PageHeader } from "../components/PageHeader";
import type { BundleRequirement, ContractTableAdjustments, Template } from "../types";

const CATEGORY_TONES: Record<string, string> = {
  采购类: "teal",
  服务类: "blue",
  保密类: "violet",
  通用: "slate",
};

export function NewContractPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [draftId, setDraftId] = useState<number | null>(null);
  const [contractNo, setContractNo] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("全部");
  const [bundleRequirements, setBundleRequirements] = useState<BundleRequirement[]>([]);

  useEffect(() => {
    let active = true;
    api
      .templates()
      .then((result) => {
        if (!active) return;
        setTemplates(result.items);
        const requested = Number(searchParams.get("template"));
        if (requested && result.items.some((item) => item.id === requested)) {
          setSelectedId(requested);
        }
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
    // Initial route query only. Selection afterwards is handled locally.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selected = templates.find((item) => item.id === selectedId) || null;
  useEffect(() => {
    if (!selected) {
      setBundleRequirements([]);
      return;
    }
    let active = true;
    api
      .bundleRequirements(selected.id)
      .then((result) => {
        if (active) setBundleRequirements(result.items);
      })
      .catch(() => {
        if (active) setBundleRequirements([]);
      });
    return () => {
      active = false;
    };
  }, [selected?.id]);
  const categories = useMemo(
    () => ["全部", ...Array.from(new Set(templates.map((template) => template.category)))],
    [templates],
  );
  const filteredTemplates = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return templates.filter((template) => {
      if (category !== "全部" && template.category !== category) return false;
      if (!keyword) return true;
      return [template.name, template.description, template.category]
        .join(" ")
        .toLowerCase()
        .includes(keyword);
    });
  }, [templates, category, query]);

  const selectTemplate = (template: Template) => {
    setSelectedId(template.id);
    setDraftId(null);
    setContractNo("");
    const next = new URLSearchParams(searchParams);
    next.set("template", String(template.id));
    setSearchParams(next, { replace: true });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const changeTemplate = () => {
    setSelectedId(null);
    setDraftId(null);
    setContractNo("");
    const next = new URLSearchParams(searchParams);
    next.delete("template");
    setSearchParams(next, { replace: true });
  };

  const ensureDraft = async (
    title: string,
    values: Record<string, string>,
    tableAdjustments: ContractTableAdjustments,
  ) => {
    if (!selected) throw new Error("请选择合同模板");
    if (draftId) {
      const updated = await api.updateContract(draftId, {
        title,
        field_values: values,
        table_adjustments: tableAdjustments,
      });
      setContractNo(updated.contract_no);
      return draftId;
    }
    const created = await api.createContractBundle({
      template_id: selected.id,
      title,
      field_values: values,
      table_adjustments: tableAdjustments,
    });
    setDraftId(created.id);
    setContractNo(created.contract_no);
    return created.id;
  };

  const saveDraft = async (
    title: string,
    values: Record<string, string>,
    tableAdjustments: ContractTableAdjustments,
  ) => {
    try {
      const id = await ensureDraft(title, values, tableAdjustments);
      message.success("合同草稿已保存");
      navigate(`/contracts/${id}`);
    } catch (caught) {
      message.error(caught instanceof ApiError ? caught.message : "保存失败，请稍后重试");
    }
  };

  const submitReview = async (
    title: string,
    values: Record<string, string>,
    tableAdjustments: ContractTableAdjustments,
  ) => {
    try {
      const id = await ensureDraft(title, values, tableAdjustments);
      await api.submitContract(id);
      message.success("合同已提交法务审核");
      navigate(`/contracts/${id}`);
    } catch (caught) {
      message.error(caught instanceof ApiError ? caught.message : "提交失败，请稍后重试");
    }
  };

  if (selected) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow={draftId ? "EDIT DRAFT" : "NEW CONTRACT"}
          title="起草合同"
          description="按模板填写业务空白项，右侧将实时生成合同预览。"
          actions={
            <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/contracts")}>返回列表</Button>
          }
        />
        {bundleRequirements.length > 0 && (
          <Alert
            type="warning"
            showIcon
            message="该模板需要同时签署配套合同"
            description={`系统将自动生成配套合同草稿：${bundleRequirements
              .map((item) => item.name)
              .join("、")}。所有合同填写并审核通过后才可下载 PDF。`}
          />
        )}
        <ContractComposer
          template={selected}
          contractNo={contractNo || undefined}
          onChangeTemplate={changeTemplate}
          backAction={<Button size="large" onClick={() => navigate("/contracts")}>取消</Button>}
          onSaveDraft={saveDraft}
          onSubmitReview={submitReview}
        />
      </div>
    );
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="NEW CONTRACT"
        title="选择合同模板"
        description="所有模板由法务统一维护，并内置空白项填写要求。选择最符合业务场景的模板开始起草。"
        actions={<Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/contracts")}>返回列表</Button>}
      />

      <div className="flow-steps">
        <div className="flow-step active"><span>01</span><div><strong>选择模板</strong><small>使用法务标准版本</small></div></div>
        <div className="flow-step"><span>02</span><div><strong>填写内容</strong><small>完成模板空白项</small></div></div>
        <div className="flow-step"><span>03</span><div><strong>提交审核</strong><small>进入法务审核队列</small></div></div>
        <div className="flow-step"><span>04</span><div><strong>下载归档</strong><small>审核通过后生成 PDF</small></div></div>
      </div>

      {error && <div className="inline-error">{error}</div>}

      <div className="template-picker-toolbar">
        <div className="filter-pills">
          {categories.map((item) => (
            <button
              type="button"
              key={item}
              className={category === item ? "active" : ""}
              onClick={() => setCategory(item)}
            >
              {item}
              <span>{item === "全部" ? templates.length : templates.filter((template) => template.category === item).length}</span>
            </button>
          ))}
        </div>
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder="搜索模板"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="template-search"
        />
      </div>

      {loading ? (
        <div className="template-card-grid">
          {Array.from({ length: 3 }).map((_, index) => (
            <div className="template-card" key={index}><Skeleton active paragraph={{ rows: 5 }} /></div>
          ))}
        </div>
      ) : filteredTemplates.length ? (
        <div className="template-card-grid">
          {filteredTemplates.map((template) => {
            const tone = CATEGORY_TONES[template.category] || "slate";
            return (
              <button
                type="button"
                className={`template-card template-${tone}`}
                key={template.id}
                onClick={() => selectTemplate(template)}
              >
                <div className="template-card-top">
                  <div className="template-card-icon"><FileProtectOutlined /></div>
                  <div className="template-card-badges">
                    <Tag bordered={false}>{template.category}</Tag>
                    <span>{template.version}</span>
                  </div>
                </div>
                <h3>{template.name}</h3>
                <p>{template.description}</p>
                <div className="template-field-preview">
                  {template.fields.slice(0, 4).map((field) => (
                    <span key={field.key} className={field.required ? "required" : ""}>
                      {field.label}
                    </span>
                  ))}
                  {template.fields.length > 4 && <span>+{template.fields.length - 4}</span>}
                </div>
                <div className="template-card-foot">
                  <span><FileTextOutlined /> {template.fields.length} 个填写项</span>
                  <span className="use-template-link">使用此模板 <ArrowRightOutlined /></span>
                </div>
              </button>
            );
          })}
        </div>
      ) : (
        <div className="panel">
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={query ? "没有匹配的合同模板" : "暂无可用的合同模板，请联系法务维护"}
          />
        </div>
      )}

      <Alert
        className="template-tip"
        type="info"
        showIcon
        icon={<ThunderboltOutlined />}
        message="模板由法务统一维护"
        description="你正在使用的是当前最新有效版本。合同提交后将保存模板快照，后续模板更新不会影响已创建的合同。"
      />
    </div>
  );
}
