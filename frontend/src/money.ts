import type { ContractTableAdjustments, TemplateField } from "./types";
import {
  FINAL_PAYMENT_PLACEHOLDER,
  PREPAYMENT_PLACEHOLDER,
  applyTableAdjustments,
  sanitizeRichHtml,
} from "./richtext";

export const TOTAL_AMOUNT_FIELD_KEY = "总额";
export const TOTAL_AMOUNT_UPPER_FIELD_KEY = "大写总额";
export const TOTAL_AMOUNT_COLUMN_LABEL = "总额（元）";
export const PREPAYMENT_FIELD_KEY = PREPAYMENT_PLACEHOLDER;
export const FINAL_PAYMENT_FIELD_KEY = FINAL_PAYMENT_PLACEHOLDER;

export type AutoAmountFieldKind = "total" | "upper" | "prepayment" | "final";

const CN_DIGITS = ["零", "壹", "贰", "叁", "肆", "伍", "陆", "柒", "捌", "玖"];
const CN_SMALL_UNITS = ["", "拾", "佰", "仟"];
const CN_BIG_UNITS = ["", "万", "亿", "万亿"];

export function autoAmountFieldKind(key: string): AutoAmountFieldKind | null {
  if (key === TOTAL_AMOUNT_FIELD_KEY) return "total";
  if (key === TOTAL_AMOUNT_UPPER_FIELD_KEY) return "upper";
  if (key === PREPAYMENT_FIELD_KEY) return "prepayment";
  if (key === FINAL_PAYMENT_FIELD_KEY) return "final";
  return null;
}

export function uppercaseFieldBaseKey(
  fields: Pick<TemplateField, "key">[],
  key: string,
): string | null {
  const candidates: string[] = [];
  if (key.startsWith("大写") && key.length > 2) candidates.push(key.slice(2));
  if (key.endsWith("大写") && key.length > 2) candidates.push(key.slice(0, -2));
  const keys = new Set(fields.map((field) => field.key));
  return candidates.find((candidate) => keys.has(candidate)) || null;
}

function normalizeLabel(value: string | null | undefined): string {
  return (value || "").replace(/[\s\u00a0]+/g, "");
}

function parseAmount(value: string | null | undefined): number | null {
  const cleaned = (value || "")
    .replace(/[\s\u00a0,，¥￥]/g, "")
    .replace(/元$/, "");
  if (!/^[+-]?\d+(?:\.\d+)?$/.test(cleaned)) return null;
  const amount = Number(cleaned);
  return Number.isFinite(amount) ? amount : null;
}

export function calculateTableRowTotal(
  quantity: string | null | undefined,
  unitPrice: string | null | undefined,
): string {
  const quantityValue = parseAmount(quantity);
  const unitPriceValue = parseAmount(unitPrice);
  if (quantityValue === null || unitPriceValue === null) return "";
  const total = Math.round(quantityValue * unitPriceValue * 100) / 100;
  return Number.isFinite(total) ? total.toFixed(2) : "";
}

function logicalCells(row: HTMLTableRowElement): { cell: HTMLTableCellElement; start: number }[] {
  let column = 0;
  return Array.from(row.cells).map((cell) => {
    const start = column;
    column += Math.max(1, cell.colSpan || 1);
    return { cell, start };
  });
}

function isSummaryRow(row: HTMLTableRowElement): boolean {
  return logicalCells(row).some(({ cell }) =>
    /^(合计|总计|小计)/.test(normalizeLabel(cell.textContent)),
  );
}

export function calculateContractTableTotal(
  content: string,
  adjustments?: ContractTableAdjustments,
): { total: number; hasColumn: boolean } {
  const adjusted = applyTableAdjustments(content, adjustments);
  const doc = new DOMParser().parseFromString(adjusted, "text/html");
  let cents = 0;
  let hasColumn = false;

  for (const table of Array.from(doc.querySelectorAll("table"))) {
    const rows = Array.from(table.rows).filter((row) => row.closest("table") === table);
    let headerIndex = -1;
    let targetColumn = -1;
    for (let rowIndex = 0; rowIndex < rows.length; rowIndex += 1) {
      const match = logicalCells(rows[rowIndex]).find(
        ({ cell }) => normalizeLabel(cell.textContent) === TOTAL_AMOUNT_COLUMN_LABEL,
      );
      if (!match) continue;
      headerIndex = rowIndex;
      targetColumn = match.start;
      hasColumn = true;
      break;
    }
    if (headerIndex < 0 || targetColumn < 0) continue;

    for (const row of rows.slice(headerIndex + 1)) {
      if (isSummaryRow(row)) continue;
      const target = logicalCells(row).find(
        ({ cell, start }) => start <= targetColumn && targetColumn < start + Math.max(1, cell.colSpan || 1),
      );
      const amount = parseAmount(target?.cell.textContent);
      if (amount !== null) cents += Math.round(amount * 100);
    }
  }

  return { total: cents / 100, hasColumn };
}

const PAYMENT_FIELD_KEYS = new Set([PREPAYMENT_FIELD_KEY, FINAL_PAYMENT_FIELD_KEY]);
const PAYMENT_BASE_FIELD_KEYS = [
  "总额",
  "总费用",
  "合同金额",
  "合同金额（元）",
  "合同总价",
  "价税合计",
  "服务费",
  "金额",
  "金额（元）",
];
const PAYMENT_BASE_LABEL_HINTS = [
  "总额",
  "总费用",
  "合同金额",
  "合同总价",
  "价税合计",
  "服务费",
  "金额",
];

function looksLikePaymentSource(key: string, label: string): boolean {
  const normalizedKey = key.trim();
  const normalizedText = normalizeLabel(label);
  if (!normalizedKey || PAYMENT_FIELD_KEYS.has(normalizedKey)) return false;
  if (/预付款|尾款/.test(normalizedKey) || /预付款|尾款/.test(normalizedText)) return false;
  if (/大写/.test(normalizedKey) || /大写/.test(normalizedText)) return false;
  return (
    PAYMENT_BASE_FIELD_KEYS.includes(normalizedKey) ||
    PAYMENT_BASE_LABEL_HINTS.some((hint) => normalizedText.includes(hint))
  );
}

export function resolvePaymentBaseAmount(
  tableTotal: number | null,
  fields: Pick<TemplateField, "key" | "label">[],
  values: Record<string, string>,
): number | null {
  if (tableTotal !== null && Number.isFinite(tableTotal)) return tableTotal;
  for (const field of fields) {
    const key = (field.key || "").trim();
    if (!looksLikePaymentSource(key, field.label || "")) continue;
    const amount = parseAmount(values[key]);
    if (amount !== null) return amount;
  }
  for (const key of PAYMENT_BASE_FIELD_KEYS) {
    const amount = parseAmount(values[key]);
    if (amount !== null) return amount;
  }
  return null;
}

function roundMoney(value: number): number {
  return Math.round(value * 100) / 100;
}

export function calculateSystemPaymentValues(
  content: string,
  adjustments: ContractTableAdjustments | undefined,
  fields: Pick<TemplateField, "key" | "label">[],
  values: Record<string, string>,
): Record<string, string> {
  const table = calculateContractTableTotal(content, adjustments);
  const base = resolvePaymentBaseAmount(
    table.hasColumn ? table.total : null,
    fields,
    values,
  );
  if (base === null) return {};
  const total = roundMoney(base);
  const prepayment = roundMoney(total * 0.3);
  const finalPayment = roundMoney(total - prepayment);
  return {
    [PREPAYMENT_FIELD_KEY]: amountToChineseUpper(prepayment),
    [FINAL_PAYMENT_FIELD_KEY]: amountToChineseUpper(finalPayment),
  };
}

function fourDigitsToChinese(value: number): string {
  const digits = [
    Math.floor(value / 1000) % 10,
    Math.floor(value / 100) % 10,
    Math.floor(value / 10) % 10,
    value % 10,
  ];
  let text = "";
  let zeroPending = false;
  for (let index = 0; index < digits.length; index += 1) {
    const digit = digits[index];
    if (!digit) {
      if (text) zeroPending = true;
      continue;
    }
    if (zeroPending) {
      text += "零";
      zeroPending = false;
    }
    text += CN_DIGITS[digit] + CN_SMALL_UNITS[3 - index];
  }
  return text;
}

function integerToChinese(value: number): string {
  if (value === 0) return "零";
  const groups: number[] = [];
  let remaining = value;
  while (remaining > 0) {
    groups.push(remaining % 10000);
    remaining = Math.floor(remaining / 10000);
  }

  let text = "";
  for (let index = groups.length - 1; index >= 0; index -= 1) {
    const group = groups[index];
    if (!group) {
      if (text && groups.slice(0, index).some((item) => item > 0) && !text.endsWith("零")) {
        text += "零";
      }
      continue;
    }
    if (text && group < 1000 && !text.endsWith("零")) text += "零";
    text += fourDigitsToChinese(group) + (CN_BIG_UNITS[index] || "");
  }
  return text.replace(/零+/g, "零").replace(/零$/g, "") || "零";
}

function amountParts(
  value: string | number,
): { negative: boolean; integer: number; jiao: number; fen: number } | null {
  const normalized = String(value ?? "")
    .replace(/[\s\u00a0,，¥￥]/g, "")
    .replace(/元$/, "");
  const numeric = Number(normalized);
  if (!Number.isFinite(numeric)) return null;
  const negative = numeric < 0;
  const cents = Math.round(Math.abs(numeric) * 100);
  const integer = Math.floor(cents / 100);
  const jiao = Math.floor(cents / 10) % 10;
  const fen = cents % 10;
  return { negative, integer, jiao, fen };
}

export function amountToChineseUpper(value: string | number): string {
  const parts = amountParts(value);
  if (!parts) return "";
  const { negative, integer, jiao, fen } = parts;

  let text = `${integerToChinese(integer)}元`;
  if (!jiao && !fen) {
    text += "整";
  } else {
    if (jiao) text += `${CN_DIGITS[jiao]}角`;
    else if (fen) text += "零";
    if (fen) text += `${CN_DIGITS[fen]}分`;
  }
  return `${negative ? "负" : ""}${text}`;
}

export function amountToChineseUpperShort(value: string | number): string {
  const parts = amountParts(value);
  if (!parts) return "";
  const { negative, integer, jiao, fen } = parts;
  let text: string;
  if (!jiao && !fen) {
    text = integerToChinese(integer);
  } else {
    text = integer ? `${integerToChinese(integer)}元` : "";
    if (jiao) text += `${CN_DIGITS[jiao]}角`;
    else if (fen && integer) text += "零";
    if (fen) text += `${CN_DIGITS[fen]}分`;
  }
  return `${negative ? "负" : ""}${text}`;
}

const SUMMARY_AMOUNT_PATTERN = /[¥￥]\s*[\d,，]*(?:\.\d+)?\s*元/;
const SUMMARY_UPPER_PATTERN = /(大写[：:]\s*(?:人民币)?\s*)[^）)]*/;

function collectTextNodes(node: Node, out: Text[] = []): Text[] {
  if (node.nodeType === 3) {
    out.push(node as Text);
  } else {
    node.childNodes.forEach((child) => collectTextNodes(child, out));
  }
  return out;
}

function replaceCellText(
  cell: HTMLElement,
  pattern: RegExp,
  replacer: (match: string, ...args: string[]) => string,
): boolean {
  let changed = false;
  for (const node of collectTextNodes(cell)) {
    const text = node.nodeValue || "";
    if (!pattern.test(text)) continue;
    node.nodeValue = text.replace(pattern, replacer);
    changed = true;
  }
  return changed;
}

function updateSummaryRow(
  summaryRow: HTMLTableRowElement,
  totalText: string,
  upperText: string,
): void {
  const candidates = Array.from(summaryRow.cells).filter(
    (cell) => !/^(合计|总计|小计)/.test(normalizeLabel(cell.textContent)),
  );
  if (!candidates.length) return;
  const amountCell =
    candidates.find((cell) => /[¥￥]|元/.test(cell.textContent || "")) ||
    candidates[candidates.length - 1];
  const upperCell = candidates.find((cell) => /大写/.test(cell.textContent || ""));

  const sameCell = upperCell === amountCell;
  const amountChanged = replaceCellText(
    amountCell,
    SUMMARY_AMOUNT_PATTERN,
    () => `¥ ${totalText} 元`,
  );
  const upperChanged = upperCell
    ? replaceCellText(
        upperCell,
        SUMMARY_UPPER_PATTERN,
        (_match, prefix) => `${prefix}${upperText}`,
      )
    : false;

  if (sameCell) {
    if (!amountChanged || !upperChanged) {
      amountCell.textContent = `¥ ${totalText} 元（大写：人民币 ${upperText}）`;
    }
    return;
  }
  if (!amountChanged) amountCell.textContent = `¥ ${totalText} 元`;
  if (upperCell) {
    if (!upperChanged) upperCell.textContent = `（大写：人民币 ${upperText}）`;
  } else {
    amountCell.textContent = `${amountCell.textContent || ""}（大写：人民币 ${upperText}）`;
  }
}

export function applyTableSummaryTotals(content: string): string {
  if (!content || !/<table/i.test(content)) return content;
  const doc = new DOMParser().parseFromString(content, "text/html");
  let changed = false;

  for (const table of Array.from(doc.querySelectorAll("table"))) {
    const rows = Array.from(table.rows).filter((row) => row.closest("table") === table);
    let headerIndex = -1;
    let targetColumn = -1;
    for (let rowIndex = 0; rowIndex < rows.length; rowIndex += 1) {
      const match = logicalCells(rows[rowIndex]).find(
        ({ cell }) => normalizeLabel(cell.textContent) === TOTAL_AMOUNT_COLUMN_LABEL,
      );
      if (match) {
        headerIndex = rowIndex;
        targetColumn = match.start;
        break;
      }
    }
    if (headerIndex < 0 || targetColumn < 0) continue;

    let cents = 0;
    let hasDataRow = false;
    let summaryRow: HTMLTableRowElement | null = null;
    for (const row of rows.slice(headerIndex + 1)) {
      if (isSummaryRow(row)) {
        if (!summaryRow) summaryRow = row;
        continue;
      }
      const cells = logicalCells(row);
      const firstText = normalizeLabel(cells[0]?.cell.textContent);
      if (/^(备注)/.test(firstText)) continue;
      hasDataRow = true;
      const target = cells.find(
        ({ cell, start }) =>
          start <= targetColumn && targetColumn < start + Math.max(1, cell.colSpan || 1),
      );
      const amount = parseAmount(target?.cell.textContent);
      if (amount !== null) cents += Math.round(amount * 100);
    }
    if (!hasDataRow || !summaryRow) continue;
    const totalValue = cents / 100;
    const rawTotal = totalValue.toFixed(2);
    const displayTotal = totalValue.toLocaleString("zh-CN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    updateSummaryRow(summaryRow, displayTotal, amountToChineseUpperShort(rawTotal));
    changed = true;
  }

  return changed ? sanitizeRichHtml(doc.body.innerHTML) : content;
}
