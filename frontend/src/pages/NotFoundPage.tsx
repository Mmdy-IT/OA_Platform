import { Button, Result } from "antd";
import { useNavigate } from "react-router-dom";

export function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <Result
      status="404"
      title="页面不存在"
      subTitle="你访问的页面可能已移动或被删除。"
      extra={<Button type="primary" onClick={() => navigate("/dashboard")}>返回工作台</Button>}
    />
  );
}
