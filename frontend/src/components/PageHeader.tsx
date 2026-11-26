import type { ReactNode } from "react";
import { ArrowLeftOutlined } from "@ant-design/icons";
import { Button } from "antd";
import { useNavigate } from "react-router-dom";

interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  back?: boolean;
}

export function PageHeader({ eyebrow, title, description, actions, back }: PageHeaderProps) {
  const navigate = useNavigate();
  return (
    <div className="page-header">
      <div className="page-header-main">
        {back && (
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            className="back-button"
            onClick={() => navigate(-1)}
          >
            返回
          </Button>
        )}
        {eyebrow && <div className="page-eyebrow">{eyebrow}</div>}
        <h1 className="page-title">{title}</h1>
        {description && <div className="page-description">{description}</div>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}
