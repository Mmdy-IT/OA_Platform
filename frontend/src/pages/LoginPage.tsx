import {
  AppstoreOutlined,
  ArrowRightOutlined,
  LockOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { Alert, Button, Input, Tag } from "antd";
import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api";
import { homePathForUser, useAuth } from "../auth";

const DEMO_ACCOUNTS = [
  {
    role: "业务人员",
    username: "business",
    password: "Business@123",
    name: "陈晨",
    description: "起草合同、提交审核",
    tone: "teal",
  },
  {
    role: "法务人员",
    username: "legal",
    password: "Legal@123",
    name: "林静",
    description: "维护模板、审核合同",
    tone: "blue",
  },
  {
    role: "系统管理员",
    username: "admin",
    password: "Admin@123",
    name: "管理员",
    description: "全局查看与系统管理",
    tone: "violet",
  },
];

export function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("business");
  const [password, setPassword] = useState("Business@123");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  if (user) {
    return <Navigate to={homePathForUser(user)} replace />;
  }

  const submit = async () => {
    if (!username.trim() || !password) {
      setError("请输入账号和密码");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const loggedIn = await login(username.trim(), password);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from && from !== "/login" ? from : homePathForUser(loggedIn), { replace: true });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "登录失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  };

  const useDemo = (account: (typeof DEMO_ACCOUNTS)[number]) => {
    setUsername(account.username);
    setPassword(account.password);
    setError("");
  };

  return (
    <div className="login-page">
      <section className="login-showcase">
        <div className="showcase-grid" />
        <div className="showcase-glow showcase-glow-one" />
        <div className="showcase-glow showcase-glow-two" />
        <div className="showcase-content">
          <div className="showcase-brand">
            <div className="showcase-logo"><AppstoreOutlined /></div>
            <div>
              <strong>绵绵聚道</strong>
              <span>MMDY WORKSPACE</span>
            </div>
          </div>

          <div className="showcase-copy">
            <Tag className="showcase-kicker">MMDY OA · 一期已上线合同管理</Tag>
            <h1>
              一个入口，
              <br />
              <em>连接全公司的协作。</em>
            </h1>
            <p>
              绵绵聚道统一承载公司内部协作与业务流转。一期先行上线合同管理，
              后续审批、行政等模块将按计划逐步接入。
            </p>
          </div>

          <div className="workflow-caption">一期能力 · 合同管理</div>
          <div className="workflow-visual">
            <div className="workflow-line" />
            {[
              ["01", "模板标准化", "法务统一维护合同模板与填写要求"],
              ["02", "业务在线填写", "按空白项动态生成表单与合同预览"],
              ["03", "法务审核", "集中查看待审合同，留痕反馈意见"],
              ["04", "归档下载", "审核通过后生成正式 PDF 合同文件"],
            ].map(([index, title, detail]) => (
              <div className="workflow-node" key={index}>
                <span className="workflow-index">{index}</span>
                <div>
                  <strong>{title}</strong>
                  <p>{detail}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="showcase-footer">
            <SafetyCertificateOutlined />
            <span>内部系统 · 角色权限隔离 · 全流程操作留痕</span>
            <span className="showcase-version">V1.0</span>
          </div>
        </div>
      </section>

      <section className="login-panel">
        <div className="login-card">
          <div className="login-eyebrow">
            <span className="live-dot" />
            企业内部访问
          </div>
          <h2>欢迎回来</h2>
          <p className="login-subtitle">登录绵绵聚道，进入你的工作空间。</p>

          {error && (
            <Alert
              type="error"
              showIcon
              message={error}
              className="login-alert"
              closable
              onClose={() => setError("")}
            />
          )}

          <div className="login-form">
            <label htmlFor="username">账号</label>
            <Input
              id="username"
              size="large"
              prefix={<UserOutlined />}
              placeholder="请输入账号"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              onPressEnter={submit}
              autoComplete="username"
            />
            <label htmlFor="password">密码</label>
            <Input.Password
              id="password"
              size="large"
              prefix={<LockOutlined />}
              placeholder="请输入密码"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              onPressEnter={submit}
              autoComplete="current-password"
            />
            <Button
              type="primary"
              size="large"
              block
              loading={loading}
              onClick={submit}
              className="login-submit"
            >
              登录绵绵聚道
              {!loading && <ArrowRightOutlined />}
            </Button>
          </div>

          <div className="demo-divider"><span>演示账号 · 点击快速填入</span></div>
          <div className="demo-account-list">
            {DEMO_ACCOUNTS.map((account) => (
              <button
                type="button"
                key={account.username}
                className={`demo-account demo-${account.tone} ${username === account.username ? "active" : ""}`}
                onClick={() => useDemo(account)}
              >
                <div className="demo-avatar">{account.name.slice(0, 1)}</div>
                <div className="demo-account-main">
                  <strong>{account.role}</strong>
                  <span>{account.description}</span>
                </div>
                <code>{account.username}</code>
              </button>
            ))}
          </div>

          <p className="login-footnote">
            当前为演示环境。正式部署前请移除演示账号，并接入企业统一身份认证（SSO / LDAP）。
          </p>
        </div>
      </section>
    </div>
  );
}
