import {
  ArrowRightOutlined,
  ClockCircleOutlined,
  DeleteOutlined,
  FileTextOutlined,
  PlusOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { Button, Input, Modal, Table, Tag, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { PageHeader } from "../components/PageHeader";
import { StatusTag } from "../components/StatusTag";
import type { ContractStatus, ContractSummary } from "../types";
import { formatDateTime, formatRelative, STATUS_META } from "../utils";

const STATUS_FILTERS: { key: ContractStatus | "all"; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "draft", label: "草稿" },
  { key: "pending", label: "待审核" },
  { key: "approved", label: "已通过" },
  { key: "rejected", label: "已驳回" },
];

export function ContractsPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [contracts, setContracts] = useState<ContractSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const statusParam = searchParams.get("status") as ContractStatus | null;
  const activeStatus = STATUS_FILTERS.some((item) => item.key === statusParam)
    ? (statusParam as ContractStatus)
    : "all";
  const canManage = user?.role === "admin" || user?.role === "legal";

  useEffect(() => {
    let active = true;
    setLoading(true);
    api
      .contracts()
      .then((result) => {
        if (active) setContracts(result.items);
      })
      .catch((caught) => {
        if (active) setError(caught instanceof ApiError ? caught.message : "合同列表加载失败");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const counts = useMemo(() => {
    return contracts.reduce<Record<string, number>>(
      (acc, contract) => {
        acc.all += 1;
        acc[contract.status] = (acc[contract.status] || 0) + 1;
        return acc;
      },
      { all: 0 },
    );
  }, [contracts]);

  const filtered = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return contracts.filter((contract) => {
      if (activeStatus !== "all" && contract.status !== activeStatus) return false;
      if (!keyword) return true;
      return [contract.title, contract.contract_no, contract.template_name, contract.creator_name]
        .join(" ")
        .toLowerCase()
        .includes(keyword);
    });
  }, [contracts, activeStatus, query]);

  const setStatus = (status: ContractStatus | "all") => {
    const next = new URLSearchParams(searchParams);
    if (status === "all") next.delete("status");
    else next.set("status", status);
    setSearchParams(next, { replace: true });
  };

  const openContract = (contract: ContractSummary) => navigate(`/contracts/${contract.id}`);

  const removeContract = (contract: ContractSummary) => {
    Modal.confirm({
      title: "确认删除这份合同？",
      content: (
        <div className="confirm-copy">
          <p>
            即将删除《{contract.title}》，合同内容及全部流转记录将无法恢复。
          </p>
          <p className="muted-text">此操作不可撤销，请再次确认。</p>
        </div>
      ),
      okText: "确认删除",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: async () => {
        setDeletingId(contract.id);
        try {
          await api.deleteContract(contract.id);
          setContracts((current) => current.filter((item) => item.id !== contract.id));
          message.success("合同已删除");
        } catch (caught) {
          message.error(caught instanceof ApiError ? caught.message : "删除失败，请稍后重试");
        } finally {
          setDeletingId(null);
        }
      },
    });
  };

  const columns: ColumnsType<ContractSummary> = [
    {
      title: "合同",
      key: "contract",
      width: "36%",
      render: (_, record) => (
        <div className="table-contract-cell">
          <div className={`table-file-icon ${STATUS_META[record.status].tone}`}>
            <FileTextOutlined />
          </div>
          <div>
            <strong>{record.title}</strong>
            <span>{record.contract_no}</span>
          </div>
        </div>
      ),
    },
    {
      title: "合同模板",
      dataIndex: "template_name",
      key: "template_name",
      render: (value, record) => (
        <div className="template-cell">
          <span>{value}</span>
          <small>{record.template_version}</small>
        </div>
      ),
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 110,
      render: (value: ContractStatus) => <StatusTag status={value} />,
    },
    {
      title: "最近更新",
      dataIndex: "updated_at",
      key: "updated_at",
      width: 160,
      render: (value: string) => (
        <div className="date-cell">
          <span>{formatDateTime(value)}</span>
          <small>{formatRelative(value)}</small>
        </div>
      ),
    },
    {
      title: "",
      key: "action",
      width: canManage ? 160 : 82,
      align: "right",
      render: (_, record) => (
        <div style={{ display: "inline-flex", alignItems: "center", gap: 2 }}>
          <Button
            type="text"
            className="row-action"
            onClick={(event) => {
              event.stopPropagation();
              openContract(record);
            }}
          >
            查看
            <ArrowRightOutlined />
          </Button>
          {canManage && (
            <Button
              type="text"
              danger
              className="row-action"
              icon={<DeleteOutlined />}
              loading={deletingId === record.id}
              disabled={!!record.bundle_id}
              title={record.bundle_id ? "合同包合同不能单独删除" : "删除合同"}
              onClick={(event) => {
                event.stopPropagation();
                removeContract(record);
              }}
            />
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="CONTRACT REGISTER"
        title="我的合同"
        description="仅查看和管理由你本人发起的合同，完成填写、提交审核，并下载已通过的正式 PDF。"
        actions={
          <Button type="primary" size="large" icon={<PlusOutlined />} onClick={() => navigate("/contracts/new")}>
            新建合同
          </Button>
        }
      />

      <div className="panel contracts-panel">
        <div className="contracts-toolbar">
          <div className="filter-pills">
            {STATUS_FILTERS.map((item) => (
              <button
                type="button"
                key={item.key}
                className={activeStatus === item.key ? "active" : ""}
                onClick={() => setStatus(item.key)}
              >
                {item.label}
                <span>{counts[item.key] || 0}</span>
              </button>
            ))}
          </div>
          <div className="toolbar-actions">
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder="搜索合同名称、编号或模板"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              className="contract-search"
            />
          </div>
        </div>

        {error && <div className="inline-error">{error}</div>}

        <Table
          rowKey="id"
          columns={columns}
          dataSource={filtered}
          loading={loading}
          pagination={{
            pageSize: 10,
            showSizeChanger: false,
            showTotal: (total) => `共 ${total} 份合同`,
            hideOnSinglePage: filtered.length <= 10,
          }}
          onRow={(record) => ({
            onClick: () => openContract(record),
            className: "clickable-row",
          })}
          locale={{
            emptyText: (
              <div className="table-empty">
                <div className="empty-icon"><FileTextOutlined /></div>
                <strong>{query || activeStatus !== "all" ? "没有匹配的合同" : "还没有合同"}</strong>
                <span>{query || activeStatus !== "all" ? "尝试调整筛选条件或搜索关键词" : "选择一份标准模板，开始起草第一份合同"}</span>
                {!query && activeStatus === "all" && (
                  <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate("/contracts/new")}>
                    新建合同
                  </Button>
                )}
              </div>
            ),
          }}
          scroll={{ x: canManage ? 980 : 900 }}
        />
      </div>

      <div className="contract-help-strip">
        <div className="help-strip-icon"><ClockCircleOutlined /></div>
        <div>
          <strong>审核通过后才能下载正式 PDF</strong>
          <span>草稿和待审核阶段可在线预览合同内容；被驳回后可根据审核意见修改并重新提交。</span>
        </div>
        <Tag color="blue" className="help-strip-tag">状态：待审核 / 已通过 / 已驳回</Tag>
      </div>
    </div>
  );
}
