import { useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { ContractTableAdjustments, TemplateField } from "../types";
import {
  CONTRACT_NUMBER_PLACEHOLDER,
  applyTableAdjustments,
  escapeHtml,
  renderPlaceholderHtml,
  stripRichHeading,
} from "../richtext";
import { applyTableSummaryTotals, calculateSystemPaymentValues } from "../money";
import { paginateContractHtml } from "../pagination";

interface ContractPaperProps {
  title: string;
  content: string;
  values: Record<string, string>;
  fields?: TemplateField[];
  tableAdjustments?: ContractTableAdjustments;
  contractNo?: string;
  hideContractNumber?: boolean;
  templateName?: string;
  highlight?: boolean;
  compact?: boolean;
  footer?: ReactNode;
}

export function ContractPaper({
  title,
  content,
  values,
  fields = [],
  tableAdjustments,
  contractNo,
  hideContractNumber = false,
  templateName,
  highlight = true,
  compact = false,
  footer,
}: ContractPaperProps) {
  const paymentValues = useMemo(
    () => calculateSystemPaymentValues(content, tableAdjustments, fields, values),
    [content, tableAdjustments, fields, values],
  );
  const renderedValues = useMemo(
    () => ({
      ...values,
      ...paymentValues,
      [CONTRACT_NUMBER_PLACEHOLDER]: hideContractNumber
        ? "\u200b"
        : contractNo?.trim() || "系统自动生成",
    }),
    [values, paymentValues, contractNo, hideContractNumber],
  );
  const bodyHtml = useMemo(
    () =>
      renderPlaceholderHtml(
        applyTableSummaryTotals(
          applyTableAdjustments(stripRichHeading(content), tableAdjustments),
        ),
        renderedValues,
        fields,
        highlight,
      ),
    [content, renderedValues, fields, highlight, tableAdjustments],
  );
  const firstHeaderHtml = useMemo(() => {
    const meta = [
      contractNo && !hideContractNumber ? `<span>编号 ${escapeHtml(contractNo)}</span>` : "",
      templateName ? `<span>${escapeHtml(templateName)}</span>` : "",
    ].join("");
    return [
      '<div class="paper-topline"><span>MMDY · CONTRACT</span><span>内部合同文件</span></div>',
      `<h2 class="paper-title">${escapeHtml(title)}</h2>`,
      meta ? `<div class="paper-meta-line">${meta}</div>` : "",
      '<div class="paper-rule"></div>',
    ].join("");
  }, [contractNo, hideContractNumber, templateName, title]);
  const nextHeaderHtml = useMemo(
    () =>
      [
        '<div class="paper-continuation-head">',
        `<span>${escapeHtml(title)}（续）</span>`,
        `<span>${escapeHtml(hideContractNumber ? "" : contractNo || "MMDY · CONTRACT")}</span>`,
        "</div>",
      ].join(""),
    [contractNo, hideContractNumber, title],
  );
  const containerRef = useRef<HTMLDivElement>(null);
  const [pageWidth, setPageWidth] = useState(780);
  const [pages, setPages] = useState<string[]>(() => [bodyHtml]);

  useLayoutEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const updateWidth = () => {
      const next = Math.max(320, Math.min(780, element.clientWidth || 780));
      setPageWidth((current) => (Math.abs(current - next) > 1 ? next : current));
    };
    updateWidth();
    const observer = new ResizeObserver(updateWidth);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useLayoutEffect(() => {
    const next = paginateContractHtml(bodyHtml, {
      pageWidth,
      firstHeaderHtml,
      nextHeaderHtml,
      footerLeft: "本文件由绵绵聚道合同管理模块生成",
    });
    setPages(next.length ? next : [""]);
  }, [bodyHtml, firstHeaderHtml, nextHeaderHtml, pageWidth]);

  return (
    <div
      ref={containerRef}
      className={`contract-paper-pages ${compact ? "contract-paper-pages-compact" : ""}`}
    >
      {pages.map((pageHtml, index) => (
        <div
          className={`contract-paper contract-paper-page ${compact ? "contract-paper-compact" : ""}`}
          key={index}
          data-page={index + 1}
        >
          <div
            className="paper-page-head"
            dangerouslySetInnerHTML={{
              __html: index === 0 ? firstHeaderHtml : nextHeaderHtml,
            }}
          />
          <div className="paper-page-body">
            <div
              className="paper-body paper-body-rich"
              dangerouslySetInnerHTML={{ __html: pageHtml }}
            />
          </div>
          <div className="paper-footer">
            <span>本文件由绵绵聚道合同管理模块生成</span>
            <span>第 {index + 1} 页 / 共 {pages.length} 页</span>
          </div>
          {index === pages.length - 1 ? footer : null}
        </div>
      ))}
    </div>
  );
}
