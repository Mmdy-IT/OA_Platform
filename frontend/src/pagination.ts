interface ContractPaginationOptions {
  pageWidth: number;
  firstHeaderHtml: string;
  nextHeaderHtml: string;
  footerLeft: string;
}

interface PageState {
  body: HTMLElement;
  content: HTMLElement;
}

const PAGE_MAX_WIDTH = 780;
const PAGE_MIN_WIDTH = 320;

function escapeText(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function isOverflowing(body: HTMLElement): boolean {
  return body.scrollHeight > body.clientHeight + 1;
}

function tryAppend(state: PageState, node: Node): boolean {
  const clone = node.cloneNode(true);
  state.content.appendChild(clone);
  if (isOverflowing(state.body)) {
    state.content.removeChild(clone);
    return false;
  }
  return true;
}

function textLength(node: Node): number {
  if (node.nodeType === Node.TEXT_NODE) return (node as Text).data.length;
  let total = 0;
  node.childNodes.forEach((child) => {
    total += textLength(child);
  });
  return total;
}

function sliceTextNode(node: Node, start: number, end: number): Node {
  const clone = node.cloneNode(true);
  let offset = 0;
  const walker = document.createTreeWalker(clone, NodeFilter.SHOW_TEXT);
  const textNodes: Text[] = [];
  while (walker.nextNode()) {
    textNodes.push(walker.currentNode as Text);
  }
  textNodes.forEach((textNode) => {
    const length = textNode.data.length;
    const nodeStart = offset;
    const nodeEnd = offset + length;
    offset = nodeEnd;
    if (nodeEnd <= start || nodeStart >= end) {
      textNode.remove();
      return;
    }
    const from = Math.max(0, start - nodeStart);
    const to = Math.min(length, end - nodeStart);
    textNode.data = textNode.data.slice(from, to);
  });
  if (clone.nodeType === Node.ELEMENT_NODE) {
    (clone as Element).querySelectorAll("*").forEach((element) => {
      if (!element.textContent && !element.querySelector("br, img, svg, hr")) {
        element.remove();
      }
    });
  }
  return clone;
}

function isHeaderRow(row: HTMLTableRowElement): boolean {
  if (row.parentElement?.tagName === "THEAD") return true;
  const cells = Array.from(row.cells);
  return cells.length > 0 && cells.every((cell) => cell.tagName === "TH");
}

function createTableSkeleton(
  table: HTMLTableElement,
  headerRows: HTMLTableRowElement[],
): HTMLTableElement {
  const clone = table.cloneNode(false) as HTMLTableElement;
  Array.from(table.children).forEach((child) => {
    if (child.tagName === "COLGROUP") clone.appendChild(child.cloneNode(true));
  });
  if (headerRows.length) {
    const thead = document.createElement("thead");
    headerRows.forEach((row) => thead.appendChild(row.cloneNode(true)));
    clone.appendChild(thead);
  }
  clone.appendChild(document.createElement("tbody"));
  return clone;
}

function splitTextAcrossPages(node: Node, state: PageState, openPage: () => void): void {
  const total = textLength(node);
  if (total === 0) {
    state.content.appendChild(node.cloneNode(true));
    return;
  }
  let offset = 0;
  while (offset < total) {
    if (state.content.childNodes.length > 0) {
      const probe = sliceTextNode(node, offset, offset + 1);
      state.content.appendChild(probe);
      const overflows = isOverflowing(state.body);
      state.content.removeChild(probe);
      if (overflows) openPage();
    }
    let low = 1;
    let high = total - offset;
    let best = 0;
    while (low <= high) {
      const middle = Math.floor((low + high) / 2);
      const part = sliceTextNode(node, offset, offset + middle);
      state.content.appendChild(part);
      const overflows = isOverflowing(state.body);
      state.content.removeChild(part);
      if (overflows) {
        high = middle - 1;
      } else {
        best = middle;
        low = middle + 1;
      }
    }
    if (best === 0) best = 1;
    state.content.appendChild(sliceTextNode(node, offset, offset + best));
    offset += best;
    if (offset < total) openPage();
  }
}

function paginateTable(
  table: HTMLTableElement,
  state: PageState,
  openPage: () => void,
): void {
  if (tryAppend(state, table)) return;
  if (state.content.childNodes.length > 0) {
    openPage();
    if (tryAppend(state, table)) return;
  }

  const rows = Array.from(table.rows).filter((row) => row.closest("table") === table);
  let headerCount = 0;
  while (headerCount < rows.length && isHeaderRow(rows[headerCount])) headerCount += 1;
  const headerRows = rows.slice(0, headerCount);
  const bodyRows = rows.slice(headerCount);
  if (!bodyRows.length) {
    state.content.appendChild(table.cloneNode(true));
    return;
  }

  let index = 0;
  while (index < bodyRows.length) {
    if (state.content.childNodes.length > 0) openPage();
    const partial = createTableSkeleton(table, headerRows);
    state.content.appendChild(partial);
    const tbody = partial.tBodies[0] ?? partial.createTBody();
    let added = 0;
    while (index + added < bodyRows.length) {
      const row = bodyRows[index + added].cloneNode(true) as HTMLTableRowElement;
      tbody.appendChild(row);
      if (isOverflowing(state.body)) {
        tbody.removeChild(row);
        break;
      }
      added += 1;
    }
    if (added === 0) {
      tbody.appendChild(bodyRows[index].cloneNode(true));
      added = 1;
    }
    index += added;
    if (index < bodyRows.length) openPage();
  }
}

function paginateList(
  list: HTMLElement,
  state: PageState,
  openPage: () => void,
): void {
  if (tryAppend(state, list)) return;
  if (state.content.childNodes.length > 0) {
    openPage();
    if (tryAppend(state, list)) return;
  }

  const items = Array.from(list.children).filter((child) => child.tagName === "LI");
  if (!items.length) {
    state.content.appendChild(list.cloneNode(true));
    return;
  }

  let index = 0;
  while (index < items.length) {
    if (state.content.childNodes.length > 0) openPage();
    const partial = list.cloneNode(false) as HTMLElement;
    state.content.appendChild(partial);
    let added = 0;
    while (index + added < items.length) {
      const item = items[index + added].cloneNode(true);
      partial.appendChild(item);
      if (isOverflowing(state.body)) {
        partial.removeChild(item);
        break;
      }
      added += 1;
    }
    if (added === 0) {
      partial.appendChild(items[index].cloneNode(true));
      added = 1;
    }
    index += added;
    if (index < items.length) openPage();
  }
}

function createPageBody(
  root: HTMLElement,
  width: number,
  headerHtml: string,
  footerLeft: string,
): PageState {
  const page = document.createElement("div");
  page.className = "contract-paper contract-paper-page";
  page.style.width = `${width}px`;
  page.style.maxWidth = `${width}px`;

  const head = document.createElement("div");
  head.className = "paper-page-head";
  head.innerHTML = headerHtml;

  const bodyWrap = document.createElement("div");
  bodyWrap.className = "paper-page-body";
  const body = document.createElement("div");
  body.className = "paper-body paper-body-rich";
  bodyWrap.appendChild(body);

  const footer = document.createElement("div");
  footer.className = "paper-footer";
  footer.innerHTML = `<span>${escapeText(footerLeft)}</span><span>第 1 页 / 共 1 页</span>`;

  page.append(head, bodyWrap, footer);
  root.appendChild(page);
  return { body: bodyWrap, content: body };
}

export function paginateContractHtml(
  bodyHtml: string,
  options: ContractPaginationOptions,
): string[] {
  const width = Math.max(
    PAGE_MIN_WIDTH,
    Math.min(options.pageWidth || PAGE_MAX_WIDTH, PAGE_MAX_WIDTH),
  );
  const root = document.createElement("div");
  root.className = "contract-pagination-probe";
  root.style.cssText = [
    "position:fixed",
    "left:-10000px",
    "top:0",
    `width:${width}px`,
    "visibility:hidden",
    "pointer-events:none",
    "z-index:-1",
  ].join(";");
  document.body.appendChild(root);

  const bodies: HTMLElement[] = [];
  const state = createPageBody(root, width, options.firstHeaderHtml, options.footerLeft);
  bodies.push(state.content);
  const openPage = () => {
    const page = createPageBody(root, width, options.nextHeaderHtml, options.footerLeft);
    state.body = page.body;
    state.content = page.content;
    bodies.push(state.content);
  };

  try {
    const source = document.createElement("div");
    source.innerHTML = bodyHtml;
    Array.from(source.childNodes).forEach((node) => {
      if (node.nodeType === Node.TEXT_NODE && !node.textContent?.trim()) return;
      if (node.nodeType === Node.ELEMENT_NODE) {
        const element = node as HTMLElement;
        if (element.tagName === "TABLE") {
          paginateTable(element as HTMLTableElement, state, openPage);
          return;
        }
        if (element.tagName === "UL" || element.tagName === "OL") {
          paginateList(element, state, openPage);
          return;
        }
      }
      if (tryAppend(state, node)) return;
      if (state.content.childNodes.length > 0) {
        openPage();
        if (tryAppend(state, node)) return;
      }
      if (node.nodeType === Node.ELEMENT_NODE && textLength(node) > 0) {
        splitTextAcrossPages(node, state, openPage);
      } else {
        state.content.appendChild(node.cloneNode(true));
      }
    });
    return bodies.map((body) => body.innerHTML);
  } finally {
    root.remove();
  }
}
