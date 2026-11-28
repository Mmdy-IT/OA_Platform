import {
  ArrowRightOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  FileAddOutlined,
  FileDoneOutlined,
  FileProtectOutlined,
  FileTextOutlined,
  InboxOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { Button, Empty, Skeleton, Tag } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api";
import { hasPermission, useAuth } from "../auth";
import { PageHeader } from "../components/PageHeader";
import { StatusTag } from "../components/StatusTag";
import type { DashboardData } from "../types";
import { formatRelative, STATUS_META } from "../utils";

export function ContractOverviewPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api
      .dashboard()
      .then((result) => {
        if (active) setData(result);
      })
      .catch((caught) => {
        if (active) setError(caught instanceof ApiError ? caught.message : "工作台加载失败");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const isReviewer = hasPermission(user, "reviews");
  const canCreate = hasPermission(user, "contracts");
  const canManageTemplates = hasPermission(user, "templates");
  const contractPath = canCreate ? "/contracts" : "/reviews";
  const stats = data?.stats;
  const pendingCount = data?.pending_contracts.length || 0;

  return (
    <div className="page-stack contract-overview-page">
      <PageHeader
        eyebrow="CONTRACT MANAGEMENT · 合同概览"
        title="合同管理概览"
        description={isReviewer ? "汇总公司合同流转、模板使用和待你处理的法务审核任务。" : "管理本人发起的合同，跟踪审核进度，获取审核通过的正式 PDF。"}
        actions={
          canCreate ? (
            <Button type="primary" size="large" icon={<PlusOutlined />} onClick={() => navigate("/contracts/new")}>
              新建合同
            </Button>
          ) : undefined
        }
      />

      {error && <div className="inline-error">{error}</div>}

      <section className="dashboard-hero">
        <div className="hero-copy">
          <Tag className="hero-tag"><SafetyCertificateOutlined /> 合同全流程在线协同</Tag>
          <h2>把复杂的合同流程，<br /><span>变成清晰的每一步。</span></h2>
          <p>法务统一模板 · 业务按需填写 · 审核留痕 · PDF 归档</p>
          <div className="hero-actions">
            {canCreate && (
              <Button type="primary" icon={<FileAddOutlined />} onClick={() => navigate("/contracts/new")}>
                起草新合同
              </Button>
            )}
            {isReviewer ? (
              <Button icon={<InboxOutlined />} onClick={() => navigate("/reviews")}>
                查看待审任务
              </Button>
            ) : (
              <Button icon={<FileTextOutlined />} onClick={() => navigate(contractPath)}>
                {canCreate ? "查看我的合同" : "查看审核任务"}
              </Button>
            )}
          </div>
        </div>
        <div className="hero-visual" aria-hidden="true">
          <div className="hero-orbit orbit-one" />
          <div className="hero-orbit orbit-two" />
          <div className="hero-document">
            <div className="hero-document-head">
              <FileDoneOutlined />
              <span>CONTRACT</span>
            </div>
            <div className="hero-document-line wide" />
            <div className="hero-document-line" />
            <div className="hero-document-line medium" />
            <div className="hero-document-stamp"><CheckCircleOutlined /> LEGAL APPROVED</div>
          </div>
          <div className="hero-float-card float-top">
            <span className="float-icon green"><CheckCircleOutlined /></span>
            <div><strong>审核通过</strong><span>可下载 PDF</span></div>
          </div>
          <div className="hero-float-card float-bottom">
            <span className="float-icon blue"><ClockCircleOutlined /></span>
            <div><strong>{pendingCount} 份待审</strong><span>法务处理中</span></div>
          </div>
        </div>
      </section>

      <section className="stats-grid">
        {loading || !stats ? (
          Array.from({ length: 4 }).map((_, index) => (
            <div className="stat-card" key={index}><Skeleton active paragraph={{ rows: 1 }} /></div>
          ))
        ) : (
          <>
            <button className="stat-card stat-navy" type="button" onClick={() => navigate(contractPath)}>
              <div className="stat-icon"><FileTextOutlined /></div>
              <div className="stat-copy"><span>{isReviewer ? "合同总量" : "我的合同"}</span><strong>{stats.total}</strong></div>
              <div className="stat-foot">全部合同记录 <ArrowRightOutlined /></div>
            </button>
            <button className="stat-card stat-amber" type="button" onClick={() => navigate(isReviewer ? "/reviews" : "/contracts?status=pending")}>
              <div className="stat-icon"><ClockCircleOutlined /></div>
              <div className="stat-copy"><span>{isReviewer ? "待我审核" : "待审核"}</span><strong>{stats.pending}</strong></div>
              <div className="stat-foot">等待法务处理 <ArrowRightOutlined /></div>
            </button>
            <button className="stat-card stat-green" type="button" onClick={() => navigate(canCreate ? "/contracts?status=approved" : "/reviews")}>
              <div className="stat-icon"><FileDoneOutlined /></div>
              <div className="stat-copy"><span>已通过</span><strong>{stats.approved}</strong></div>
              <div className="stat-foot">可下载正式 PDF <ArrowRightOutlined /></div>
            </button>
            <button
              className="stat-card stat-blue"
              type="button"
              onClick={() => navigate(canManageTemplates ? "/templates" : canCreate ? "/contracts/new" : contractPath)}
            >
              <div className="stat-icon"><FileProtectOutlined /></div>
              <div className="stat-copy"><span>{canManageTemplates ? "可用模板" : "模板库"}</span><strong>{stats.templates}</strong></div>
              <div className="stat-foot">{canManageTemplates ? "维护标准合同模板" : "选择模板快速起草"} <ArrowRightOutlined /></div>
            </button>
          </>
        )}
      </section>

      <section className="dashboard-grid">
        <div className="panel recent-panel">
          <div className="panel-head">
            <div>
              <span className="panel-eyebrow">RECENT ACTIVITY</span>
              <h3>最近合同</h3>
            </div>
            <Button type="link" onClick={() => navigate("/contracts")}>查看全部 <ArrowRightOutlined /></Button>
          </div>
          {loading ? (
            <Skeleton active paragraph={{ rows: 7 }} />
          ) : data?.recent_contracts.length ? (
            <div className="contract-list">
              {data.recent_contracts.map((contract) => (
                <button
                  type="button"
                  className="contract-list-row"
                  key={contract.id}
                  onClick={() => navigate(`/contracts/${contract.id}`)}
                >
                  <div className={`contract-file-icon ${STATUS_META[contract.status].tone}`}>
                    <FileTextOutlined />
                  </div>
                  <div className="contract-list-main">
                    <div className="contract-list-title">
                      <strong>{contract.title}</strong>
                      <StatusTag status={contract.status} />
                    </div>
                    <div className="contract-list-meta">
                      <span>{contract.contract_no}</span>
                      <span>{contract.template_name}</span>
                      {isReviewer && <span>发起人：{contract.creator_name}</span>}
                    </div>
                  </div>
                  <div className="contract-list-time">{formatRelative(contract.updated_at)}</div>
                  <ArrowRightOutlined className="contract-list-arrow" />
                </button>
              ))}
            </div>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有合同记录">
              {canCreate && <Button type="primary" onClick={() => navigate("/contracts/new")}>起草第一份合同</Button>}
            </Empty>
          )}
        </div>

        <div className="dashboard-side">
          <div className="panel todo-panel">
            <div className="panel-head">
              <div>
                <span className="panel-eyebrow">ACTION REQUIRED</span>
                <h3>{isReviewer ? "待审核队列" : "我的待办"}</h3>
              </div>
              {isReviewer && pendingCount > 0 && <span className="count-badge">{pendingCount}</span>}
            </div>
            {loading ? (
              <Skeleton active paragraph={{ rows: 4 }} />
            ) : data?.pending_contracts.length ? (
              <div className="todo-list">
                {data.pending_contracts.map((contract) => (
                  <button
                    type="button"
                    className="todo-row"
                    key={contract.id}
                    onClick={() => navigate(`/contracts/${contract.id}`)}
                  >
                    <span className="todo-indicator" />
                    <div>
                      <strong>{contract.title}</strong>
                      <span>{isReviewer ? `${contract.creator_name} · ` : ""}{formatRelative(contract.submitted_at)}提交</span>
                    </div>
                    <ArrowRightOutlined />
                  </button>
                ))}
                <Button block onClick={() => navigate(isReviewer ? "/reviews" : "/contracts?status=pending")}>
                  查看全部待办
                </Button>
              </div>
            ) : (
              <div className="empty-compact">
                <CheckCircleOutlined />
                <strong>当前没有待办</strong>
                <span>{isReviewer ? "审核队列已清空" : "所有合同均无待处理事项"}</span>
              </div>
            )}
          </div>

          <div className="panel status-panel">
            <div className="panel-head">
              <div>
                <span className="panel-eyebrow">PIPELINE</span>
                <h3>流程分布</h3>
              </div>
            </div>
            {loading || !stats ? (
              <Skeleton active paragraph={{ rows: 4 }} />
            ) : (
              <div className="status-bars">
                {(["draft", "pending", "approved", "rejected"] as const).map((status) => {
                  const count = stats[status];
                  const percent = stats.total ? Math.round((count / stats.total) * 100) : 0;
                  return (
                    <div className="status-bar-row" key={status}>
                      <div className="status-bar-label">
                        <span className={`bar-dot ${STATUS_META[status].tone}`} />
                        <span>{STATUS_META[status].label}</span>
                        <strong>{count}</strong>
                      </div>
                      <div className="bar-track">
                        <div className={`bar-fill ${STATUS_META[status].tone}`} style={{ width: `${Math.max(percent, count ? 6 : 0)}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
