import {
  AuditOutlined,
  BellOutlined,
  DashboardOutlined,
  FileProtectOutlined,
  FileTextOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import { Avatar, Badge, Button, Dropdown, Layout, Menu, Tag, Tooltip } from "antd";
import type { MenuProps } from "antd";
import dayjs from "dayjs";
import { useEffect, useMemo, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import brandLogo from "../assets/brand-logo-transparent.png";
import { useAuth } from "../auth";
import { initials, ROLE_META } from "../utils";

const { Header, Sider, Content } = Layout;

const PAGE_NAMES: Record<string, string> = {
  "/dashboard": "工作台",
  "/contracts": "合同管理 / 合同列表",
  "/reviews": "合同管理 / 审核工作台",
  "/templates": "合同管理 / 合同模板",
  "/admin/permissions": "系统管理 / 权限管理",
};

export function AppLayout() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    if (window.innerWidth < 992) setCollapsed(true);
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
    if (location.pathname.startsWith("/contracts")) return "/contracts";
    return "/dashboard";
  }, [location.pathname]);

  const role = user ? ROLE_META[user.role] : null;

  const handleLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

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
            <Tooltip title="一期功能：合同模板、合同起草、法务审核与 PDF 下载">
              <Badge dot color="#5A6A46" offset={[-2, 4]}>
                <Button type="text" shape="circle" icon={<BellOutlined />} className="topbar-icon" />
              </Badge>
            </Tooltip>
            <Dropdown
              trigger={["click"]}
              menu={{
                items: [
                  {
                    key: "info",
                    disabled: true,
                    label: (
                      <div className="dropdown-user-card">
                        <strong>{user?.display_name}</strong>
                        <span>{user?.department} · {role?.label}</span>
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
                <Avatar size={34} className={`user-avatar role-${user?.role}`}>
                  {initials(user?.display_name)}
                </Avatar>
                <span>{role?.label}</span>
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
