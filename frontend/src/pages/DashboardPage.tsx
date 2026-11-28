import {
  ArrowRightOutlined,
  AuditOutlined,
  BankOutlined,
  BookOutlined,
  CalendarOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  FileAddOutlined,
  FileProtectOutlined,
  FileTextOutlined,
  IdcardOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
  ShopOutlined,
  TeamOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { Button, Skeleton, Tag } from "antd";
import dayjs from "dayjs";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api";
import { hasPermission, useAuth } from "../auth";
import type { DashboardData } from "../types";
import { initials } from "../utils";

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 6) return "夜深了";
  if (hour < 12) return "上午好";
  if (hour < 18) return "下午好";
  return "晚上好";
}

const OA_MODULES = [
  {
    key: "contract",
    name: "合同管理",
    description: "起草、审批、用印归档与合同台账",
    icon: <FileTextOutlined />,
    status: "已上线",
    live: true,
  },
  {
    key: "hr",
    name: "人事管理",
    description: "员工档案、组织信息与人事流程",
    icon: <TeamOutlined />,
    status: "规划中",
    live: false,
  },
  {
    key: "finance",
    name: "财务协同",
    description: "费用报销、付款申请与预算协同",
    icon: <BankOutlined />,
    status: "规划中",
    live: false,
  },
  {
    key: "procurement",
    name: "采购管理",
    description: "采购申请、询比价与供应商协同",
    icon: <ShopOutlined />,
    status: "规划中",
    live: false,
  },
  {
    key: "admin",
    name: "行政办公",
    description: "用章、证照、资产与行政服务",
    icon: <IdcardOutlined />,
    status: "规划中",
    live: false,
  },
  {
    key: "knowledge",
    name: "知识中心",
    description: "制度、模板与组织知识沉淀",
    icon: <BookOutlined />,
    status: "规划中",
    live: false,
  },
];

const WEEKDAYS = ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"];

export function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [contractData, setContractData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api
      .dashboard()
      .then((result) => {
        if (active) setContractData(result);
      })
      .catch((caught) => {
        if (active) {
          setError(caught instanceof ApiError ? caught.message : "工作台数据加载失败");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const displayName = user?.display_name.split(" · ")[0] || user?.username || "";
  const canUseContracts = hasPermission(user, "contracts") || hasPermission(user, "reviews");
  const canCreate = hasPermission(user, "contracts");
  const canReview = hasPermission(user, "reviews");
  const pendingCount = contractData?.pending_contracts.length || 0;
  const contractPath = canCreate ? "/contracts" : "/reviews";
  const quickActions = useMemo(
    () =>
      [
        canUseContracts
          ? {
              key: "overview",
              label: "合同概览",
              description: "查看合同流转与待办",
              icon: <FileProtectOutlined />,
              onClick: () => navigate("/contract-overview"),
            }
          : null,
        canCreate
          ? {
              key: "new",
              label: "发起合同",
              description: "从标准模板开始起草",
              icon: <FileAddOutlined />,
              onClick: () => navigate("/contracts/new"),
            }
          : null,
        canReview
          ? {
              key: "review",
              label: "审核队列",
              description: "处理待审合同",
              icon: <AuditOutlined />,
              onClick: () => navigate("/reviews"),
            }
          : null,
        {
          key: "permission",
          label: "权限申请",
          description: "申请业务模块使用权限",
          icon: <SafetyCertificateOutlined />,
          onClick: () => navigate("/permission-requests"),
        },
      ].filter(Boolean) as {
        key: string;
        label: string;
        description: string;
        icon: ReactNode;
        onClick: () => void;
      }[],
    [canCreate, canReview, canUseContracts, navigate],
  );

  return (
    <div className="page-stack oa-home-page">
      <section className="oa-home-hero">
        <div className="oa-home-hero-copy">
          <span className="oa-home-eyebrow">MMDY BUSINESS OS · 企业协同中枢</span>
          <h1>{greeting()}，{displayName}</h1>
          <p>
            欢迎进入绵绵聚道企业协同 OA。以统一身份、统一流程和统一数据，
            连接合同、人事、财务、采购及行政等全线业务。
          </p>
          <div className="oa-home-hero-meta">
            <span><CalendarOutlined /> {dayjs().format("YYYY年M月D日")} {WEEKDAYS[dayjs().day()]}</span>
            <span><UserOutlined /> {user?.department || "部门未设置"}</span>
            <span>{user?.job_title || "岗位未设置"}</span>
          </div>
          <div className="oa-home-hero-actions">
            {canUseContracts && (
              <Button type="primary" size="large" icon={<FileTextOutlined />} onClick={() => navigate("/contract-overview")}>
                进入合同管理
              </Button>
            )}
            <Button size="large" icon={<PlusOutlined />} onClick={() => navigate("/permission-requests")}>
              申请模块权限
            </Button>
          </div>
        </div>
        <div className="oa-home-hero-art" aria-hidden="true">
          <div className="oa-orbit oa-orbit-one" />
          <div className="oa-orbit oa-orbit-two" />
          <div className="oa-core-card">
            <span className="oa-core-mark">MM</span>
            <strong>统一业务门户</strong>
            <small>ONE ENTERPRISE · ONE WORKSPACE</small>
          </div>
          <div className="oa-art-chip oa-art-chip-top">
            <CheckCircleOutlined />
            <span>流程在线</span>
          </div>
          <div className="oa-art-chip oa-art-chip-bottom">
            <ClockCircleOutlined />
            <span>{pendingCount} 项合同待办</span>
          </div>
        </div>
      </section>

      {error && <div className="inline-error">{error}</div>}

      <section className="oa-section">
        <div className="oa-section-head">
          <div>
            <span className="panel-eyebrow">BUSINESS MODULES</span>
            <h2>业务应用</h2>
          </div>
          <span>统一入口逐步接入企业全线业务</span>
        </div>
        <div className="oa-module-grid">
          {OA_MODULES.map((module) => (
            <button
              type="button"
              key={module.key}
              className={`oa-module-card ${module.live && canUseContracts ? "is-live" : "is-planned"}`}
              disabled={!module.live || !canUseContracts}
              onClick={() => module.live && navigate("/contract-overview")}
            >
              <span className="oa-module-icon">{module.icon}</span>
              <span className="oa-module-copy">
                <strong>{module.name}</strong>
                <small>{module.description}</small>
              </span>
              <Tag bordered={false} className={module.live ? "oa-live-tag" : "oa-planned-tag"}>
                {module.status}
              </Tag>
            </button>
          ))}
        </div>
      </section>

      <section className="oa-home-grid">
        <div className="panel oa-quick-panel">
          <div className="panel-head">
            <div>
              <span className="panel-eyebrow">QUICK ACCESS</span>
              <h3>快捷入口</h3>
            </div>
          </div>
          <div className="oa-quick-grid">
            {quickActions.map((action) => (
              <button type="button" key={action.key} className="oa-quick-item" onClick={action.onClick}>
                <span>{action.icon}</span>
                <div>
                  <strong>{action.label}</strong>
                  <small>{action.description}</small>
                </div>
                <ArrowRightOutlined />
              </button>
            ))}
          </div>
        </div>

        <div className="panel oa-profile-panel">
          <div className="oa-profile-head">
            <span className="oa-profile-avatar">{initials(user?.display_name)}</span>
            <div>
              <strong>{user?.display_name}</strong>
              <span>{user?.job_title || "岗位未设置"}</span>
            </div>
          </div>
          <div className="oa-profile-list">
            <div><span>所属部门</span><strong>{user?.department || "未设置"}</strong></div>
            <div><span>系统账号</span><strong>{user?.username}</strong></div>
            <div><span>今日日期</span><strong>{dayjs().format("YYYY-MM-DD")}</strong></div>
          </div>
        </div>

        <div className="panel oa-todo-panel">
          <div className="panel-head">
            <div>
              <span className="panel-eyebrow">TO-DO</span>
              <h3>我的待办</h3>
            </div>
            {pendingCount > 0 && <span className="oa-count-badge">{pendingCount}</span>}
          </div>
          {loading ? (
            <Skeleton active paragraph={{ rows: 3 }} />
          ) : contractData?.pending_contracts.length ? (
            <div className="oa-todo-list">
              {contractData.pending_contracts.slice(0, 3).map((contract) => (
                <button type="button" key={contract.id} onClick={() => navigate(`/contracts/${contract.id}`)}>
                  <span className="oa-todo-dot" />
                  <div>
                    <strong>{contract.title}</strong>
                    <small>{canReview ? `${contract.creator_name} · ` : ""}{contract.contract_no || "配套通用合同"}</small>
                  </div>
                  <ArrowRightOutlined />
                </button>
              ))}
            </div>
          ) : (
            <div className="oa-empty-todo">
              <CheckCircleOutlined />
              <strong>暂无待办</strong>
              <span>当前合同流程均已处理完成</span>
            </div>
          )}
          <Button block onClick={() => navigate(canReview ? "/reviews" : contractPath)}>
            查看全部待办
          </Button>
        </div>
      </section>

      <section className="panel oa-notice-panel">
        <div>
          <span className="panel-eyebrow">PLATFORM NOTICE</span>
          <h3>平台动态</h3>
        </div>
        <div className="oa-notice-list">
          <div><Tag className="oa-live-tag">已上线</Tag><span>合同管理模块正式运行，支持模板、合同包、法务审核和 PDF 归档。</span></div>
          <div><Tag className="oa-planned-tag">规划中</Tag><span>人事、财务、采购、行政和知识中心将按业务优先级逐步接入。</span></div>
          <div><Tag className="oa-planned-tag">统一身份</Tag><span>飞书免登已启用，人员岗位、部门和权限由组织信息统一维护。</span></div>
        </div>
      </section>
    </div>
  );
}
