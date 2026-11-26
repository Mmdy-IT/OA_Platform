import DOMPurify from "dompurify";
import type {
  ContractTableAdjustments,
  ContractTableNewRow,
  ContractTableRow,
  TemplateField,
} from "./types";
import { formatChineseDateValue, formatCurrency } from "./utils";

const PLACEHOLDER_SOURCE =
  String.raw`\{\{\s*([A-Za-z_\u3400-\u4dbf\u4e00-\u9fff][A-Za-z0-9_\u3400-\u4dbf\u4e00-\u9fff]{0,39})\s*\}\}`;

export const PLACEHOLDER_RE = new RegExp(PLACEHOLDER_SOURCE, "g");
export const FIELD_KEY_RE =
  /^[A-Za-z_\u3400-\u4dbf\u4e00-\u9fff][A-Za-z0-9_\u3400-\u4dbf\u4e00-\u9fff]{0,39}$/;

export const CONTRACT_NUMBER_PLACEHOLDER = "合同编号";
export const PREPAYMENT_PLACEHOLDER = "预付款";
export const FINAL_PAYMENT_PLACEHOLDER = "尾款";
export const SYSTEM_PLACEHOLDER_KEYS = [CONTRACT_NUMBER_PLACEHOLDER] as const;
export const AUTO_PLACEHOLDER_KEYS = [PREPAYMENT_PLACEHOLDER, FINAL_PAYMENT_PLACEHOLDER] as const;
const SYSTEM_PLACEHOLDER_SET = new Set<string>(SYSTEM_PLACEHOLDER_KEYS);
const AUTO_PLACEHOLDER_SET = new Set<string>(AUTO_PLACEHOLDER_KEYS);

export function isSystemPlaceholderKey(key: string): boolean {
  return SYSTEM_PLACEHOLDER_SET.has(key);
}

export function isAutoPlaceholderKey(key: string): boolean {
  return AUTO_PLACEHOLDER_SET.has(key);
}

const HTML_TAG_RE =
  /<\/?(?:p|div|br|h[1-6]|strong|b|em|i|u|s|strike|span|font|table|thead|tbody|tfoot|tr|td|th|ul|ol|li|blockquote|hr|sub|sup|pre|colgroup|col)\b[^>]*>/i;

const ALLOWED_TAGS = [
  "p", "div", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
  "strong", "b", "em", "i", "u", "s", "strike", "del", "span", "mark",
  "table", "thead", "tbody", "tfoot", "tr", "td", "th", "colgroup", "col",
  "ul", "ol", "li", "blockquote", "pre", "sub", "sup",
];

const SANITIZE_OPTIONS = {
  ALLOWED_TAGS,
  ALLOWED_ATTR: ["style", "colspan", "rowspan", "start"],
  ALLOW_DATA_ATTR: false,
};

export function isRichHtml(content: string | null | undefined): boolean {
  return !!content && HTML_TAG_RE.test(content);
}

export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function plainTextToHtml(text: string | null | undefined): string {
  const lines = (text || "").replace(/\r/g, "").split("\n");
  while (lines.length && !lines[0].trim()) lines.shift();
  while (lines.length && !lines[lines.length - 1].trim()) lines.pop();
  if (!lines.length) return "<p></p>";
  return lines
    .map((line) => (line.trim() ? `<p>${escapeHtml(line.replace(/\s+$/, ""))}</p>` : "<p></p>"))
    .join("");
}

export function sanitizeRichHtml(html: string | null | undefined): string {
  return DOMPurify.sanitize(html || "", SANITIZE_OPTIONS);
}

export function toEditorHtml(content: string | null | undefined): string {
  return isRichHtml(content) ? sanitizeRichHtml(content) : plainTextToHtml(content);
}

export function htmlToPlainText(content: string | null | undefined): string {
  if (!content) return "";
  if (!isRichHtml(content)) return content.replace(/\r/g, "");
  const doc = new DOMParser().parseFromString(content, "text/html");
  return (doc.body.textContent || "").replace(/\u00a0/g, " ");
}

export function hasRichContent(content: string | null | undefined): boolean {
  return htmlToPlainText(content).trim().length > 0;
}

export function extractPlaceholderKeys(content: string | null | undefined): string[] {
  const text = htmlToPlainText(content);
  const keys: string[] = [];
  PLACEHOLDER_RE.lastIndex = 0;
  for (const match of text.matchAll(PLACEHOLDER_RE)) {
    if (!keys.includes(match[1])) keys.push(match[1]);
  }
  return keys;
}

export function stripDocumentHeading(html: string): string {
  const doc = new DOMParser().parseFromString(html, "text/html");
  const first = doc.body.firstElementChild;
  if (first) {
    const text = (first.textContent || "").trim();
    if (
      text &&
      text.length <= 30 &&
      /合同|协议/.test(text) &&
      !text.includes("{{") &&
      !/[：:，,。；;]/.test(text)
    ) {
      first.remove();
    }
  }
  return doc.body.innerHTML;
}

function replacePlaceholdersInTextNodes(
  doc: Document,
  values: Record<string, string>,
  fields: TemplateField[],
  highlight: boolean,
): void {
  const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  while (walker.nextNode()) nodes.push(walker.currentNode as Text);

  for (const node of nodes) {
    const text = node.nodeValue || "";
    PLACEHOLDER_RE.lastIndex = 0;
    if (!PLACEHOLDER_RE.test(text)) continue;

    const fragment = doc.createDocumentFragment();
    let last = 0;
    PLACEHOLDER_RE.lastIndex = 0;
    let match: RegExpExecArray | null;
    while ((match = PLACEHOLDER_RE.exec(text))) {
      if (match.index > last) {
        fragment.appendChild(doc.createTextNode(text.slice(last, match.index)));
      }
      const key = match[1];
      const field = fields.find((item) => item.key === key);
      const rawValue = (values[key] || "").trim();
      const span = doc.createElement("span");
      if (rawValue) {
        if (highlight) span.className = "paper-value";
        span.textContent =
          field?.type === "currency"
            ? formatCurrency(rawValue)
            : field?.type === "date"
              ? formatChineseDateValue(rawValue)
              : rawValue;
      } else {
        span.className = highlight ? "paper-blank" : "paper-empty";
        span.textContent = "________________";
      }
      fragment.appendChild(span);
      last = match.index + match[0].length;
    }
    if (last < text.length) fragment.appendChild(doc.createTextNode(text.slice(last)));
    node.parentNode?.replaceChild(fragment, node);
  }
}

export function renderPlaceholderHtml(
  content: string,
  values: Record<string, string>,
  fields: TemplateField[] = [],
  highlight = true,
): string {
  const base = toEditorHtml(content);
  const doc = new DOMParser().parseFromString(base, "text/html");
  replacePlaceholdersInTextNodes(doc, values, fields, highlight);
  return sanitizeRichHtml(doc.body.innerHTML);
}

export function stripRichHeading(html: string): string {
  return stripDocumentHeading(toEditorHtml(html));
}

export interface ContractTableModel {
  index: number;
  headerCount: number;
  columnCount: number;
  columnLabels: string[];
  columnRoles: {
    sequence: number | null;
    quantity: number | null;
    unitPrice: number | null;
    total: number | null;
  };
  bodyRows: number[];
  rowLabels: string[];
  dataRowFlags: boolean[];
}

function tableRows(table: HTMLTableElement): HTMLTableRowElement[] {
  return Array.from(table.rows).filter((row) => row.closest("table") === table);
}

function isHeaderRow(row: HTMLTableRowElement): boolean {
  if (row.parentElement?.tagName === "THEAD") return true;
  const cells = Array.from(row.cells);
  return cells.length > 0 && cells.every((cell) => cell.tagName === "TH");
}

function rowLabel(row: HTMLTableRowElement): string {
  const text = (row.textContent || "").replace(/\s+/g, " ").trim();
  return text.length > 32 ? `${text.slice(0, 32)}…` : text;
}

const HEADER_HINTS = [
  "序号", "名称", "规格", "型号", "数量", "单价", "总额", "金额",
  "单位", "备注", "项目", "内容", "日期", "税率",
];

function normalizedLabel(value: string | null | undefined): string {
  return (value || "").replace(/[\s\u00a0]+/g, "");
}

function looksLikeHeaderRow(row: HTMLTableRowElement): boolean {
  const labels = Array.from(row.cells).map((cell) => normalizedLabel(cell.textContent));
  if (labels.length < 2 || labels.some((label) => !label)) return false;
  return labels.some((label) => HEADER_HINTS.some((hint) => label.includes(hint)));
}

function columnIndex(labels: string[], keyword: string): number | null {
  const index = labels.findIndex((label) => normalizedLabel(label).includes(keyword));
  return index >= 0 ? index : null;
}

export function isNewContractTableRow(row: ContractTableRow): row is ContractTableNewRow {
  return typeof row === "object" && row !== null;
}

export function inspectContractTables(content: string | null | undefined): ContractTableModel[] {
  const doc = new DOMParser().parseFromString(toEditorHtml(content), "text/html");
  return Array.from(doc.querySelectorAll("table")).map((table, index) => {
    const rows = tableRows(table);
    let headerCount = 0;
    while (headerCount < rows.length && isHeaderRow(rows[headerCount])) headerCount += 1;
    const bodyRows = rows.slice(headerCount);
    const columnCount = Math.max(
      1,
      ...rows.map((row) => row.cells.length),
    );
    const labelRow = headerCount
      ? rows[0]
      : rows[0] && looksLikeHeaderRow(rows[0])
        ? rows[0]
        : null;
    const headerLabels = labelRow
      ? Array.from(labelRow.cells).map((cell) => (cell.textContent || "").replace(/\s+/g, " ").trim())
      : [];
    const columnLabels = Array.from(
      { length: columnCount },
      (_, columnIndexValue) => headerLabels[columnIndexValue] || `第${columnIndexValue + 1}列`,
    );
    const dataRowFlags = bodyRows.map((row) => {
      if (row === labelRow) return false;
      const text = normalizedLabel(row.textContent);
      if (!text) return false;
      const firstCell = normalizedLabel(row.cells[0]?.textContent);
      return !/^(合计|总计|小计|备注)/.test(firstCell || text);
    });
    return {
      index,
      headerCount,
      columnCount,
      columnLabels,
      columnRoles: {
        sequence: columnIndex(columnLabels, "序号"),
        quantity: columnIndex(columnLabels, "数量"),
        unitPrice: columnIndex(columnLabels, "单价"),
        total: columnIndex(columnLabels, "总额"),
      },
      bodyRows: bodyRows.map((_, rowIndex) => rowIndex),
      rowLabels: bodyRows.map(rowLabel),
      dataRowFlags,
    };
  });
}

export function applyTableAdjustments(
  content: string,
  adjustments: ContractTableAdjustments | undefined,
): string {
  if (!content || !adjustments || !Object.keys(adjustments).length) return content;
  const doc = new DOMParser().parseFromString(content, "text/html");
  const tables = Array.from(doc.querySelectorAll("table"));

  for (const [rawIndex, rawRows] of Object.entries(adjustments)) {
    const index = Number(rawIndex);
    if (!Number.isInteger(index) || index < 0 || index >= tables.length || !Array.isArray(rawRows)) {
      continue;
    }
    const table = tables[index];
    const rows = tableRows(table);
    let headerCount = 0;
    while (headerCount < rows.length && isHeaderRow(rows[headerCount])) headerCount += 1;
    const bodyRows = rows.slice(headerCount);
    if (!bodyRows.length) continue;

    const columnCount = Math.max(1, ...rows.map((row) => row.cells.length));
    const sourceRows = bodyRows.map((row) => row.cloneNode(true) as HTMLTableRowElement);
    const seen = new Set<number>();
    const selected: ContractTableRow[] = [];
    for (const item of rawRows.slice(0, 200)) {
      if (item === null) {
        selected.push(null);
      } else if (isNewContractTableRow(item)) {
        selected.push({
          id: item.id || `new-${index}-${selected.length}`,
          cells: Array.isArray(item.cells) ? item.cells.map((cell) => String(cell || "")) : [],
        });
      } else if (Number.isInteger(item) && item >= 0 && item < sourceRows.length && !seen.has(item)) {
        selected.push(item);
        seen.add(item);
      }
    }
    const finalRows = selected.length ? selected : [null];

    bodyRows.forEach((row) => row.remove());
    let tbody = Array.from(table.children).find(
      (child): child is HTMLTableSectionElement => child.tagName === "TBODY",
    );
    if (!tbody) {
      tbody = doc.createElement("tbody");
      const thead = Array.from(table.children).find((child) => child.tagName === "THEAD");
      if (thead) thead.insertAdjacentElement("afterend", tbody);
      else table.insertBefore(tbody, table.firstChild);
    }

    for (const item of finalRows) {
      if (item === null || isNewContractTableRow(item)) {
        const row = doc.createElement("tr");
        const values = isNewContractTableRow(item) ? item.cells : [];
        for (let cellIndex = 0; cellIndex < columnCount; cellIndex += 1) {
          const cell = doc.createElement("td");
          const lines = String(values[cellIndex] || "").split(/\r?\n/);
          cell.appendChild(doc.createTextNode(lines[0] || "\u00a0"));
          for (const line of lines.slice(1)) {
            cell.appendChild(doc.createElement("br"));
            cell.appendChild(doc.createTextNode(line || "\u00a0"));
          }
          row.appendChild(cell);
        }
        tbody.appendChild(row);
      } else {
        tbody.appendChild(sourceRows[item].cloneNode(true));
      }
    }
  }

  return sanitizeRichHtml(doc.body.innerHTML);
}
