import {
  CheckCircleFilled,
  DeleteOutlined,
  EditOutlined,
  FileProtectOutlined,
  InfoCircleOutlined,
  PlusOutlined,
  SaveOutlined,
  SendOutlined,
  SwapOutlined,
  TableOutlined,
} from "@ant-design/icons";
import { Alert, Button, DatePicker, Input, Modal, Progress, Select, Tag, message } from "antd";
import dayjs from "dayjs";
import type { ChangeEvent, PointerEvent as ReactPointerEvent, ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type {
  ContractTableAdjustments,
  ContractTableNewRow,
  ContractTableRow,
  PartyAutoFillRole,
  PartyInfo,
  Template,
  TemplateField,
  WarehouseInfo,
} from "../types";
import {
  inspectContractTables,
  isNewContractTableRow,
  type ContractTableModel,
} from "../richtext";
import {
  PARTY_SIDE_LABEL,
  isPartyAutoFillRole,
  isPartyNameRole,
  isWarehouseAutoFillRole,
  partyValueForRole,
  resolveAutoFill,
  roleAttribute,
  roleSide,
} from "../party";
import {
  FINAL_PAYMENT_FIELD_KEY,
  PREPAYMENT_FIELD_KEY,
  TOTAL_AMOUNT_FIELD_KEY,
  TOTAL_AMOUNT_UPPER_FIELD_KEY,
  amountToChineseUpper,
  amountToChineseUpperShort,
  autoAmountFieldKind,
  calculateSystemPaymentValues,
  calculateTableRowTotal,
  calculateContractTableTotal,
  uppercaseFieldBaseKey,
  type AutoAmountFieldKind,
} from "../money";
import {
  fieldTypeLabel,
  fieldValueProblem,
  invalidFieldValues,
  missingRequiredFields,
  normalizeDateValue,
  numericInputOptions,
  sanitizeNumericInput,
} from "../utils";
import { ContractPaper } from "./ContractPaper";

function newTableRowId(): string {
  return `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function applyAutoTableRows(
  model: ContractTableModel,
  rows: ContractTableRow[],
): ContractTableRow[] {
  const { sequence: sequenceColumn, quantity, unitPrice, total } = model.columnRoles;
  let sequence = 0;
  return rows.map((source) => {
    if (!isNewContractTableRow(source)) {
      if (typeof source === "number" && model.dataRowFlags[source]) sequence += 1;
      return source;
    }
    sequence += 1;
    const cells = [...source.cells];
    if (sequenceColumn !== null) cells[sequenceColumn] = String(sequence);
    if (quantity !== null && unitPrice !== null && total !== null) {
      cells[total] = calculateTableRowTotal(cells[quantity], cells[unitPrice]);
    }
    return { ...source, cells };
  });
}

function hydrateTableAdjustments(
  content: string,
  adjustments: ContractTableAdjustments,
): ContractTableAdjustments {
  const models = inspectContractTables(content);
  const next: ContractTableAdjustments = {};
  for (const [rawIndex, rows] of Object.entries(adjustments)) {
    const index = Number(rawIndex);
    const model = models.find((item) => item.index === index);
    if (!model || !Array.isArray(rows)) continue;
    next[rawIndex] = applyAutoTableRows(
      model,
      rows.map((row) => {
        if (isNewContractTableRow(row)) {
          return {
            id: row.id || newTableRowId(),
            cells: Array.from(
              { length: model.columnCount },
              (_, cellIndex) => String(row.cells[cellIndex] || ""),
            ),
          };
        }
        if (row === null) {
          return {
            id: newTableRowId(),
            cells: Array.from({ length: model.columnCount }, () => ""),
          };
        }
        return row;
      }),
    );
  }
  return next;
}

interface ContractComposerProps {
  template: Pick<
    Template,
    "name" | "category" | "version" | "description" | "instructions" | "content" | "fields"
  >;
  initialTitle?: string;
  initialValues?: Record<string, string>;
  initialTableAdjustments?: ContractTableAdjustments;
  contractNo?: string;
  banner?: ReactNode;
  onChangeTemplate?: () => void;
  backAction?: ReactNode;
  onSaveDraft: (
    title: string,
    values: Record<string, string>,
    tableAdjustments: ContractTableAdjustments,
  ) => Promise<void>;
  onSubmitReview: (
    title: string,
    values: Record<string, string>,
    tableAdjustments: ContractTableAdjustments,
  ) => Promise<void>;
}

export function ContractComposer({
  template,
  initialTitle = "",
  initialValues = {},
  initialTableAdjustments = {},
  contractNo,
  banner,
  onChangeTemplate,
  backAction,
  onSaveDraft,
  onSubmitReview,
}: ContractComposerProps) {
  const [title, setTitle] = useState(initialTitle || template.name);
  const [values, setValues] = useState<Record<string, string>>(initialValues);
  const [tableAdjustments, setTableAdjustments] = useState<ContractTableAdjustments>(() =>
    hydrateTableAdjustments(template.content, initialTableAdjustments),
  );
  const [draggedRow, setDraggedRow] = useState<{ table: number; position: number } | null>(null);
  const [dropTarget, setDropTarget] = useState<{ table: number; position: number } | null>(null);
  const dragStateRef = useRef<{ table: number; from: number; to: number } | null>(null);
  const [errors, setErrors] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<"draft" | "submit" | null>(null);
  const [parties, setParties] = useState<PartyInfo[]>([]);
  const [partyLoading, setPartyLoading] = useState(true);
  const [partyError, setPartyError] = useState("");
  const [warehouses, setWarehouses] = useState<WarehouseInfo[]>([]);
  const [warehouseLoading, setWarehouseLoading] = useState(true);
  const [warehouseError, setWarehouseError] = useState("");
  const hasPartyFields = useMemo(
    () =>
      template.fields.some((field) => {
        const role = resolveAutoFill(field);
        return !!role && isPartyAutoFillRole(role);
      }),
    [template.fields],
  );
  const hasWarehouseFields = useMemo(
    () =>
      template.fields.some((field) => {
        const role = resolveAutoFill(field);
        return !!role && isWarehouseAutoFillRole(role);
      }),
    [template.fields],
  );

  useEffect(() => {
    if (!hasPartyFields) {
      setPartyLoading(false);
      return;
    }
    let active = true;
    setPartyLoading(true);
    api
      .parties()
      .then((result) => {
        if (!active) return;
        setParties(result.items);
        setPartyError("");
      })
      .catch(() => {
        if (!active) return;
        setParties([]);
        setPartyError("主体信息库暂时不可用，可先手动填写主体名称，恢复后刷新页面即可自动带出。");
      })
      .finally(() => {
        if (active) setPartyLoading(false);
      });
    return () => {
      active = false;
    };
  }, [hasPartyFields]);

  const partyByName = useMemo(
    () =>
      new Map(
        parties.map((party) => [
          `${party.party_type || "甲方"}|${party.entity_name}`,
          party,
        ]),
      ),
    [parties],
  );

  useEffect(() => {
    if (!parties.length) return;
    setValues((current) => {
      const next = { ...current };
      let changed = false;
      for (const field of template.fields) {
        const role = resolveAutoFill(field);
        if (!role || !isPartyAutoFillRole(role) || !isPartyNameRole(role)) continue;
        const side = roleSide(role);
        const party = partyByName.get(
          `${side === "party_a" ? "甲方" : "乙方"}|${current[field.key] || ""}`,
        );
        if (!party) continue;
        for (const other of template.fields) {
          const otherRole = resolveAutoFill(other);
          if (
            !otherRole ||
            !isPartyAutoFillRole(otherRole) ||
            roleAttribute(otherRole) === "name" ||
            roleSide(otherRole) !== side
          ) {
            continue;
          }
          if ((current[other.key] || "").trim()) continue;
          next[other.key] = partyValueForRole(party, otherRole);
          changed = true;
        }
      }
      return changed ? next : current;
    });
  }, [parties, partyByName, template.fields]);

  useEffect(() => {
    if (!hasWarehouseFields) {
      setWarehouseLoading(false);
      return;
    }
    let active = true;
    setWarehouseLoading(true);
    api
      .warehouses()
      .then((result) => {
        if (!active) return;
        setWarehouses(result.items);
        setWarehouseError("");
      })
      .catch(() => {
        if (!active) return;
        setWarehouses([]);
        setWarehouseError("仓库信息库暂时不可用，请稍后刷新页面重试。");
      })
      .finally(() => {
        if (active) setWarehouseLoading(false);
      });
    return () => {
      active = false;
    };
  }, [hasWarehouseFields]);

  const warehouseByName = useMemo(
    () => new Map(warehouses.map((item) => [item.warehouse_short_name, item])),
    [warehouses],
  );
  const warehouseByAddress = useMemo(
    () => new Map(warehouses.map((item) => [item.warehouse_address, item])),
    [warehouses],
  );

  useEffect(() => {
    if (!warehouses.length) return;
    setValues((current) => {
      const next = { ...current };
      let changed = false;
      for (const field of template.fields) {
        if (resolveAutoFill(field) !== "warehouse_short_name") continue;
        const raw = (current[field.key] || "").trim();
        const warehouse = warehouseByName.get(raw) || warehouseByAddress.get(raw);
        if (!warehouse) continue;
        if (raw !== warehouse.warehouse_address) {
          next[field.key] = warehouse.warehouse_address;
          changed = true;
        }
        for (const other of template.fields) {
          if (resolveAutoFill(other) !== "warehouse_address") continue;
          if ((current[other.key] || "").trim()) continue;
          next[other.key] = warehouse.warehouse_address;
          changed = true;
        }
      }
      return changed ? next : current;
    });
  }, [warehouses, warehouseByName, warehouseByAddress, template.fields]);

  const tableModels = useMemo(
    () => inspectContractTables(template.content).filter((model) => model.bodyRows.length > 0),
    [template.content],
  );

  const autoAmountState = useMemo(() => {
    const keys = new Set(template.fields.map((field) => field.key));
    if (!keys.has(TOTAL_AMOUNT_FIELD_KEY) && !keys.has(TOTAL_AMOUNT_UPPER_FIELD_KEY)) {
      return { values: {}, hasColumn: false };
    }
    const result = calculateContractTableTotal(template.content, tableAdjustments);
    if (!result.hasColumn) return { values: {}, hasColumn: false };
    const totalText = result.total.toFixed(2);
    const next: Record<string, string> = {};
    if (keys.has(TOTAL_AMOUNT_FIELD_KEY)) next[TOTAL_AMOUNT_FIELD_KEY] = totalText;
    if (keys.has(TOTAL_AMOUNT_UPPER_FIELD_KEY)) {
      next[TOTAL_AMOUNT_UPPER_FIELD_KEY] = amountToChineseUpper(totalText);
    }
    return { values: next, hasColumn: true };
  }, [template.content, template.fields, tableAdjustments]);

  const autoPaymentState = useMemo(() => {
    const keys = new Set(template.fields.map((field) => field.key));
    if (!keys.has(PREPAYMENT_FIELD_KEY) && !keys.has(FINAL_PAYMENT_FIELD_KEY)) {
      return { values: {}, hasBase: false };
    }
    const systemValues = calculateSystemPaymentValues(
      template.content,
      tableAdjustments,
      template.fields,
      values,
    );
    if (!systemValues[PREPAYMENT_FIELD_KEY]) return { values: {}, hasBase: false };
    const next: Record<string, string> = {};
    if (keys.has(PREPAYMENT_FIELD_KEY)) {
      next[PREPAYMENT_FIELD_KEY] = systemValues[PREPAYMENT_FIELD_KEY];
    }
    if (keys.has(FINAL_PAYMENT_FIELD_KEY)) {
      next[FINAL_PAYMENT_FIELD_KEY] = systemValues[FINAL_PAYMENT_FIELD_KEY];
    }
    return { values: next, hasBase: true };
  }, [template.content, template.fields, tableAdjustments, values]);

  const uppercaseSources = useMemo(() => {
    const sources: Record<string, string> = {};
    for (const field of template.fields) {
      if (field.key === TOTAL_AMOUNT_UPPER_FIELD_KEY) continue;
      const baseKey = uppercaseFieldBaseKey(template.fields, field.key);
      if (baseKey && baseKey !== field.key) sources[field.key] = baseKey;
    }
    return sources;
  }, [template.fields]);

  const autoUppercaseValues = useMemo(() => {
    const next: Record<string, string> = {};
    for (const [upperKey, baseKey] of Object.entries(uppercaseSources)) {
      const raw = String(autoAmountState.values[baseKey] ?? values[baseKey] ?? "").trim();
      next[upperKey] = raw ? amountToChineseUpperShort(raw) : "";
    }
    return next;
  }, [uppercaseSources, autoAmountState.values, values]);

  const effectiveValues = useMemo(
    () => ({
      ...values,
      ...autoAmountState.values,
      ...autoPaymentState.values,
      ...autoUppercaseValues,
    }),
    [values, autoAmountState.values, autoPaymentState.values, autoUppercaseValues],
  );

  const requiredCount = template.fields.filter((field) => field.required).length;
  const completedRequired = template.fields.filter(
    (field) => field.required && (effectiveValues[field.key] || "").trim(),
  ).length;
  const completion = requiredCount ? Math.round((completedRequired / requiredCount) * 100) : 100;

  const missing = useMemo(
    () => missingRequiredFields(template.fields, effectiveValues),
    [template.fields, effectiveValues],
  );

  const autoKindForField = (key: string): AutoAmountFieldKind | null => {
    const kind = autoAmountFieldKind(key);
    if (!kind) return null;
    if (kind === "prepayment" || kind === "final") {
      return autoPaymentState.hasBase ? kind : null;
    }
    return autoAmountState.hasColumn ? kind : null;
  };

  const rowsForTable = (model: ContractTableModel): ContractTableRow[] =>
    tableAdjustments[String(model.index)] || model.bodyRows;

  const setRowsForTable = (model: ContractTableModel, rows: ContractTableRow[]) => {
    setTableAdjustments((current) => {
      const next = { ...current };
      const key = String(model.index);
      const normalized = applyAutoTableRows(model, rows);
      const unchanged =
        normalized.length === model.bodyRows.length &&
        normalized.every((item, index) => item === model.bodyRows[index]);
      if (unchanged) delete next[key];
      else next[key] = normalized;
      return next;
    });
  };

  const addTableRow = (model: ContractTableModel) => {
    const row: ContractTableNewRow = {
      id: newTableRowId(),
      cells: Array.from({ length: model.columnCount }, () => ""),
    };
    const rows = rowsForTable(model);
    const insertAt = rows.findIndex(
      (item) =>
        typeof item === "number" &&
        /^(合计|总计|小计|备注)/.test(model.rowLabels[item] || ""),
    );
    const position = insertAt >= 0 ? insertAt : rows.length;
    setRowsForTable(model, [...rows.slice(0, position), row, ...rows.slice(position)]);
  };

  const removeTableRow = (model: ContractTableModel, position: number) => {
    const rows = rowsForTable(model);
    if (!isNewContractTableRow(rows[position])) return;
    setRowsForTable(model, rows.filter((_, index) => index !== position));
  };

  const updateTableRowCell = (
    model: ContractTableModel,
    position: number,
    cellIndex: number,
    value: string,
  ) => {
    const rows = rowsForTable(model);
    const row = rows[position];
    if (!isNewContractTableRow(row)) return;
    const cells = Array.from(
      { length: model.columnCount },
      (_, index) => (index === cellIndex ? value : row.cells[index] || ""),
    );
    const next = [...rows];
    next[position] = { ...row, cells };
    setRowsForTable(model, next);
  };

  const rowAtPoint = (x: number, y: number) => {
    const element = document.elementFromPoint(x, y)?.closest<HTMLElement>("[data-table-row]");
    if (!element) return null;
    const table = Number(element.dataset.tableIndex);
    const position = Number(element.dataset.rowPosition);
    if (!Number.isInteger(table) || !Number.isInteger(position)) return null;
    return { table, position };
  };

  const startRowDrag = (
    event: ReactPointerEvent<HTMLSpanElement>,
    model: ContractTableModel,
    position: number,
  ) => {
    if (event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    dragStateRef.current = { table: model.index, from: position, to: position };
    setDraggedRow({ table: model.index, position });
    setDropTarget({ table: model.index, position });
  };

  const moveRowDrag = (event: ReactPointerEvent<HTMLSpanElement>) => {
    const state = dragStateRef.current;
    if (!state) return;
    const target = rowAtPoint(event.clientX, event.clientY);
    if (!target || target.table !== state.table || target.position === state.to) return;
    state.to = target.position;
    setDropTarget({ table: state.table, position: target.position });
  };

  const finishRowDrag = (event?: ReactPointerEvent<HTMLSpanElement>) => {
    const state = dragStateRef.current;
    dragStateRef.current = null;
    setDraggedRow(null);
    setDropTarget(null);
    if (!state) return;
    const target = event ? rowAtPoint(event.clientX, event.clientY) : null;
    const destination = target?.table === state.table ? target.position : state.to;
    const model = tableModels.find((item) => item.index === state.table);
    if (!model || destination === state.from) return;
    const rows = [...rowsForTable(model)];
    const [moved] = rows.splice(state.from, 1);
    if (moved !== undefined) {
      rows.splice(destination, 0, moved);
      setRowsForTable(model, rows);
    }
  };

  const updateValue = (key: string, value: string) => {
    setValues((current) => ({ ...current, [key]: value }));
    if (errors.has(key)) {
      setErrors((current) => {
        const next = new Set(current);
        next.delete(key);
        return next;
      });
    }
  };

  const applyPartySelection = (
    field: TemplateField,
    role: PartyAutoFillRole,
    entityName: string,
  ) => {
    const side = roleSide(role);
    const party = partyByName.get(
      `${side === "party_a" ? "甲方" : "乙方"}|${entityName}`,
    );
    setValues((current) => {
      const next = { ...current, [field.key]: entityName };
      if (party) {
        for (const other of template.fields) {
          const otherRole = resolveAutoFill(other);
          if (
            !otherRole ||
            !isPartyAutoFillRole(otherRole) ||
            otherRole === role ||
            roleAttribute(otherRole) === "name" ||
            roleSide(otherRole) !== side
          ) {
            continue;
          }
          next[other.key] = partyValueForRole(party, otherRole);
        }
      }
      return next;
    });
    setErrors((current) => {
      const next = new Set(current);
      next.delete(field.key);
      for (const other of template.fields) {
        const otherRole = resolveAutoFill(other);
        if (otherRole && isPartyAutoFillRole(otherRole) && roleSide(otherRole) === side) {
          next.delete(other.key);
        }
      }
      return next;
    });
    if (party) {
      message.success(`已带出${PARTY_SIDE_LABEL[side]}「${party.entity_name}」的主体信息`);
    }
  };

  const applyWarehouseSelection = (field: TemplateField, shortName: string) => {
    const warehouse = warehouseByName.get(shortName);
    setValues((current) => {
      const next = {
        ...current,
        [field.key]: warehouse ? warehouse.warehouse_address : shortName,
      };
      if (warehouse) {
        for (const other of template.fields) {
          if (resolveAutoFill(other) !== "warehouse_address") continue;
          next[other.key] = warehouse.warehouse_address;
        }
      }
      return next;
    });
    setErrors((current) => {
      const next = new Set(current);
      next.delete(field.key);
      for (const other of template.fields) {
        if (resolveAutoFill(other) === "warehouse_address") next.delete(other.key);
      }
      return next;
    });
    if (warehouse) {
      message.success(`已选择仓库「${warehouse.warehouse_short_name}」，正文将填充完整地址`);
    }
  };

  const handleFieldChange = (field: TemplateField, value: string) => {
    const role = resolveAutoFill(field);
    if (role === "warehouse_short_name") {
      applyWarehouseSelection(field, value);
      return;
    }
    if (role && isPartyAutoFillRole(role) && isPartyNameRole(role)) {
      applyPartySelection(field, role, value);
      return;
    }
    const nextValue =
      field.type === "number" || field.type === "currency"
        ? sanitizeNumericInput(value, numericInputOptions(field))
        : value;
    updateValue(field.key, nextValue);
  };

  const validate = (forSubmit: boolean) => {
    const next = new Set<string>();
    if (!title.trim()) next.add("__title__");
    const invalidFields = invalidFieldValues(template.fields, effectiveValues);
    invalidFields.forEach((item) => next.add(item.field.key));
    const missingFields = forSubmit ? missingRequiredFields(template.fields, effectiveValues) : [];
    missingFields.forEach((field) => next.add(field.key));
    setErrors(next);
    if (next.size) {
      message.error(
        next.has("__title__")
          ? "请填写合同名称"
          : invalidFields.length
            ? `${invalidFields[0].field.label}：${invalidFields[0].message}`
          : `还有 ${missingFields.length} 个必填项未完成，请补充后再提交`,
      );
      const firstKey = next.has("__title__")
        ? "__title__"
        : invalidFields[0]?.field.key || missingFields[0]?.key;
      if (firstKey) {
        document.getElementById(`field-${firstKey}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
      }
      return false;
    }
    return true;
  };

  const saveDraft = async () => {
    if (!validate(false)) return;
    setBusy("draft");
    try {
      await onSaveDraft(title.trim(), effectiveValues, tableAdjustments);
    } finally {
      setBusy(null);
    }
  };

  const submitForReview = () => {
    if (!validate(true)) return;
    Modal.confirm({
      title: "提交法务审核？",
      icon: <SendOutlined style={{ color: "#5A6A46" }} />,
      content: (
        <div className="confirm-copy">
          <p>提交后合同将进入法务审核队列，审核期间不能修改内容。</p>
          <div className="confirm-summary">
            <span>合同名称</span><strong>{title.trim()}</strong>
            <span>使用模板</span><strong>{template.name} · {template.version}</strong>
          </div>
        </div>
      ),
      okText: "确认提交",
      cancelText: "再检查一下",
      onOk: async () => {
        setBusy("submit");
        try {
          await onSubmitReview(title.trim(), effectiveValues, tableAdjustments);
        } finally {
          setBusy(null);
        }
      },
    });
  };

  return (
    <div className="composer">
      <div className="composer-grid">
        <div className="composer-form-column">
          {banner}
          <div className="panel template-brief">
            <div className="template-brief-head">
              <div className="template-brief-icon"><FileProtectOutlined /></div>
              <div className="template-brief-main">
                <div className="template-brief-tags">
                  <Tag>{template.category}</Tag>
                  <span>{template.version}</span>
                </div>
                <strong>{template.name}</strong>
                <p>{template.description}</p>
              </div>
              {onChangeTemplate && (
                <Button type="text" icon={<SwapOutlined />} onClick={onChangeTemplate}>
                  更换模板
                </Button>
              )}
            </div>
            {template.instructions && (
              <details className="instruction-details" open>
                <summary><InfoCircleOutlined /> 模板填写要求</summary>
                <div className="instruction-content">{template.instructions}</div>
              </details>
            )}
          </div>

          <div className="panel form-panel">
            <div className="form-panel-head">
              <div>
                <span className="panel-eyebrow">CONTRACT DETAILS</span>
                <h3>填写合同信息</h3>
              </div>
              <div className="completion-widget">
                <Progress
                  type="circle"
                  percent={completion}
                  size={48}
                  strokeWidth={8}
                  strokeColor="#1d9b74"
                  format={(percent) => <span className="completion-percent">{percent}%</span>}
                />
                <div>
                  <strong>必填项进度</strong>
                  <span>{completedRequired} / {requiredCount} 已完成</span>
                </div>
              </div>
            </div>

            <div className={`composer-field ${errors.has("__title__") ? "has-error" : ""}`} id="field-__title__">
              <label htmlFor="contract-title">
                合同名称 <em>*</em>
              </label>
              <Input
                id="contract-title"
                size="large"
                placeholder="请输入便于识别的合同名称，例如：2026 年度办公电脑采购合同"
                value={title}
                maxLength={200}
                showCount
                status={errors.has("__title__") ? "error" : undefined}
                onChange={(event) => {
                  setTitle(event.target.value);
                  if (errors.has("__title__")) {
                    setErrors((current) => {
                      const next = new Set(current);
                      next.delete("__title__");
                      return next;
                    });
                  }
                }}
              />
              <div className="field-help">该名称会显示在合同列表、审核工作台和 PDF 文件标题中。</div>
            </div>

            <div className="form-divider"><span>模板空白项</span><small>{template.fields.length} 个字段</small></div>

            {hasPartyFields && partyError && (
              <Alert
                type="warning"
                showIcon
                className="party-source-alert"
                message="主体信息库暂时不可用"
                description={partyError}
              />
            )}
            {hasWarehouseFields && warehouseError && (
              <Alert
                type="warning"
                showIcon
                className="party-source-alert"
                message="仓库信息库暂时不可用"
                description={warehouseError}
              />
            )}

            {template.fields.length ? (
              <div className="dynamic-fields">
                {template.fields.map((field, index) => (
                  <FieldControl
                    key={field.key}
                    field={field}
                    index={index}
                    value={effectiveValues[field.key] || ""}
                    error={errors.has(field.key)}
                    parties={parties}
                    partyLoading={partyLoading}
                    partyError={!!partyError}
                    warehouses={warehouses}
                    warehouseLoading={warehouseLoading}
                    warehouseError={!!warehouseError}
                    autoKind={
                      autoKindForField(field.key) ??
                      (uppercaseSources[field.key] ? "upper" : null)
                    }
                    onChange={(value) => handleFieldChange(field, value)}
                  />
                ))}
              </div>
            ) : (
              <Alert type="warning" showIcon message="该模板尚未配置可填写的空白项，请联系法务维护模板。" />
            )}

            {tableModels.length > 0 && (
              <>
                <div className="form-divider">
                  <span>表格行调整</span>
                  <small>{tableModels.length} 张表格 · 可增删、拖拽排序</small>
                </div>
                <div className="contract-table-editor">
                  <div className="contract-table-editor-note">
                    <TableOutlined />
                    <span>
                      表格列与表头由法务锁定。新增正文行可直接填写各列内容；拖拽左侧行号图标可调整行顺序。
                      {tableModels.some((model) => model.columnRoles.sequence !== null) &&
                        " 序号列会按数据行顺序自动生成。"}
                      {tableModels.some(
                        (model) =>
                          model.columnRoles.quantity !== null &&
                          model.columnRoles.unitPrice !== null &&
                          model.columnRoles.total !== null,
                      ) && " 含数量、单价和总额列时，行总额会按单价 × 数量自动计算并锁定；合计行会按所有行的总额自动累加并生成大写金额。"}
                    </span>
                  </div>
                  {tableModels.map((model) => {
                    const rows = rowsForTable(model);
                    return (
                      <div className="contract-table-card" key={model.index}>
                        <div className="contract-table-card-head">
                          <div>
                            <strong>表格 {model.index + 1}</strong>
                            <span>表头 {model.headerCount} 行 · 正文 {rows.length} 行</span>
                          </div>
                          <Button size="small" icon={<PlusOutlined />} onClick={() => addTableRow(model)}>
                            添加一行
                          </Button>
                        </div>
                        <div className="contract-table-row-list">
                          {rows.map((source, position) => {
                            const isNew = isNewContractTableRow(source);
                            const isDropTarget =
                              dropTarget?.table === model.index && dropTarget.position === position;
                            const isDragging =
                              draggedRow?.table === model.index && draggedRow.position === position;
                            const rowKey = isNew
                              ? source.id
                              : `${model.index}-original-${String(source)}`;
                            return (
                              <div
                                className={[
                                  "contract-table-row-item",
                                  isNew ? "is-new" : "",
                                  isDropTarget ? "is-drop-target" : "",
                                  isDragging ? "is-dragging" : "",
                                ].filter(Boolean).join(" ")}
                                key={rowKey}
                                data-table-row
                                data-table-index={model.index}
                                data-row-position={position}
                              >
                                <span
                                  className="contract-table-row-no"
                                  title="拖拽行号调整顺序"
                                  aria-label={`第 ${position + 1} 行，拖拽调整顺序`}
                                  onPointerDown={(event) => startRowDrag(event, model, position)}
                                  onPointerMove={moveRowDrag}
                                  onPointerUp={(event) => finishRowDrag(event)}
                                  onPointerCancel={() => finishRowDrag()}
                                >
                                  {position + 1}
                                </span>
                                {isNew ? (
                                  <div className="contract-table-new-cells">
                                    {Array.from({ length: model.columnCount }, (_, cellIndex) => {
                                      const calculatedSequence =
                                        model.columnRoles.sequence === cellIndex;
                                      const calculatedTotal =
                                        model.columnRoles.total === cellIndex &&
                                        model.columnRoles.quantity !== null &&
                                        model.columnRoles.unitPrice !== null;
                                      return (
                                        <Input
                                          key={cellIndex}
                                          size="small"
                                          value={source.cells[cellIndex] || ""}
                                          placeholder={
                                            calculatedSequence
                                              ? "自动生成"
                                              : calculatedTotal
                                                ? "自动计算"
                                                : model.columnLabels[cellIndex]
                                          }
                                          aria-label={`${model.columnLabels[cellIndex]}，第 ${position + 1} 行`}
                                          maxLength={500}
                                          readOnly={calculatedSequence || calculatedTotal}
                                          onChange={(event) =>
                                            updateTableRowCell(
                                              model,
                                              position,
                                              cellIndex,
                                              event.target.value,
                                            )
                                          }
                                        />
                                      );
                                    })}
                                  </div>
                                ) : (
                                  <span className="contract-table-row-label">
                                    {model.rowLabels[source as number] || "空白行"}
                                  </span>
                                )}
                                {isNew ? (
                                  <Button
                                    type="text"
                                    danger
                                    size="small"
                                    icon={<DeleteOutlined />}
                                    disabled={rows.length <= 1}
                                    onClick={() => removeTableRow(model, position)}
                                  >
                                    删除
                                  </Button>
                                ) : (
                                  <span className="contract-table-row-locked">模板行</span>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            )}

            <div className="composer-actions">
              <div className="composer-actions-note">
                <CheckCircleFilled />
                <span>内容自动保留在当前页面，提交前可随时预览</span>
              </div>
              <div className="composer-actions-buttons">
                {backAction}
                <Button
                  size="large"
                  icon={<SaveOutlined />}
                  loading={busy === "draft"}
                  disabled={busy === "submit"}
                  onClick={saveDraft}
                >
                  保存草稿
                </Button>
                <Button
                  type="primary"
                  size="large"
                  icon={<SendOutlined />}
                  loading={busy === "submit"}
                  disabled={busy === "draft"}
                  onClick={submitForReview}
                >
                  提交法务审核
                </Button>
              </div>
            </div>
          </div>
        </div>

        <aside className="preview-column">
          <div className="preview-toolbar">
            <div>
              <span className="panel-eyebrow">LIVE PREVIEW</span>
              <h3>合同预览</h3>
            </div>
            <Tag color="blue" bordered={false}>实时生成</Tag>
          </div>
          <div className="preview-note">
            <EditOutlined />
            空白项会以蓝色标记；表格正文行可在左侧增删，预览会实时同步。
          </div>
          <div className="paper-scroll">
            <ContractPaper
              title={title.trim() || "未命名合同"}
              content={template.content}
              values={effectiveValues}
              fields={template.fields}
              tableAdjustments={tableAdjustments}
              contractNo={contractNo}
              templateName={`${template.name} · ${template.version}`}
              compact
            />
          </div>
        </aside>
      </div>
    </div>
  );
}

function FieldControl({
  field,
  index,
  value,
  error,
  parties,
  partyLoading,
  partyError,
  warehouses,
  warehouseLoading,
  warehouseError,
  autoKind,
  onChange,
}: {
  field: TemplateField;
  index: number;
  value: string;
  error: boolean;
  parties: PartyInfo[];
  partyLoading: boolean;
  partyError: boolean;
  warehouses: WarehouseInfo[];
  warehouseLoading: boolean;
  warehouseError: boolean;
  autoKind: AutoAmountFieldKind | null;
  onChange: (value: string) => void;
}) {
  const autoRole = resolveAutoFill(field);
  const partyRole = autoRole && isPartyAutoFillRole(autoRole) ? autoRole : "";
  const partyNameRole = !!partyRole && isPartyNameRole(partyRole);
  const warehouseNameRole = autoRole === "warehouse_short_name";
  const warehouseAddressRole = autoRole === "warehouse_address";
  const expectedPartyType =
    partyRole && roleSide(partyRole as PartyAutoFillRole) === "party_a"
      ? "甲方"
      : partyRole
        ? "乙方"
        : "";
  const partyOptions = expectedPartyType
    ? parties.filter((party) => (party.party_type || "甲方") === expectedPartyType)
    : parties;
  const warehouseLookup = value.trim();
  const selectedWarehouse = warehouseNameRole
    ? warehouses.find(
        (warehouse) =>
          warehouse.warehouse_short_name === warehouseLookup ||
          warehouse.warehouse_address === warehouseLookup,
      )
    : undefined;
  const warehouseSelectValue = selectedWarehouse?.warehouse_short_name;
  const dateValue = field.type === "date" ? normalizeDateValue(value) : "";
  const valueError = fieldValueProblem(field, value);
  const canUsePartySelect =
    partyNameRole && !partyError && (partyLoading || partyOptions.length > 0);
  const warehouseDirectoryAvailable =
    !warehouseError && (warehouseLoading || warehouses.length > 0);
  const canUseWarehouseSelect = warehouseNameRole && warehouseDirectoryAvailable;
  const commonProps = {
    status: error ? ("error" as const) : undefined,
    placeholder: field.placeholder || `请输入${field.label}`,
    value,
    readOnly: !!autoKind,
    onChange: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => onChange(event.target.value),
  };

  return (
    <div className={`composer-field ${error ? "has-error" : ""}`} id={`field-${field.key}`}>
      <label htmlFor={`input-${field.key}`}>
        <span className="field-index">{String(index + 1).padStart(2, "0")}</span>
        {field.label}
        {field.required ? <em>*</em> : <small>选填</small>}
        <span className="field-type-chip">
          {autoKind
            ? autoKind === "total"
              ? "自动合计"
              : autoKind === "prepayment" || autoKind === "final"
                ? "自动计算"
                : "自动生成"
            : warehouseNameRole
              ? "仓库下拉"
              : warehouseAddressRole
                ? "仓库带出"
                : partyNameRole
                  ? "主体库下拉"
                  : partyRole
                    ? "主体库带出"
                    : fieldTypeLabel(field.type)}
        </span>
      </label>
      {warehouseNameRole ? (
        canUseWarehouseSelect ? (
          <Select
            id={`input-${field.key}`}
            size="large"
            value={warehouseSelectValue}
            placeholder={field.placeholder || `请选择${field.label}`}
            options={warehouses.map((warehouse) => ({
              label: warehouse.warehouse_short_name,
              value: warehouse.warehouse_short_name,
            }))}
            loading={warehouseLoading}
            onChange={onChange}
            status={error ? "error" : undefined}
            showSearch
            optionFilterProp="label"
          />
        ) : (
          <Input
            id={`input-${field.key}`}
            size="large"
            maxLength={200}
            {...commonProps}
            placeholder={
              warehouseLoading
                ? "正在加载仓库信息…"
                : warehouseError
                  ? "仓库信息库暂不可用，可手动填写仓库简称"
                  : "仓库暂无数据，请手动输入仓库简称"
            }
          />
        )
      ) : partyNameRole ? (
        canUsePartySelect ? (
          <Select
            id={`input-${field.key}`}
            size="large"
            value={value || undefined}
            placeholder={field.placeholder || `请选择${field.label}`}
            options={partyOptions.map((party) => ({ label: party.entity_name, value: party.entity_name }))}
            loading={partyLoading}
            onChange={onChange}
            status={error ? "error" : undefined}
            showSearch
            optionFilterProp="label"
          />
        ) : (
          <Input
            id={`input-${field.key}`}
            size="large"
            maxLength={500}
            {...commonProps}
            placeholder={
              partyLoading
                ? "正在加载主体信息…"
                : partyError
                  ? "主体信息库暂不可用，可手动填写主体名称"
                  : `${expectedPartyType || "主体"}库暂无数据，请手动输入主体名称`
            }
          />
        )
      ) : warehouseAddressRole ? (
        <Input
          id={`input-${field.key}`}
          size="large"
          maxLength={500}
          {...commonProps}
          readOnly={warehouseDirectoryAvailable}
          placeholder={
            warehouseLoading
              ? "正在加载仓库信息…"
              : warehouseError
                ? "仓库信息库暂不可用，可手动填写仓库地址"
                : "请先选择仓库简称"
          }
        />
      ) : partyRole ? (
        <Input id={`input-${field.key}`} size="large" maxLength={500} {...commonProps} />
      ) : field.type === "textarea" ? (
        <Input.TextArea
          id={`input-${field.key}`}
          autoSize={{ minRows: 3, maxRows: 8 }}
          maxLength={4000}
          showCount
          {...commonProps}
        />
      ) : field.type === "select" ? (
        <Select
          id={`input-${field.key}`}
          size="large"
          value={value || undefined}
          placeholder={field.placeholder || `请选择${field.label}`}
          options={field.options.map((option) => ({ label: option, value: option, title: option }))}
          onChange={onChange}
          status={error ? "error" : undefined}
          popupMatchSelectWidth={false}
          classNames={{ popup: { root: "contract-option-dropdown" } }}
          showSearch
          optionFilterProp="label"
        />
      ) : field.type === "date" ? (
        <DatePicker
          id={`input-${field.key}`}
          size="large"
          className="date-control"
          style={{ width: "100%" }}
          value={dateValue ? dayjs(dateValue) : null}
          format="YYYY年MM月DD日"
          inputReadOnly
          placeholder={field.placeholder || `请选择${field.label}`}
          onChange={(date) => onChange(date ? date.format("YYYY-MM-DD") : "")}
          status={error ? "error" : undefined}
          allowClear
        />
      ) : field.type === "currency" ? (
        <Input
          id={`input-${field.key}`}
          size="large"
          prefix="¥"
          suffix="CNY"
          inputMode="decimal"
          autoComplete="off"
          {...commonProps}
          placeholder={field.placeholder || `请输入${field.label}（仅限数字）`}
        />
      ) : field.type === "number" ? (
        <Input
          id={`input-${field.key}`}
          size="large"
          inputMode="decimal"
          autoComplete="off"
          {...commonProps}
          placeholder={field.placeholder || `请输入${field.label}（仅限数字）`}
        />
      ) : (
        <Input id={`input-${field.key}`} size="large" maxLength={500} {...commonProps} />
      )}
      {warehouseNameRole && selectedWarehouse && (
        <div className="party-source-card">
          <div className="party-source-card-head">
            <CheckCircleFilled /> 已选择仓库，正文将填充完整地址
          </div>
          <div className="party-source-grid">
            <div>
              <span>仓库简称</span>
              <strong>{selectedWarehouse.warehouse_short_name}</strong>
            </div>
            <div>
              <span>仓库地址</span>
              <strong>{selectedWarehouse.warehouse_address || "—"}</strong>
            </div>
          </div>
        </div>
      )}
      {autoKind ? (
        <div className="field-help auto-field-help">
          {autoKind === "total"
            ? "由表格「总额（元）」列中所有行自动求和，无需手动填写。"
            : "根据对应小写金额自动生成人民币大写，无需手动填写。"}
        </div>
      ) : warehouseAddressRole ? (
        <div className="field-help">
          {warehouseError
            ? "仓库信息库暂不可用，请手动填写仓库地址。"
            : "选择仓库简称后自动带出仓库地址，无需手动填写。"}
        </div>
      ) : field.hint ? (
        <div className={`field-help ${error ? "error-help" : ""}`}>
          {error ? valueError || "该项为必填内容，请完成填写。" : field.hint}
        </div>
      ) : null}
      {error && !autoKind && !field.hint && (
        <div className="field-help error-help">
          {valueError || "该项为必填内容，请完成填写。"}
        </div>
      )}
    </div>
  );
}
