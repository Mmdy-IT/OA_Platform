import {
  DeleteOutlined,
  DownloadOutlined,
  PaperClipOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { Button, Modal, message } from "antd";
import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { api, ApiError } from "../api";
import type { ContractAttachment } from "../types";
import { formatDateTime } from "../utils";

const ACCEPT_ATTACHMENTS =
  ".xlsx,.xls,.doc,.docx,.dox,.pdf,image/*,.png,.jpg,.jpeg,.gif,.bmp,.webp,.tif,.tiff,.svg,.ico,.heic,.heif,.avif";

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(2)} MB`;
}

export function ContractAttachments({
  contractId,
  initialAttachments = [],
  editable = false,
  onEnsureContract,
}: {
  contractId?: number;
  initialAttachments?: ContractAttachment[];
  editable?: boolean;
  onEnsureContract?: () => Promise<number>;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [attachments, setAttachments] = useState<ContractAttachment[]>(initialAttachments);
  const [activeContractId, setActiveContractId] = useState<number | undefined>(contractId);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    setActiveContractId(contractId);
    if (!contractId) {
      setAttachments(initialAttachments);
      return;
    }
    let active = true;
    setLoading(true);
    api
      .contractAttachments(contractId)
      .then((result) => {
        if (active) setAttachments(result.items);
      })
      .catch(() => {
        if (active) setAttachments(initialAttachments);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    // Initial attachments are only a fallback; the authoritative list is loaded by API.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    return () => {
      active = false;
    };
  }, [contractId]);

  const handleFiles = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    if (!files.length) return;
    setUploading(true);
    try {
      let targetId = activeContractId;
      if (!targetId) {
        if (!onEnsureContract) {
          throw new Error("请先保存合同草稿后再上传附件");
        }
        targetId = await onEnsureContract();
        setActiveContractId(targetId);
        message.info("已自动保存合同草稿，并上传附件");
      }
      const result = await api.uploadContractAttachments(targetId, files);
      setAttachments((current) => [...current, ...result.items]);
      message.success(`已上传 ${result.items.length} 个附件`);
    } catch (caught) {
      message.error(caught instanceof ApiError ? caught.message : "附件上传失败");
    } finally {
      setUploading(false);
    }
  };

  const download = async (attachment: ContractAttachment) => {
    try {
      await api.downloadContractAttachment(attachment);
    } catch (caught) {
      message.error(caught instanceof ApiError ? caught.message : "附件下载失败");
    }
  };

  const remove = (attachment: ContractAttachment) => {
    Modal.confirm({
      title: "删除这个附件？",
      content: `附件「${attachment.original_name}」删除后无法恢复。`,
      okText: "确认删除",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: async () => {
        try {
          await api.deleteContractAttachment(attachment.id);
          setAttachments((current) => current.filter((item) => item.id !== attachment.id));
          message.success("附件已删除");
        } catch (caught) {
          message.error(caught instanceof ApiError ? caught.message : "附件删除失败");
        }
      },
    });
  };

  return (
    <div className="contract-attachments-panel">
      <div className="contract-attachments-head">
        <div>
          <span className="panel-eyebrow">ATTACHMENTS</span>
          <h3>合同附件</h3>
        </div>
        {editable && (
          <>
            <input
              ref={inputRef}
              type="file"
              hidden
              multiple
              accept={ACCEPT_ATTACHMENTS}
              onChange={handleFiles}
            />
            <Button
              icon={<UploadOutlined />}
              loading={uploading}
              onClick={() => inputRef.current?.click()}
            >
              上传附件
            </Button>
          </>
        )}
      </div>
      <p className="contract-attachments-help">
        支持 Excel、Word、PDF 及所有图片格式，单个附件不超过 20MB，最多 30 个。
        {editable && !activeContractId && " 首次上传附件时会自动保存合同草稿。"}
      </p>
      {loading ? (
        <div className="contract-attachments-empty">正在加载附件…</div>
      ) : attachments.length ? (
        <div className="contract-attachment-list">
          {attachments.map((attachment) => (
            <div className="contract-attachment-item" key={attachment.id}>
              <span className="contract-attachment-icon">
                <PaperClipOutlined />
              </span>
              <div className="contract-attachment-info">
                <strong title={attachment.original_name}>{attachment.original_name}</strong>
                <span>
                  {formatSize(attachment.size)} · {formatDateTime(attachment.created_at)}
                </span>
              </div>
              <Button
                type="text"
                icon={<DownloadOutlined />}
                title="下载附件"
                onClick={() => download(attachment)}
              />
              {editable && (
                <Button
                  type="text"
                  danger
                  icon={<DeleteOutlined />}
                  title="删除附件"
                  onClick={() => remove(attachment)}
                />
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="contract-attachments-empty">
          <PaperClipOutlined />
          <span>暂无附件</span>
        </div>
      )}
    </div>
  );
}
