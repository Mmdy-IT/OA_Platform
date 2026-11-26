import { Tag } from "antd";
import type { ContractStatus } from "../types";
import { STATUS_META } from "../utils";

export function StatusTag({ status, dot = true }: { status: ContractStatus; dot?: boolean }) {
  const meta = STATUS_META[status];
  return (
    <Tag color={meta.color} className={`status-tag status-${meta.tone}`}>
      {dot && <span className="status-dot" />}
      {meta.label}
    </Tag>
  );
}
