import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  FormOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Checkbox,
  Input,
  Modal,
  Table,
  Tag,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { PageHeader } from "../components/PageHeader";
import type {
  PermissionKey,
  PermissionModule,
  PermissionRequestRecord,
} from "../types";
import { formatDateTime } from "../utils";

const STATUS_META: Record<
  PermissionRequestRecord["status"],
  { label: string; color: string }
> = {
  pending: { label: "待审批", color: "processing" },
  approved: { label: "已通过", color: "success" },
  rejected: { label: "已驳回", color: "error" },
};

export function PermissionRequestPage() {
  const { user } = useAuth();
  const [items, setItems] = useState<PermissionRequestRecord[]>([]);
  const [modules, setModules] = useState<PermissionModule[]>([]);
  const [canApprove, setCanApprove] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<PermissionKey[]>([]);
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [reviewing, setReviewing] = useState<{
    record: PermissionRequestRecord;
    decision: "approve" | "reject";
  } | null>(null);
  const [reviewComment, setReviewComment] = useState("");
  const [reviewSaving, setReviewSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const result = await api.permissionRequests();
      setItems(result.items);
      setModules(result.modules);
      setCanApprove(result.can_approve);
    } catch (caught) {
      message.error(caught instanceof ApiError ? caught.message : "权限申请加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const groups = useMemo(() => {
    const result: { name: string; modules: PermissionModule[] }[] = [];
    for (const module of modules) {
      const group = result.find((item) => item.name === module.group);
      if (group) group.modules.push(module);
      else result.push({ name: module.group, modules: [module] });
    }
    return result;
  }, [modules]);

  const modulesByKey = useMemo(
    () => new Map(modules.map((module) => [module.key, module])),
    [modules],
  );
  const granted = useMemo(() => new Set(user?.permissions || []), [user?.permissions]);

  const togglePermission = (key: PermissionKey) => {
    if (granted.has(key) || (key === "reviews" && user?.role !== "legal")) return;
    setSelected((current) =>
      current.includes(key) ? current.filter((item) => item !== key) : [...current, key],
    );
  };

  const toggleGroup = (groupModules: PermissionModule[], checked: boolean) => {
    const available = groupModules
      .map((module) => module.key)
      .filter(
        (key) =>
          !granted.has(key) && (key !== "reviews" || user?.role === "legal"),
      );
    setSelected((current) => {
      const rest = current.filter((key) => !available.includes(key));
      return checked ? [...rest, ...available] : rest;
    });
  };

  const submit = async () => {
    if (!selected.length) {
      message.warning("请至少选择一个需要开通的权限");
      return;
    }
    if (!reason.trim()) {
      message.warning("请填写开通事由");
      return;
    }
    setSubmitting(true);
    try {
      await api.createPermissionRequest({
        permissions: selected,
        reason: reason.trim(),
      });
      message.success("权限申请已提交，请等待系统管理员审批");
      setSelected([]);
      setReason("");
      await load();
    } catch (caught) {
      message.error(caught instanceof ApiError ? caught.message : "权限申请提交失败");
    } finally {
      setSubmitting(false);
    }
  };

  const submitReview = async () => {
    if (!reviewing) return;
    setReviewSaving(true);
    try {
      await api.reviewPermissionRequest(reviewing.record.id, {
        decision: reviewing.decision,
        comment: reviewComment.trim(),
      });
      message.success(reviewing.decision === "approve" ? "申请已通过并开通权限" : "申请已驳回");
      setReviewing(null);
      setReviewComment("");
      await load();
    } catch (caught) {
      message.error(caught instanceof ApiError ? caught.message : "审批失败");
    } finally {
      setReviewSaving(false);
    }
  };

  const columns: ColumnsType<PermissionRequestRecord> = [
    {
      title: "申请人",
      key: "applicant",
      width: 170,
      render: (_, record) => (
        <div>
          <strong>{record.display_name || record.username}</strong>
          <div className="muted-text">{record.username}</div>
        </div>
      ),
    },
    {
      title: "申请权限",
      key: "permissions",
      render: (_, record) => (
        <div className="permission-request-tags">
          {record.permissions.map((key) => (
            <Tag key={key} bordered={false}>
              {modulesByKey.get(key)?.label || key}
            </Tag>
          ))}
        </div>
      ),
    },
    {
      title: "开通事由",
      dataIndex: "reason",
      key: "reason",
      render: (value: string) => <span className="permission-request-reason">{value}</span>,
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      width: 100,
      render: (status: PermissionRequestRecord["status"]) => (
        <Tag color={STATUS_META[status].color}>{STATUS_META[status].label}</Tag>
      ),
    },
    {
      title: "审批信息",
      key: "review",
      width: 210,
      render: (_, record) =>
        record.status === "pending" ? (
          <span className="muted-text">等待管理员审批</span>
        ) : (
          <div className="permission-request-review">
            <span>{record.reviewer_name || "管理员"} · {formatDateTime(record.reviewed_at)}</span>
            {record.review_comment && <small>{record.review_comment}</small>}
          </div>
        ),
    },
    {
      title: "",
      key: "actions",
      width: 160,
      render: (_, record) =>
        canApprove && record.status === "pending" && record.oa_user_id !== user?.id ? (
          <div className="permission-request-actions">
            <Button
              type="link"
              size="small"
              icon={<CheckCircleOutlined />}
              onClick={() => {
                setReviewing({ record, decision: "approve" });
                setReviewComment("");
              }}
            >
              通过
            </Button>
            <Button
              type="link"
              size="small"
              danger
              icon={<CloseCircleOutlined />}
              onClick={() => {
                setReviewing({ record, decision: "reject" });
                setReviewComment("");
              }}
            >
              驳回
            </Button>
          </div>
        ) : null,
    },
  ];

  return (
    <div className="page-stack permission-request-page">
      <PageHeader
        eyebrow="PERMISSION REQUESTS"
        title="权限申请"
        description="提交需要开通的系统子模块并填写事由，由系统管理员审批后自动开通。"
      />

      <div className="permission-request-layout">
        <div className="panel permission-request-form">
          <div className="panel-head">
            <div>
              <span className="panel-eyebrow">NEW REQUEST</span>
              <h3>提交权限申请</h3>
            </div>
            <FormOutlined />
          </div>
          <Alert
            type="info"
            showIcon
            message="已开通的权限不可重复选择"
            description="请只勾选当前尚未开通、且因工作需要必须使用的子模块。"
          />
          <div className="permission-request-module-scroll">
            {groups.map((group) => {
            const availableKeys = group.modules
              .map((module) => module.key)
              .filter(
                (key) =>
                  !granted.has(key) &&
                  (key !== "reviews" || user?.role === "legal"),
              );
            const selectedCount = availableKeys.filter((key) => selected.includes(key)).length;
            const allSelected = availableKeys.length > 0 && selectedCount === availableKeys.length;
            const partiallySelected = selectedCount > 0 && !allSelected;
              return (
                <div className="permission-module-group" key={group.name}>
                <div className="permission-group-head">
                  <div className="permission-group-title">
                    <span className="permission-group-name">{group.name}</span>
                    <span className="permission-group-count">
                      可选 {availableKeys.length} 项
                    </span>
                  </div>
                  <Checkbox
                    checked={allSelected}
                    indeterminate={partiallySelected}
                    disabled={!availableKeys.length}
                    onChange={(event) => toggleGroup(group.modules, event.target.checked)}
                  >
                    全选
                  </Checkbox>
                </div>
                {group.modules.map((module) => {
                  const alreadyGranted = granted.has(module.key);
                  const reviewLocked =
                    module.key === "reviews" && user?.role !== "legal";
                  const checked = selected.includes(module.key);
                  return (
                    <label
                      key={module.key}
                      className={`permission-option ${checked ? "checked" : ""} ${alreadyGranted || reviewLocked ? "disabled" : ""}`}
                    >
                      <Checkbox
                        checked={alreadyGranted || checked}
                        disabled={alreadyGranted || reviewLocked}
                        onChange={() => togglePermission(module.key)}
                      />
                      <div>
                        <strong>{module.label}</strong>
                        <span>
                          {reviewLocked
                            ? "仅法务角色可申请此权限"
                            : alreadyGranted
                              ? "已开通"
                              : module.description}
                        </span>
                      </div>
                    </label>
                  );
                })}
                </div>
              );
            })}
          </div>
          <div className="permission-editor-section">
            <div className="permission-section-head">
              <strong>开通事由 <em>*</em></strong>
              <span>{reason.length}/1000</span>
            </div>
            <Input.TextArea
              rows={4}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              maxLength={1000}
              placeholder="请说明申请开通这些权限的具体工作场景和必要性"
            />
          </div>
          <Button
            type="primary"
            block
            size="large"
            loading={submitting}
            onClick={submit}
          >
            提交申请
          </Button>
        </div>

        <div className="panel permission-request-list">
          <div className="panel-head">
            <div>
              <span className="panel-eyebrow">REQUEST HISTORY</span>
              <h3>{canApprove ? "全部权限申请" : "我的申请记录"}</h3>
            </div>
            {canApprove && (
              <Tag color="gold" icon={<SafetyCertificateOutlined />}>
                管理员审批
              </Tag>
            )}
          </div>
          <Table
            rowKey="id"
            loading={loading}
            columns={columns}
            dataSource={items}
            pagination={{ pageSize: 10, showSizeChanger: false }}
            scroll={{ x: 980, y: "calc(100vh - 390px)" }}
            locale={{ emptyText: "暂无权限申请" }}
          />
        </div>
      </div>

      <Modal
        open={!!reviewing}
        title={reviewing?.decision === "approve" ? "确认通过权限申请？" : "驳回权限申请？"}
        okText={reviewing?.decision === "approve" ? "确认通过并开通" : "确认驳回"}
        cancelText="取消"
        okButtonProps={{ danger: reviewing?.decision === "reject" }}
        confirmLoading={reviewSaving}
        onOk={submitReview}
        onCancel={() => {
          if (reviewSaving) return;
          setReviewing(null);
          setReviewComment("");
        }}
      >
        {reviewing && (
          <div className="permission-review-modal">
            <p>
              <strong>{reviewing.record.display_name || reviewing.record.username}</strong>
              {" 申请开通："}
              {reviewing.record.permissions
                .map((key) => modulesByKey.get(key)?.label || key)
                .join("、")}
            </p>
            <p className="muted-text">事由：{reviewing.record.reason}</p>
            <Input.TextArea
              rows={3}
              value={reviewComment}
              onChange={(event) => setReviewComment(event.target.value)}
              maxLength={1000}
              placeholder="审批意见（选填）"
            />
          </div>
        )}
      </Modal>
    </div>
  );
}
