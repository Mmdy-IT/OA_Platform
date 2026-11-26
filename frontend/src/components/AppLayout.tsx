import {
  AuditOutlined,
  BellOutlined,
  DashboardOutlined,
  FileProtectOutlined,
  FileTextOutlined,
  LinkOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  TeamOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import { Avatar, Badge, Button, Dropdown, Layout, Menu, Popover, Tag } from "antd";
import type { MenuProps } from "antd";
import dayjs from "dayjs";
import { useEffect, useMemo, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import brandLogo from "../assets/brand-logo-transparent.png";
import { api } from "../api";
import { useAuth } from "../auth";
import type { NotificationItem } from "../types";
import { formatDateTime, initials } from "../utils";

const { Header, Sider, Content } = Layout;

const PAGE_NAMES: Record<string, string> = {
  "/dashboard": "工作台",
  "/contracts": "合同管理 / 合同列表",
  "/parties": "合同管理 / 乙方主体信息",
  "/reviews": "合同管理 / 审核工作台",
  "/templates": "合同管理 / 合同模板",
  "/bundle-rules": "合同管理 / 合同包规则",
  "/admin/permissions": "系统管理 / 权限管理",
};

export function AppLayout() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(false);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [notificationOpen, setNotificationOpen] = useState(false);
  const displayNameParts = (user?.display_name || "")
    .split("·")
    .map((part) => part.trim())
    .filter(Boolean);
  const displayName = displayNameParts[0] || user?.username || "OA 用户";
  const jobTitle = user?.job_title || displayNameParts[1] || "岗位未设置";

  useEffect(() => {
    if (window.innerWidth < 992) setCollapsed(true);
  }, []);

  useEffect(() => {
    let active = true;
    const load = () => {
      api
        .notifications()
        .then((result) => {
          if (active) setNotifications(result.items);
        })
        .catch(() => {
          if (active) setNotifications([]);
        });
    };
    void load();
    const timer = window.setInterval(load, 60000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const currentPage = useMemo(() => {
    const found = Object.keys(PAGE_NAMES).find((path) => location.pathname.startsWith(path));
    return found ? PAGE_NAMES[found] : "绵绵聚道";
  }, [location.pathname]);

  const menuItems = useMemo<MenuProps["items"]>(() => {
    const granted = new Set(user?.permissions || []);
    const items: NonNullable<MenuProps["items"]> = [];
    if (granted.has("dashboard")) {
      items.push({
        key: "/dashboard",
        icon: <DashboardOutlined />,
        label: "工作台",
      });
    }

    const contractChildren: NonNullable<MenuProps["items"]> = [];
    if (granted.has("contracts")) {
      contractChildren.push({
        key: "/contracts",
        icon: <UnorderedListOutlined />,
        label: "合同列表",
      });
    }
    if (granted.has("parties")) {
      contractChildren.push({
        key: "/parties",
        icon: <TeamOutlined />,
        label: "乙方主体信息",
      });
    }
    if (granted.has("reviews")) {
      contractChildren.push({
        key: "/reviews",
        icon: <AuditOutlined />,
        label: "审核工作台",
      });
    }
    if (granted.has("templates")) {
      contractChildren.push({
        key: "/templates",
        icon: <FileProtectOutlined />,
        label: "合同模板",
      });
      contractChildren.push({
        key: "/bundle-rules",
        icon: <LinkOutlined />,
        label: "合同包规则",
      });
    }
    if (contractChildren.length) {
      items.push({
        key: "contract-management",
        icon: <FileTextOutlined />,
        label: "合同管理",
        children: contractChildren,
      });
    }

    if (user?.role === "admin") {
      items.push({
        key: "system-management",
        icon: <SettingOutlined />,
        label: "系统管理",
        children: [
          {
            key: "/admin/permissions",
            icon: <SafetyCertificateOutlined />,
            label: "权限管理",
          },
        ],
      });
    }
    return items;
  }, [user?.permissions, user?.role]);

  const selectedKey = useMemo(() => {
    if (location.pathname.startsWith("/admin/permissions")) return "/admin/permissions";
    if (location.pathname.startsWith("/reviews")) return "/reviews";
    if (location.pathname.startsWith("/templates")) return "/templates";
    if (location.pathname.startsWith("/bundle-rules")) return "/bundle-rules";
    if (location.pathname.startsWith("/contracts")) return "/contracts";
    if (location.pathname.startsWith("/parties")) return "/parties";
    return "/dashboard";
  }, [location.pathname]);

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  const refreshNotifications = () => {
    api
      .notifications()
      .then((result) => setNotifications(result.items))
      .catch(() => undefined);
  };

  const notificationPanel = (
    <div className="notifications-panel">
      <div className="notifications-head">
        <strong>消息通知</strong>
        <span>{notifications.length} 条</span>
      </div>
      {notifications.length ? (
        <div className="notification-list">
          {notifications.map((item) => (
            <button
              type="button"
              className="notification-item"
              key={item.id}
              onClick={() => {
                setNotificationOpen(false);
                navigate(`/contracts/${item.contract_id}`);
              }}
            >
              <span className={`notification-dot notification-${item.kind}`} />
              <span className="notification-copy">
                <strong>{item.title}</strong>
                <span>{item.description}</span>
                <small>{formatDateTime(item.created_at)}</small>
              </span>
            </button>
          ))}
        </div>
      ) : (
        <div className="notifications-empty">暂无新消息</div>
      )}
    </div>
  );

  return (
    <Layout className="app-layout">
      <Sider
        width={252}
        collapsedWidth={0}
        trigger={null}
        collapsible
        collapsed={collapsed}
        onBreakpoint={(broken) => setCollapsed(broken)}
        className="app-sider"
      >
        <div className="sider-inner">
          <div className="app-brand" onClick={() => navigate("/dashboard")}>
            <div className="brand-mark">
              <img src={brandLogo} alt="绵绵的羊" className="brand-logo" />
            </div>
            <div>
              <div className="brand-title">绵绵聚道</div>
              <div className="brand-subtitle">MMDY WORKSPACE</div>
            </div>
          </div>

          <Menu
            theme="light"
            mode="inline"
            selectedKeys={[selectedKey]}
            defaultOpenKeys={["contract-management", "system-management"]}
            items={menuItems}
            className="app-menu"
            onClick={({ key }) => {
              navigate(key);
              if (window.innerWidth < 992) setCollapsed(true);
            }}
          />

          <div className="sider-spacer" />
        </div>
      </Sider>

      <Layout className="main-layout">
        <Header className="app-topbar">
          <div className="topbar-left">
            <Button
              type="text"
              className="collapse-button"
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed((value) => !value)}
            />
            <div className="topbar-breadcrumb">
              <span>绵绵聚道</span>
              <span className="crumb-divider">/</span>
              <strong>{currentPage}</strong>
            </div>
          </div>
          <div className="topbar-right">
            <div className="topbar-date">{dayjs().format("YYYY年M月D日")}</div>
            <Tag className="phase-tag">内部系统</Tag>
            <Popover
              trigger="click"
              placement="bottomRight"
              open={notificationOpen}
              onOpenChange={(open) => {
                setNotificationOpen(open);
                if (open) refreshNotifications();
              }}
              content={notificationPanel}
              classNames={{ root: "notifications-popover" }}
            >
              <Badge count={notifications.length} size="small" offset={[-2, 4]}>
                <Button type="text" shape="circle" icon={<BellOutlined />} className="topbar-icon" />
              </Badge>
            </Popover>
            <Dropdown
              trigger={["click"]}
              menu={{
                items: [
                  {
                    key: "info",
                    disabled: true,
                    label: (
                      <div className="dropdown-user-card">
                        <strong>{displayName}</strong>
                        <span>
                          {[user?.department, jobTitle].filter(Boolean).join(" · ")}
                        </span>
                      </div>
                    ),
                  },
                  { type: "divider" },
                  {
                    key: "logout",
                    icon: <LogoutOutlined />,
                    label: "退出登录",
                    onClick: handleLogout,
                  },
                ],
              }}
            >
              <button type="button" className="topbar-user">
                <Avatar
                  size={38}
                  src={user?.avatar_url || undefined}
                  className={`user-avatar role-${user?.role}`}
                >
                  {initials(user?.display_name)}
                </Avatar>
                <span>{`${displayName} | ${jobTitle}`}</span>
              </button>
            </Dropdown>
          </div>
        </Header>
        <Content className="app-content">
          <div className="content-container">
            <Outlet />
          </div>
        </Content>
      </Layout>
    </Layout>
  );
}
