import {
  AuditOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  FileTextOutlined,
  InboxOutlined,
  InfoCircleOutlined,
  RightOutlined,
  SearchOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { Button, Empty, Input, Skeleton } from "antd";
import dayjs from "dayjs";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { PageHeader } from "../components/PageHeader";
import { StatusTag } from "../components/StatusTag";
import type { ContractSummary } from "../types";
import { formatDateTime, formatRelative } from "../utils";

type QueueFilter = "all" | "today" | "overdue";

export function ReviewInboxPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [contracts, setContracts] = useState<ContractSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<QueueFilter>("all");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api
      .contracts({ status: "pending", scope: "all" })
      .then((result) => {
        if (active) {
          setContracts(
            [...result.items].sort(
              (a, b) => new Date(a.submitted_at || 0).getTime() - new Date(b.submitted_at || 0).getTime(),
            ),
          );
        }
      })
      .catch((caught) => {
        if (active) setError(caught instanceof ApiError ? caught.message : "审核队列加载失败");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const ownPendingCount = contracts.filter((item) => item.creator_id === user?.id).length;
  const reviewableContracts = useMemo(
    () => contracts.filter((item) => item.creator_id !== user?.id),
    [contracts, user?.id],
  );
  const todayCount = reviewableContracts.filter((item) => item.submitted_at && dayjs(item.submitted_at).isSame(dayjs(), "day")).length;
  const overdueCount = reviewableContracts.filter((item) => item.submitted_at && dayjs().diff(dayjs(item.submitted_at), "hour") >= 24).length;

  const filtered = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return reviewableContracts.filter((contract) => {
      if (filter === "today" && !(contract.submitted_at && dayjs(contract.submitted_at).isSame(dayjs(), "day"))) return false;
      if (filter === "overdue" && !(contract.submitted_at && dayjs().diff(dayjs(contract.submitted_at), "hour") >= 24)) return false;
      if (!keyword) return true;
      return [contract.title, contract.contract_no, contract.creator_name, contract.template_name]
        .join(" ")
        .toLowerCase()
        .includes(keyword);
    });
  }, [reviewableContracts, filter, query]);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="LEGAL REVIEW DESK"
        title="审核工作台"
        description="集中处理待审核合同，核对合同主体、金额、交付或服务范围及违约条款。"
      />

      <div className="review-hero">
        <div className="review-hero-main">
          <div className="review-hero-icon"><AuditOutlined /></div>
          <div>
            <span className="panel-eyebrow">PENDING REVIEW</span>
            <h2>{reviewableContracts.length ? `${reviewableContracts.length} 份合同等待审核` : "审核队列已清空"}</h2>
            <p>{reviewableContracts.length ? "按提交时间从早到晚排列，建议优先处理超过 24 小时的合同。" : "当前没有待你处理的合同，新的审核任务会自动出现在这里。"}</p>
          </div>
        </div>
        <div className="review-hero-stats">
          <div><span>待审核</span><strong>{reviewableContracts.length}</strong></div>
          <div><span>今日提交</span><strong>{todayCount}</strong></div>
          <div><span>超 24 小时</span><strong className={overdueCount ? "warn" : ""}>{overdueCount}</strong></div>
        </div>
      </div>

      {ownPendingCount > 0 && (
        <div className="review-self-note">
          <InfoCircleOutlined />
          <span>
            有 {ownPendingCount} 份合同由你本人发起，已从审核队列中排除。发起人与审核人需分离，请由其他法务人员处理。
          </span>
        </div>
      )}

      <div className="panel review-queue-panel">
        <div className="contracts-toolbar">
          <div className="filter-pills">
            <button type="button" className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>
              全部待审 <span>{reviewableContracts.length}</span>
            </button>
            <button type="button" className={filter === "today" ? "active" : ""} onClick={() => setFilter("today")}>
              今日提交 <span>{todayCount}</span>
            </button>
            <button type="button" className={filter === "overdue" ? "active" : ""} onClick={() => setFilter("overdue")}>
              超过 24 小时 <span>{overdueCount}</span>
            </button>
          </div>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索合同或发起人"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="contract-search"
          />
        </div>

        {error && <div className="inline-error">{error}</div>}

        {loading ? (
          <div className="review-queue-list">
            {Array.from({ length: 3 }).map((_, index) => (
              <div className="review-queue-card" key={index}><Skeleton active paragraph={{ rows: 2 }} /></div>
            ))}
          </div>
        ) : filtered.length ? (
          <div className="review-queue-list">
            {filtered.map((contract) => {
              const overdue = contract.submitted_at && dayjs().diff(dayjs(contract.submitted_at), "hour") >= 24;
              return (
                <div className="review-queue-card" key={contract.id}>
                  <div className="review-queue-file"><FileTextOutlined /></div>
                  <div className="review-queue-main">
                    <div className="review-queue-title">
                      <button type="button" onClick={() => navigate(`/contracts/${contract.id}`)}>{contract.title}</button>
                      {overdue && <span className="overdue-chip">超 24 小时</span>}
                    </div>
                    <div className="review-queue-meta">
                      <span>{contract.contract_no}</span>
                      <span>{contract.template_name}</span>
                      <span>发起人：{contract.creator_name}</span>
                    </div>
                  </div>
                  <div className="review-queue-time">
                    <ClockCircleOutlined />
                    <span>{formatRelative(contract.submitted_at)}提交</span>
                    <small>{formatDateTime(contract.submitted_at)}</small>
                  </div>
                  <StatusTag status={contract.status} />
                  <Button type="primary" onClick={() => navigate(`/contracts/${contract.id}`)}>
                    开始审核 <RightOutlined />
                  </Button>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="review-empty">
            {reviewableContracts.length ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前筛选条件下没有待审合同" />
            ) : (
              <>
                <div className="review-empty-icon"><CheckCircleOutlined /></div>
                <h3>所有合同均已处理</h3>
                <p>审核队列为空，新的待审合同会自动进入这里。</p>
              </>
            )}
          </div>
        )}
      </div>

      <div className="review-guide-grid">
        <div className="panel review-guide-card">
          <div className="guide-icon"><InboxOutlined /></div>
          <div><strong>集中审核</strong><span>所有业务合同统一进入法务审核队列，按提交时间排序。</span></div>
        </div>
        <div className="panel review-guide-card">
          <div className="guide-icon"><SafetyCertificateOutlined /></div>
          <div><strong>意见留痕</strong><span>通过或驳回意见将记录在合同流转时间线中。</span></div>
        </div>
        <div className="panel review-guide-card">
          <div className="guide-icon"><FileTextOutlined /></div>
          <div><strong>模板快照</strong><span>审核时查看的是发起时保存的模板版本，不受后续修改影响。</span></div>
        </div>
      </div>
    </div>
  );
}
