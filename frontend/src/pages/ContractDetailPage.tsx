import {
  AuditOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  CopyOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  FileDoneOutlined,
  FileTextOutlined,
  SendOutlined,
  UndoOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { Alert, Button, Descriptions, Modal, Result, Skeleton, Tag, Timeline, message } from "antd";
import TextArea from "antd/es/input/TextArea";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { hasPermission, homePathForUser, useAuth } from "../auth";
import { ContractPaper } from "../components/ContractPaper";
import { ContractAttachments } from "../components/ContractAttachments";
import { PageHeader } from "../components/PageHeader";
import { StatusTag } from "../components/StatusTag";
import type { Contract } from "../types";
import {
  EVENT_META,
  formatDateTime,
  STATUS_META,
} from "../utils";

const REVIEW_SHORTCUTS = [
  "请补充并明确付款节点与付款条件。",
  "合同金额大小写不一致，请核对后修改。",
  "服务范围/交付物描述不够具体，请补充量化标准。",
  "请调整保密期限，原则上不少于三年。",
];

export function ContractDetailPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [contract, setContract] = useState<Contract | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [permissionDenied, setPermissionDenied] = useState(false);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [decision, setDecision] = useState<"approve" | "reject">("approve");
  const [comment, setComment] = useState("");

  const load = async () => {
    try {
      const result = await api.contract(id || "");
      setContract(result);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 403) setPermissionDenied(true);
      else setError(caught instanceof ApiError ? caught.message : "合同加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setLoading(true);
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const isOwner = !!contract && contract.creator_id === user?.id;
  const isReviewer = hasPermission(user, "reviews");
  const canEdit = hasPermission(user, "contracts");
  const fallbackPath = homePathForUser(user);
  const canReview =
    !!contract &&
    isReviewer &&
    contract.status === "pending" &&
    contract.creator_id !== user?.id;
  const isOwnPendingReview =
    !!contract &&
    isReviewer &&
    contract.status === "pending" &&
    contract.creator_id === user?.id;

  const events = useMemo(() => [...(contract?.events || [])].reverse(), [contract?.events]);

  if (loading) {
    return (
      <div className="page-stack">
        <Skeleton active paragraph={{ rows: 3 }} />
        <div className="detail-loading-grid">
          <div className="panel"><Skeleton active paragraph={{ rows: 16 }} /></div>
          <div className="panel"><Skeleton active paragraph={{ rows: 8 }} /></div>
        </div>
      </div>
    );
  }

  if (permissionDenied) {
    return <Result status="403" title="无权查看此合同" extra={<Button onClick={() => navigate(fallbackPath)}>返回工作区</Button>} />;
  }

  if (error || !contract) {
    return <Result status="error" title="合同加载失败" subTitle={error} extra={<Button onClick={() => navigate(fallbackPath)}>返回工作区</Button>} />;
  }

  const statusMeta = STATUS_META[contract.status];

  const runAction = async (
    name: string,
    request: () => Promise<Contract>,
    success: string,
  ) => {
    setActionBusy(name);
    try {
      const updated = await request();
      setContract(updated);
      message.success(success);
    } catch (caught) {
      message.error(caught instanceof ApiError ? caught.message : "操作失败，请稍后重试");
    } finally {
      setActionBusy(null);
    }
  };

  const downloadPdf = async () => {
    setActionBusy("download");
    try {
      await api.downloadContract(contract);
      message.success("PDF 合同已开始下载");
    } catch (caught) {
      message.error(caught instanceof ApiError ? caught.message : "PDF 下载失败");
    } finally {
      setActionBusy(null);
    }
  };

  const submit = () => {
    Modal.confirm({
      title: "提交法务审核？",
      icon: <SendOutlined style={{ color: "#5A6A46" }} />,
      content: "提交后合同内容将被锁定，审核期间不可修改。",
      okText: "确认提交",
      cancelText: "取消",
      onOk: async () => {
        try {
          const ensured = await api.ensureBundleCompanions(contract.id);
          if (ensured.next_contract_id) {
            const nextId = ensured.next_contract_id;
            message.warning("主合同已保存，请先填写通用合同模板");
            Modal.info({
              title: "请先填写通用合同模板",
              content:
                "该合同属于合同包，请先填写并保存通用合同模板，再保存或提交主合同。",
              okText: "去填写通用合同",
              onOk: () => navigate(`/contracts/${nextId}/edit`),
            });
            return;
          }
        } catch (caught) {
          message.error(caught instanceof ApiError ? caught.message : "操作失败，请稍后重试");
          return;
        }
        await runAction("submit", () => api.submitContract(contract.id), "合同已提交法务审核");
      },
    });
  };

  const withdraw = () => {
    Modal.confirm({
      title: "撤回审核？",
      icon: <UndoOutlined style={{ color: "#c47b0a" }} />,
      content: "撤回后合同将回到草稿状态，你可以继续修改并重新提交。",
      okText: "确认撤回",
      cancelText: "取消",
      onOk: () =>
        runAction("withdraw", () => api.withdrawContract(contract.id), "已撤回，合同回到草稿状态"),
    });
  };

  const remove = () => {
    Modal.confirm({
      title: contract.bundle ? "删除合同包内全部文件？" : "删除这份合同？",
      icon: <ExclamationCircleOutlined style={{ color: "#d64545" }} />,
      content: contract.bundle
        ? "该合同属于合同包，将同时删除合同包内的两个文件（主合同与通用合同），是否确认删除？"
        : "删除后合同及流转记录将无法恢复，此操作不可撤销。",
      okText: "确认删除",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: async () => {
        setActionBusy("delete");
        try {
          await api.deleteContract(contract.id);
          message.success("合同已删除");
          navigate(fallbackPath, { replace: true });
        } catch (caught) {
          message.error(caught instanceof ApiError ? caught.message : "删除失败");
        } finally {
          setActionBusy(null);
        }
      },
    });
  };

  const openReview = (nextDecision: "approve" | "reject") => {
    setDecision(nextDecision);
    setComment(nextDecision === "reject" ? contract.review_comment || "" : "");
    setReviewOpen(true);
  };

  const submitReview = async () => {
    if (decision === "reject" && !comment.trim()) {
      message.warning("驳回时请填写审核意见");
      return;
    }
    setActionBusy("review");
    try {
      const updated = await api.reviewContract(contract.id, { decision, comment: comment.trim() });
      setContract(updated);
      setReviewOpen(false);
      message.success(decision === "approve" ? "合同审核通过，已开放 PDF 下载" : "合同已驳回给业务修改");
    } catch (caught) {
      message.error(caught instanceof ApiError ? caught.message : "审核提交失败");
    } finally {
      setActionBusy(null);
    }
  };

  const copyNumber = async () => {
    try {
      await navigator.clipboard.writeText(contract.contract_no);
      message.success("合同编号已复制");
    } catch {
      message.error("复制失败，请手动选择编号");
    }
  };

  const showOwnerDraftActions =
    canEdit && isOwner && (contract.status === "draft" || contract.status === "rejected");

  return (
    <div className="page-stack detail-page">
      <PageHeader
        eyebrow={
          contract.template_category === "通用类" && contract.bundle_id
            ? "CONTRACT · 配套通用合同"
            : `CONTRACT · ${contract.contract_no}`
        }
        title={contract.title}
        description={
          <span className="detail-subtitle">
            <StatusTag status={contract.status} />
            <span>{contract.template_name} · {contract.template_version}</span>
            <span>发起人 {contract.creator_name}</span>
          </span>
        }
        back
        actions={
          <div className="detail-header-actions">
            {showOwnerDraftActions && (
              <>
                <Button icon={<EditOutlined />} onClick={() => navigate(`/contracts/${contract.id}/edit`)}>修改</Button>
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  loading={actionBusy === "submit"}
                  onClick={submit}
                >
                  提交审核
                </Button>
              </>
            )}
            {canEdit && isOwner && contract.status === "pending" && (
              <Button loading={actionBusy === "withdraw"} onClick={withdraw}>撤回审核</Button>
            )}
            {contract.status === "approved" && (
              <Button
                type="primary"
                icon={<DownloadOutlined />}
                loading={actionBusy === "download"}
                onClick={downloadPdf}
              >
                下载 PDF
              </Button>
            )}
            {canReview && (
              <>
                <Button danger onClick={() => openReview("reject")}>驳回</Button>
                <Button type="primary" icon={<CheckCircleOutlined />} onClick={() => openReview("approve")}>审核通过</Button>
              </>
            )}
          </div>
        }
      />

      <div className={`detail-banner banner-${statusMeta.tone}`}>
        <div className="detail-banner-icon">
          {contract.status === "approved" ? <FileDoneOutlined /> : contract.status === "pending" ? <ClockCircleOutlined /> : contract.status === "rejected" ? <CloseCircleOutlined /> : <FileTextOutlined />}
        </div>
        <div className="detail-banner-copy">
          <strong>{statusMeta.label} · {statusMeta.description}</strong>
          {contract.status === "pending" && (
            <span>已于 {formatDateTime(contract.submitted_at)} 提交，等待法务审核。</span>
          )}
          {contract.status === "approved" && (
            <span>{contract.reviewer_name} 于 {formatDateTime(contract.reviewed_at)} 完成审核，正式 PDF 已可下载。</span>
          )}
          {contract.status === "rejected" && (
            <span>审核意见：{contract.review_comment || "请根据法务意见修改后重新提交。"}</span>
          )}
          {contract.status === "draft" && <span>合同尚未提交，完善内容后可提交法务审核。</span>}
        </div>
        {contract.status === "approved" && (
          <Button icon={<DownloadOutlined />} loading={actionBusy === "download"} onClick={downloadPdf}>
            下载正式文件
          </Button>
        )}
      </div>

      {isOwnPendingReview && (
        <Alert
          type="info"
          showIcon
          message="该合同由你发起，不能由本人审核"
          description="系统要求发起人与审核人分离。请由其他具备审核权限的法务人员通过审核工作台处理。"
        />
      )}

      <div className="detail-layout">
        <div className="detail-document-column">
          <div className="document-stage-toolbar">
            <div>
              <span className="panel-eyebrow">CONTRACT DOCUMENT</span>
              <h3>合同正文</h3>
            </div>
            <div className="document-toolbar-meta">
              <span>共 {contract.fields_schema.length} 个填写项</span>
              {contract.status === "approved" && <Tag color="success" bordered={false}>已审核</Tag>}
            </div>
          </div>
          <div className="document-stage">
            <ContractPaper
              title={contract.title}
              content={contract.template_content}
              values={contract.field_values}
              fields={contract.fields_schema}
              tableAdjustments={contract.table_adjustments}
              contractNo={contract.contract_no}
              hideContractNumber={
                contract.template_category === "通用类" && !!contract.bundle_id
              }
              templateName={`${contract.template_name} · ${contract.template_version}`}
              highlight={false}
            />
          </div>
        </div>

        <aside className="detail-sidebar">
          {contract.bundle && (
            <div className="panel bundle-panel">
              <div className="bundle-panel-head">
                <div>
                  <span className="panel-eyebrow">CONTRACT BUNDLE</span>
                  <h3>合同包 · {contract.bundle.bundle_no}</h3>
                </div>
                <Tag color={contract.bundle.all_approved ? "success" : "processing"} bordered={false}>
                  {contract.bundle.all_approved ? "已全部通过" : "关联合同"}
                </Tag>
              </div>
              <p>同包合同需要全部审核通过后才可下载 PDF。</p>
              <div className="bundle-member-list">
                {contract.bundle.members.map((member) => (
                  <button
                    type="button"
                    className={`bundle-member ${member.id === contract.id ? "current" : ""}`}
                    key={member.id}
                    onClick={() => navigate(`/contracts/${member.id}`)}
                  >
                    <span>
                      <strong>{member.title}</strong>
                      <small>
                        {member.contract_no ? `${member.contract_no} · ` : ""}
                        {member.template_name}
                      </small>
                    </span>
                    <StatusTag status={member.status} />
                  </button>
                ))}
              </div>
            </div>
          )}

          {canReview && (
            <div className="panel review-action-panel">
              <div className="review-action-head">
                <div className="review-action-icon"><AuditOutlined /></div>
                <div>
                  <span className="panel-eyebrow">REVIEW TASK</span>
                  <h3>等待法务审核</h3>
                </div>
              </div>
              <p>请核对合同主体、金额、交付/服务范围及违约条款。审核通过后系统将开放正式 PDF 下载。</p>
              <div className="review-action-buttons">
                <Button danger block onClick={() => openReview("reject")}>驳回修改</Button>
                <Button type="primary" block icon={<CheckCircleOutlined />} onClick={() => openReview("approve")}>审核通过</Button>
              </div>
            </div>
          )}

          {contract.status === "approved" && (
            <div className="panel approved-download-panel">
              <div className="approved-seal"><CheckCircleOutlined /></div>
              <h3>法务审核已通过</h3>
              <p>合同内容已锁定，可下载带审核信息的正式 PDF 文件。</p>
              <Button type="primary" block icon={<DownloadOutlined />} loading={actionBusy === "download"} onClick={downloadPdf}>
                下载 PDF 合同
              </Button>
            </div>
          )}

          {isOwnPendingReview && (
            <div className="panel review-action-panel review-action-panel-muted">
              <div className="review-action-head">
                <div className="review-action-icon"><AuditOutlined /></div>
                <div>
                  <span className="panel-eyebrow">REVIEW TASK</span>
                  <h3>等待其他法务审核</h3>
                </div>
              </div>
              <p>本人发起或参与的合同不能由本人审批，请等待其他法务人员处理。</p>
            </div>
          )}

          {showOwnerDraftActions && (
            <div className="panel next-step-panel">
              <div className="next-step-icon"><EditOutlined /></div>
              <h3>{contract.status === "rejected" ? "根据意见修改合同" : "完善合同信息"}</h3>
              <p>{contract.status === "rejected" ? "请阅读法务驳回意见，调整对应空白项后重新提交。" : "合同尚未提交，可以继续修改或提交法务审核。"}</p>
              <Button block icon={<EditOutlined />} onClick={() => navigate(`/contracts/${contract.id}/edit`)}>修改合同</Button>
              <Button block type="primary" icon={<SendOutlined />} loading={actionBusy === "submit"} onClick={submit} className="mt-8">提交审核</Button>
              <Button block danger type="text" icon={<DeleteOutlined />} loading={actionBusy === "delete"} onClick={remove} className="mt-8">删除合同</Button>
            </div>
          )}

          <div className="panel info-panel">
            <div className="panel-head">
              <div><span className="panel-eyebrow">CONTRACT INFO</span><h3>合同信息</h3></div>
              {contract.contract_no && (
                <Button type="text" size="small" icon={<CopyOutlined />} onClick={copyNumber} />
              )}
            </div>
            <Descriptions column={1} size="small" className="info-descriptions" colon={false}>
              {contract.contract_no && (
                <Descriptions.Item label="合同编号">{contract.contract_no}</Descriptions.Item>
              )}
              <Descriptions.Item label="合同编码">{contract.contract_code}</Descriptions.Item>
              <Descriptions.Item label="当前状态"><StatusTag status={contract.status} /></Descriptions.Item>
              <Descriptions.Item label="合同模板">{contract.template_name}</Descriptions.Item>
              <Descriptions.Item label="模板版本">{contract.template_version}</Descriptions.Item>
              <Descriptions.Item label="业务经办">{contract.creator_name}</Descriptions.Item>
              <Descriptions.Item label="创建时间">{formatDateTime(contract.created_at)}</Descriptions.Item>
              <Descriptions.Item label="提交时间">{formatDateTime(contract.submitted_at)}</Descriptions.Item>
              <Descriptions.Item label="法务审核">{contract.reviewer_name || "待分配"}</Descriptions.Item>
              <Descriptions.Item label="审核时间">{formatDateTime(contract.reviewed_at)}</Descriptions.Item>
            </Descriptions>
          </div>

          <div className="panel">
            <ContractAttachments
              contractId={contract.id}
              initialAttachments={contract.attachments || []}
            />
          </div>

          <div className="panel timeline-panel">
            <div className="panel-head">
              <div><span className="panel-eyebrow">AUDIT TRAIL</span><h3>流转记录</h3></div>
            </div>
            <Timeline
              className="contract-timeline"
              items={events.map((event) => {
                const meta = EVENT_META[event.action] || { label: event.action, tone: "slate" };
                return {
                  dot: <span className={`timeline-dot tone-${meta.tone}`} />,
                  children: (
                    <div className="timeline-item">
                      <div className="timeline-item-head">
                        <strong>{meta.label}</strong>
                        <span>{formatDateTime(event.created_at)}</span>
                      </div>
                      <div className="timeline-actor"><UserOutlined /> {event.actor_name}</div>
                      {event.comment && <p>{event.comment}</p>}
                    </div>
                  ),
                };
              })}
            />
            {!events.length && <div className="muted-text">暂无流转记录</div>}
          </div>
        </aside>
      </div>

      <Modal
        open={reviewOpen}
        onCancel={() => setReviewOpen(false)}
        onOk={submitReview}
        confirmLoading={actionBusy === "review"}
        okText={decision === "approve" ? "确认审核通过" : "确认驳回"}
        cancelText="取消"
        okButtonProps={{ danger: decision === "reject" }}
        width={620}
        title={
          <div className="review-modal-title">
            <span className={`review-modal-icon ${decision}`}>
              {decision === "approve" ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
            </span>
            <div>
              <strong>{decision === "approve" ? "审核通过" : "驳回修改"}</strong>
              <span>{contract.contract_no} · {contract.title}</span>
            </div>
          </div>
        }
      >
        <div className="review-decision-toggle">
          <button
            type="button"
            className={decision === "approve" ? "active approve" : ""}
            onClick={() => { setDecision("approve"); setComment(""); }}
          >
            <CheckCircleOutlined />
            <div><strong>审核通过</strong><span>内容无误，开放 PDF 下载</span></div>
          </button>
          <button
            type="button"
            className={decision === "reject" ? "active reject" : ""}
            onClick={() => setDecision("reject")}
          >
            <CloseCircleOutlined />
            <div><strong>驳回修改</strong><span>退回业务人员补充调整</span></div>
          </button>
        </div>

        {decision === "reject" && (
          <div className="review-shortcuts">
            <span>常用意见</span>
            <div>
              {REVIEW_SHORTCUTS.map((item) => (
                <button type="button" key={item} onClick={() => setComment(item)}>{item}</button>
              ))}
            </div>
          </div>
        )}

        <div className="review-comment-field">
          <label>
            {decision === "approve" ? "审核意见（选填）" : "驳回意见（必填）"}
            {decision === "reject" && <em>*</em>}
          </label>
          <TextArea
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            rows={4}
            maxLength={2000}
            showCount
            placeholder={decision === "approve" ? "可补充审核结论或备注…" : "请明确说明需要修改的条款或空白项，便于业务人员处理…"}
          />
        </div>

        {decision === "approve" && (
          <Alert
            type="info"
            showIcon
            message="审核通过后，合同内容将锁定，发起人可下载正式 PDF。"
          />
        )}
      </Modal>
    </div>
  );
}
