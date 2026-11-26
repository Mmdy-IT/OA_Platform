import {
  EditOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
  TeamOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { Alert, Button, Checkbox, Drawer, Input, Table, Tag, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api";
import { PageHeader } from "../components/PageHeader";
import type {
  PermissionKey,
  PermissionModule,
  Role,
  UserPermissionRecord,
} from "../types";
import { formatDateTime, initials, ROLE_META } from "../utils";

type RoleFilter = "all" | Role;

const ROLE_FILTERS: { key: RoleFilter; label: string }[] = [
  { key: "all", label: "全部人员" },
  { key: "admin", label: "管理员" },
  { key: "legal", label: "法务" },
  { key: "business", label: "业务" },
];

export function AdminPermissionsPage() {
  const [items, setItems] = useState<UserPermissionRecord[]>([]);
  const [modules, setModules] = useState<PermissionModule[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState<RoleFilter>("all");
  const [editing, setEditing] = useState<UserPermissionRecord | null>(null);
  const [draftPermissions, setDraftPermissions] = useState<PermissionKey[]>([]);
  const [draftUnionId, setDraftUnionId] = useState("");
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const result = await api.adminPermissions();
      setItems(result.items);
      setModules(result.modules);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "人员权限加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const modulesByKey = useMemo(() => {
    return Object.fromEntries(modules.map((item) => [item.key, item])) as Record<
      PermissionKey,
      PermissionModule
    >;
  }, [modules]);

  const groups = useMemo(() => {
    const result: { name: string; modules: PermissionModule[] }[] = [];
    for (const module of modules) {
      const group = result.find((item) => item.name === module.group);
      if (group) group.modules.push(module);
      else result.push({ name: module.group, modules: [module] });
    }
    return result;
  }, [modules]);

  const filtered = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return items.filter((item) => {
      if (roleFilter !== "all" && item.role !== roleFilter) return false;
      if (!keyword) return true;
      return [item.display_name, item.username, item.department, item.union_id]
        .join(" ")
        .toLowerCase()
        .includes(keyword);
    });
  }, [items, query, roleFilter]);

  const unionCount = items.filter((item) => item.union_id).length;
  const adminCount = items.filter((item) => item.role === "admin").length;
  const contractGranted = items.filter((item) =>
    item.permissions.some((key) => key === "contracts" || key === "reviews" || key === "templates"),
  ).length;

  const openEditor = (record: UserPermissionRecord) => {
    setEditing(record);
    setDraftPermissions(record.permissions);
    setDraftUnionId(record.union_id);
  };

  const closeEditor = () => {
    if (saving) return;
    setEditing(null);
  };

  const togglePermission = (key: PermissionKey) => {
    setDraftPermissions((current) =>
      current.includes(key) ? current.filter((item) => item !== key) : [...current, key],
    );
  };

  const toggleGroup = (modules: PermissionModule[], checked: boolean) => {
    const keys = modules.map((module) => module.key);
    setDraftPermissions((current) => {
      const rest = current.filter((key) => !keys.includes(key));
      return checked ? [...rest, ...keys] : rest;
    });
  };

  const save = async () => {
    if (!editing) return;
    setSaving(true);
    try {
      const updated = await api.updateUserPermission(editing.id, {
        permissions: draftPermissions,
        union_id: draftUnionId.trim(),
      });
      setItems((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setEditing(updated);
      setDraftPermissions(updated.permissions);
      setDraftUnionId(updated.union_id);
      message.success("权限已保存，用户刷新页面或重新登录后生效");
    } catch (caught) {
      message.error(caught instanceof ApiError ? caught.message : "权限保存失败");
    } finally {
      setSaving(false);
    }
  };

  const columns: ColumnsType<UserPermissionRecord> = [
    {
      title: "人员",
      key: "person",
      render: (_, record) => (
        <div className="permission-person">
          <span className="permission-avatar">{initials(record.display_name)}</span>
          <div>
            <strong>{record.display_name || record.username}</strong>
            <span>{record.username} · OA ID {record.oa_user_id ?? "-"}</span>
          </div>
        </div>
      ),
    },
    {
      title: "部门",
      dataIndex: "department",
      key: "department",
      render: (value: string) => value || "-",
    },
    {
      title: "岗位",
      dataIndex: "job_title",
      key: "job_title",
      render: (value: string) => value || "-",
    },
    {
      title: "角色",
      dataIndex: "role",
      key: "role",
      width: 110,
      render: (role: Role) => (
        <Tag bordered={false} className={`permission-role role-${role}`}>
          {ROLE_META[role]?.label || role}
        </Tag>
      ),
    },
    {
      title: "飞书 union_id",
      dataIndex: "union_id",
      key: "union_id",
      width: 190,
      render: (value: string) =>
        value ? <code className="permission-union-id">{value}</code> : <span className="muted-text">未绑定</span>,
    },
    {
      title: "已开通子模块",
      key: "permissions",
      render: (_, record) =>
        record.permissions.length ? (
          <div className="permission-tags">
            {record.permissions.map((key) => (
              <Tag key={key} color="blue" bordered={false}>
                {modulesByKey[key]?.label || key}
              </Tag>
            ))}
          </div>
        ) : (
          <Tag color="default" bordered={false}>未开通</Tag>
        ),
    },
    {
      title: "最近更新",
      dataIndex: "updated_at",
      key: "updated_at",
      width: 150,
      render: (value: string) => <span className="permission-updated">{formatDateTime(value)}</span>,
    },
    {
      title: "",
      key: "action",
      width: 92,
      render: (_, record) => (
        <Button type="text" icon={<EditOutlined />} onClick={() => openEditor(record)}>
          配置
        </Button>
      ),
    },
  ];

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="ACCESS CONTROL"
        title="人员权限管理"
        description="按人员配置可访问的子模块。权限保存在公司 mmdy_db 的 oa_user_permission 表中，后续接入飞书鉴权时通过 union_id 匹配人员。"
        actions={
          <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
            刷新
          </Button>
        }
      />

      <div className="permission-stats">
        <div className="permission-stat">
          <span className="permission-stat-icon blue"><TeamOutlined /></span>
          <div><span>人员总数</span><strong>{items.length}</strong></div>
        </div>
        <div className="permission-stat">
          <span className="permission-stat-icon teal"><UserOutlined /></span>
          <div><span>已绑定飞书</span><strong>{unionCount}</strong></div>
        </div>
        <div className="permission-stat">
          <span className="permission-stat-icon violet"><SafetyCertificateOutlined /></span>
          <div><span>开通合同模块</span><strong>{contractGranted}</strong></div>
        </div>
        <div className="permission-stat">
          <span className="permission-stat-icon amber"><SafetyCertificateOutlined /></span>
          <div><span>管理员</span><strong>{adminCount}</strong></div>
        </div>
      </div>

      {error && (
        <Alert
          type="error"
          showIcon
          message="人员权限表暂时不可用"
          description={error}
          className="permission-alert"
        />
      )}

      <div className="panel permission-panel">
        <div className="contracts-toolbar">
          <div className="filter-pills">
            {ROLE_FILTERS.map((item) => (
              <button
                type="button"
                key={item.key}
                className={roleFilter === item.key ? "active" : ""}
                onClick={() => setRoleFilter(item.key)}
              >
                {item.label} <span>{item.key === "all" ? items.length : items.filter((row) => row.role === item.key).length}</span>
              </button>
            ))}
          </div>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="搜索姓名、账号、部门或 union_id"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="contract-search"
          />
        </div>
        <Table<UserPermissionRecord>
          rowKey="id"
          columns={columns}
          dataSource={filtered}
          loading={loading}
          pagination={false}
          locale={{ emptyText: error ? "权限数据加载失败" : "没有匹配的人员" }}
        />
      </div>

      <Drawer
        open={!!editing}
        onClose={closeEditor}
        width={560}
        title="配置人员权限"
        className="permission-drawer"
      >
        {editing && (
          <div className="permission-editor">
            <div className="permission-editor-profile">
              <span className="permission-avatar large">{initials(editing.display_name)}</span>
              <div>
                <strong>{editing.display_name || editing.username}</strong>
                <span>{editing.username} · {editing.department || "未设置部门"}</span>
                <Tag bordered={false} className={`permission-role role-${editing.role}`}>
                  {ROLE_META[editing.role]?.label || editing.role}
                </Tag>
              </div>
            </div>

            <div className="permission-editor-section">
              <div className="permission-section-head">
                <strong>飞书 union_id</strong>
                <span>用于后续飞书鉴权登录匹配</span>
              </div>
              <Input
                allowClear
                value={draftUnionId}
                onChange={(event) => setDraftUnionId(event.target.value)}
                placeholder="例如：on_xxxxxxxxxxxxxxxx"
                maxLength={64}
              />
              <p className="muted-text">可暂时留空；绑定后请确保同一 union_id 不重复。</p>
            </div>

            <div className="permission-editor-section">
              <div className="permission-section-head">
                <strong>子模块权限</strong>
                <span>已勾选 {draftPermissions.length} / {modules.length} 项</span>
              </div>
              {groups.map((group) => {
                const groupKeys = group.modules.map((module) => module.key);
                const selectedCount = groupKeys.filter((key) => draftPermissions.includes(key)).length;
                const allSelected = groupKeys.length > 0 && selectedCount === groupKeys.length;
                const partiallySelected = selectedCount > 0 && !allSelected;
                return (
                  <div className="permission-module-group" key={group.name}>
                    <div className="permission-group-head">
                      <div className="permission-group-title">
                        <span className="permission-group-name">{group.name}</span>
                        <span className="permission-group-count">已选 {selectedCount}/{groupKeys.length}</span>
                      </div>
                      <Checkbox
                        checked={allSelected}
                        indeterminate={partiallySelected}
                        onChange={(event) => toggleGroup(group.modules, event.target.checked)}
                      >
                        全选
                      </Checkbox>
                    </div>
                    {group.modules.map((module) => {
                      const checked = draftPermissions.includes(module.key);
                      return (
                        <label
                          key={module.key}
                          className={`permission-option ${checked ? "checked" : ""}`}
                        >
                          <Checkbox
                            checked={checked}
                            onChange={() => togglePermission(module.key)}
                          />
                          <div>
                            <strong>{module.label}</strong>
                            <span>{module.description}</span>
                          </div>
                        </label>
                      );
                    })}
                  </div>
                );
              })}
            </div>

            <Alert
              type="info"
              showIcon
              message="权限变更后，用户刷新页面或重新登录即可生效。"
              description="管理员账号始终可以进入当前权限管理页面。"
            />

            <div className="permission-editor-actions">
              <Button onClick={closeEditor} disabled={saving}>取消</Button>
              <Button type="primary" onClick={save} loading={saving}>保存权限</Button>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
