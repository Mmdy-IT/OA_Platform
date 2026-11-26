import { LoginOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { Alert, Button, Spin } from "antd";
import { useEffect, useState } from "react";
import { Navigate, useLocation, useSearchParams } from "react-router-dom";
import brandLogo from "../assets/brand-logo-transparent.png";
import { api } from "../api";
import { homePathForUser, useAuth } from "../auth";

const FEISHU_ERRORS: Record<string, string> = {
  cancelled: "已取消飞书授权",
  state_invalid: "飞书登录安全校验失败，请重新发起登录",
  missing_union_id: "飞书未返回 union_id，请检查飞书应用权限",
  unbound: "飞书账号尚未绑定 OA 人员，请联系管理员",
  auth_failed: "飞书授权失败，请稍后重试",
  permission_unavailable: "人员权限服务暂不可用，请稍后重试",
};

export function LoginPage() {
  const { user } = useAuth();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const queryError = FEISHU_ERRORS[searchParams.get("feishu_error") || ""] || "";
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [error, setError] = useState(queryError);

  const requestedPath = (location.state as { from?: string } | null)?.from;
  const next = requestedPath && requestedPath !== "/login" ? requestedPath : "/dashboard";
  const feishuLoginUrl = `/api/auth/feishu/login?next=${encodeURIComponent(next)}`;

  useEffect(() => {
    let active = true;
    api
      .feishuConfig()
      .then((result) => {
        if (!active) return;
        setEnabled(result.enabled);
        if (result.enabled && !queryError) {
          window.location.replace(feishuLoginUrl);
        } else if (!result.enabled) {
          setError("飞书登录未启用，请联系管理员配置应用。");
        }
      })
      .catch(() => {
        if (!active) return;
        setEnabled(false);
        setError("无法获取飞书登录配置，请稍后重试。");
      });
    return () => {
      active = false;
    };
  }, [feishuLoginUrl, queryError]);

  if (user) {
    return <Navigate to={homePathForUser(user)} replace />;
  }

  return (
    <div className="feishu-login-page">
      <div className="feishu-login-card">
        <img src={brandLogo} alt="绵绵聚道" className="feishu-login-logo" />
        <div className="login-eyebrow">
          <span className="live-dot" />
          企业统一身份认证
        </div>
        <h1>绵绵聚道</h1>
        <p>仅支持飞书账号登录</p>

        {error ? (
          <Alert
            type="error"
            showIcon
            message={error}
            className="feishu-login-alert"
          />
        ) : (
          <div className="feishu-login-loading">
            <Spin size="small" />
            <span>正在跳转飞书登录…</span>
          </div>
        )}

        <Button
          type="primary"
          size="large"
          block
          icon={<LoginOutlined />}
          disabled={enabled === false}
          onClick={() => window.location.assign(feishuLoginUrl)}
          className="feishu-login-retry"
        >
          发起飞书登录
        </Button>

        <div className="feishu-login-foot">
          <SafetyCertificateOutlined />
          <span>内部系统 · 飞书身份认证 · 权限由管理员统一配置</span>
        </div>
      </div>
    </div>
  );
}
