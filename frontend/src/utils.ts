import dayjs from "dayjs";
import type { ContractStatus, Role, TemplateField, TemplateFieldType } from "./types";

export const STATUS_META: Record<
  ContractStatus,
  { label: string; color: string; tone: string; description: string }
> = {
  draft: {
    label: "草稿",
    color: "default",
    tone: "slate",
    description: "尚未提交法务审核",
  },
  pending: {
    label: "待审核",
    color: "processing",
    tone: "amber",
    description: "法务正在审核中",
  },
  approved: {
    label: "已通过",
    color: "success",
    tone: "green",
    description: "法务审核通过，可下载 PDF",
  },
  rejected: {
    label: "已驳回",
    color: "error",
    tone: "red",
    description: "请根据审核意见修改后重新提交",
  },
};

export const ROLE_META: Record<Role, { label: string; short: string; tone: string }> = {
  admin: { label: "系统管理员", short: "管理员", tone: "violet" },
  legal: { label: "法务人员", short: "法务", tone: "blue" },
  business: { label: "业务人员", short: "业务", tone: "teal" },
};

export const EVENT_META: Record<string, { label: string; tone: string }> = {
  created: { label: "创建合同", tone: "slate" },
  updated: { label: "更新内容", tone: "slate" },
  submitted: { label: "提交审核", tone: "blue" },
  resubmitted: { label: "重新提交", tone: "blue" },
  approved: { label: "审核通过", tone: "green" },
  rejected: { label: "驳回修改", tone: "red" },
  withdrawn: { label: "撤回审核", tone: "amber" },
};

export const FIELD_TYPE_OPTIONS: { value: TemplateFieldType; label: string }[] = [
  { value: "text", label: "单行文本" },
  { value: "textarea", label: "多行文本" },
  { value: "date", label: "日期" },
  { value: "number", label: "数字" },
  { value: "currency", label: "金额" },
  { value: "select", label: "下拉选项" },
];

export function fieldTypeLabel(type: TemplateFieldType): string {
  return FIELD_TYPE_OPTIONS.find((item) => item.value === type)?.label || type;
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "-";
  return dayjs(value).format("YYYY-MM-DD HH:mm");
}

export function formatDate(value?: string | null): string {
  if (!value) return "-";
  return dayjs(value).format("YYYY-MM-DD");
}

export function formatRelative(value?: string | null): string {
  if (!value) return "-";
  const target = dayjs(value);
  const minutes = dayjs().diff(target, "minute");
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = dayjs().diff(target, "hour");
  if (hours < 24) return `${hours} 小时前`;
  const days = dayjs().diff(target, "day");
  if (days < 7) return `${days} 天前`;
  return target.format("MM-DD HH:mm");
}

export function initials(name?: string): string {
  if (!name) return "OA";
  const clean = name.split("·")[0].trim();
  return clean.slice(0, 3) || "OA";
}

export function missingRequiredFields(
  fields: TemplateField[],
  values: Record<string, string>,
): TemplateField[] {
  return fields.filter((field) => field.required && !(values[field.key] || "").trim());
}

export function stripDocumentHeading(content: string): string {
  const lines = content.replace(/\r/g, "").split("\n");
  while (lines.length && !lines[0].trim()) lines.shift();
  if (lines.length) {
    const first = lines[0].trim();
    if (first.length <= 24 && (first.includes("合同") || first.includes("协议"))) {
      lines.shift();
      while (lines.length && !lines[0].trim()) lines.shift();
    }
  }
  return lines.join("\n").trim();
}

export function formatCurrency(value: string): string {
  const numeric = Number(String(value).replace(/,/g, ""));
  if (!Number.isFinite(numeric)) return value;
  return numeric.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

const DATE_VALUE_RE = /^(\d{4})(?:-|\/|\.|年)(\d{1,2})(?:-|\/|\.|月)(\d{1,2})日?/;

export function normalizeDateValue(value: string): string {
  const match = String(value || "").trim().match(DATE_VALUE_RE);
  if (!match) return "";
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (month < 1 || month > 12 || day < 1 || day > 31) return "";
  return `${match[1]}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

export function formatChineseDateValue(value: string): string {
  const normalized = normalizeDateValue(value);
  if (!normalized) return value;
  const [year, month, day] = normalized.split("-");
  return `${year}年${month}月${day}日`;
}

interface NumericInputOptions {
  allowNegative?: boolean;
  maxDecimals?: number;
}

export function numericInputOptions(field: TemplateField): NumericInputOptions {
  if (field.type === "currency") {
    return { allowNegative: false, maxDecimals: 2 };
  }
  return { allowNegative: true, maxDecimals: 6 };
}

export function sanitizeNumericInput(
  raw: string,
  { allowNegative = false, maxDecimals = 6 }: NumericInputOptions = {},
): string {
  let source = String(raw || "")
    .replace(/[０-９]/g, (char) => String.fromCharCode(char.charCodeAt(0) - 0xfee0))
    .replace(/[－ー]/g, "-")
    .replace(/＋/g, "+")
    .replace(/．/g, ".")
    .replace(/[\s\u00a0,，¥￥]/g, "");

  let negative = false;
  if (source.startsWith("-") || source.startsWith("+")) {
    negative = allowNegative && source.startsWith("-");
    source = source.slice(1);
  }
  source = source.replace(/[+-]/g, "");

  const dotIndex = source.indexOf(".");
  const hasDot = dotIndex >= 0;
  const integerPart = (hasDot ? source.slice(0, dotIndex) : source).replace(/\D/g, "");
  const decimalPart = (hasDot ? source.slice(dotIndex + 1) : "")
    .replace(/\D/g, "")
    .slice(0, Math.max(0, maxDecimals));

  if (!integerPart && !decimalPart && !hasDot) {
    return negative ? "-" : "";
  }

  return `${negative ? "-" : ""}${integerPart || "0"}${hasDot ? "." : ""}${decimalPart}`;
}

export function fieldValueProblem(field: TemplateField, value: string): string {
  const trimmed = String(value || "").trim();
  if (!trimmed) return "";

  if (field.type === "currency" || field.type === "number") {
    const compact = trimmed.replace(/[\s\u00a0,，¥￥]/g, "");
    const pattern =
      field.type === "currency"
        ? /^\d+(?:\.\d{0,2})?$/
        : /^[+-]?\d+(?:\.\d{0,6})?$/;
    if (!pattern.test(compact) || !Number.isFinite(Number(compact))) {
      return field.type === "currency"
        ? "仅可填写数字金额，最多两位小数"
        : "仅可填写数字，最多六位小数";
    }
    return "";
  }

  if (field.type === "date") {
    const normalized = normalizeDateValue(trimmed);
    if (!normalized || dayjs(normalized).format("YYYY-MM-DD") !== normalized) {
      return "请选择有效日期";
    }
    return "";
  }

  if (field.type === "select") {
    return (field.options || []).includes(trimmed) ? "" : "请从下拉选项中选择";
  }

  return "";
}

export function invalidFieldValues(
  fields: TemplateField[],
  values: Record<string, string>,
): { field: TemplateField; message: string }[] {
  const keys = new Set(fields.map((field) => field.key));
  const uppercaseBaseExists = (key: string) => {
    const candidates: string[] = [];
    if (key.startsWith("大写") && key.length > 2) candidates.push(key.slice(2));
    if (key.endsWith("大写") && key.length > 2) candidates.push(key.slice(0, -2));
    return candidates.some((candidate) => keys.has(candidate));
  };
  return fields.flatMap((field) => {
    if (
      field.key === "预付款" ||
      field.key === "尾款" ||
      uppercaseBaseExists(field.key)
    ) {
      return [];
    }
    const message = fieldValueProblem(field, values[field.key] || "");
    return message ? [{ field, message }] : [];
  });
}
