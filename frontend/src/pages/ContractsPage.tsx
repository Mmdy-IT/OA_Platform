import {
  ArrowRightOutlined,
  ClockCircleOutlined,
  FileTextOutlined,
  PlusOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { Button, Input, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { hasPermission, useAuth } from "../auth";
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

  const statusParam = searchParams.get("status") as ContractStatus | null;
  const activeStatus = STATUS_FILTERS.some((item) => item.key === statusParam)
    ? (statusParam as ContractStatus)
    : "all";
  const isReviewer = hasPermission(user, "reviews");

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
    ...(isReviewer
      ? [
          {
            title: "发起人",
            dataIndex: "creator_name",
            key: "creator_name",
            width: 150,
            render: (value: string) => <span className="muted-cell">{value}</span>,
          },
        ]
      : []),
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
      width: 82,
      align: "right",
      render: (_, record) => (
        <Button
          type="text"
          className="row-action"
          onClick={(event) => {
            event.stopPropagation();
            openContract(record);
          }}
        >
          {record.status === "pending" && isReviewer && record.creator_id !== user?.id ? "审核" : "查看"}
          <ArrowRightOutlined />
        </Button>
      ),
    },
  ];

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="CONTRACT REGISTER"
        title={isReviewer ? "全部合同" : "我的合同"}
        description={
          isReviewer
            ? "查看公司全部合同，进入合同详情完成法务审核、追踪流转记录。"
            : "管理由你发起的合同，完成填写、提交审核，并下载已通过的正式 PDF。"
        }
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
          scroll={{ x: 900 }}
        />
      </div>

      <div className="contract-help-strip">
        <div className="help-strip-icon"><ClockCircleOutlined /></div>
        <div>
          <strong>审核通过后才能下载正式 PDF</strong>
          <span>草稿和待审核阶段可在线预览合同内容；被驳回后可根据审核意见修改并重新提交。</span>
        </div>
        {!isReviewer && (
          <Tag color="blue" className="help-strip-tag">状态：待审核 / 已通过 / 已驳回</Tag>
        )}
      </div>
    </div>
  );
}
