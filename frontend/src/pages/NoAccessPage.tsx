import { Button, Result } from "antd";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export function NoAccessPage() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  return (
    <Result
      status="403"
      title="暂未开通访问权限"
      subTitle="请联系管理员在「系统管理 / 权限管理」中为你开通子模块权限。"
      extra={
        <Button
          onClick={async () => {
            await logout();
            navigate("/login", { replace: true });
          }}
        >
          退出登录
        </Button>
      }
    />
  );
}
