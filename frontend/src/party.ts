import type {
  AutoFillRole,
  PartyAttribute,
  PartyAutoFillRole,
  PartyInfo,
  PartySide,
  TemplateField,
  WarehouseAutoFillRole,
} from "./types";

interface PartyAttributeMeta {
  attribute: PartyAttribute;
  field: keyof PartyInfo;
  label: string;
}

export const PARTY_ATTRIBUTE_META: PartyAttributeMeta[] = [
  { attribute: "name", field: "entity_name", label: "主体名称" },
  { attribute: "credit_code", field: "unified_social_credit_code", label: "统一社会信用代码" },
  { attribute: "account_name", field: "account_name", label: "户名" },
  { attribute: "bank_name", field: "bank_name", label: "开户行" },
  { attribute: "bank_branch_code", field: "bank_branch_code", label: "行号" },
  { attribute: "tax_number", field: "tax_number", label: "税号" },
  { attribute: "contact_address", field: "contact_address", label: "联系地址" },
  { attribute: "contact_phone", field: "contact_phone", label: "联系方式" },
];

export const PARTY_SIDE_LABEL: Record<PartySide, string> = {
  party_a: "甲方",
  party_b: "乙方",
};

export const AUTO_FILL_OPTIONS = [
  { label: "手动填写", value: "" },
  {
    label: "甲方主体",
    options: PARTY_ATTRIBUTE_META.map((item) => ({
      label: item.attribute === "name" ? "主体名称（下拉选择）" : item.label,
      value: `party_a_${item.attribute}`,
    })),
  },
  {
    label: "乙方主体",
    options: PARTY_ATTRIBUTE_META.map((item) => ({
      label: item.attribute === "name" ? "主体名称（下拉选择）" : item.label,
      value: `party_b_${item.attribute}`,
    })),
  },
  {
    label: "仓库信息",
    options: [
      { label: "仓库简称（下拉选择并填充地址）", value: "warehouse_short_name" },
      { label: "仓库地址（随仓库简称带出）", value: "warehouse_address" },
    ],
  },
];

const SYSTEM_PARTY_FIELD_KEYS: Record<PartySide, Record<PartyAttribute, string>> = {
  party_a: {
    name: "甲方",
    credit_code: "甲方信用代码",
    account_name: "甲方户名",
    bank_name: "甲方开户行",
    bank_branch_code: "甲方行号",
    tax_number: "甲方税号",
    contact_address: "甲方地址",
    contact_phone: "甲方联系人",
  },
  party_b: {
    name: "乙方",
    credit_code: "乙方信用代码",
    account_name: "乙方户名",
    bank_name: "乙方开户行",
    bank_branch_code: "乙方行号",
    tax_number: "乙方税号",
    contact_address: "乙方地址",
    contact_phone: "乙方联系人",
  },
};

export const SYSTEM_PARTY_FIELDS: Array<{
  side: PartySide;
  attribute: PartyAttribute;
  role: PartyAutoFillRole;
  key: string;
  label: string;
  required: boolean;
  hint: string;
}> = (["party_a", "party_b"] as PartySide[]).flatMap((side) =>
  PARTY_ATTRIBUTE_META.map((item) => {
    const sideLabel = PARTY_SIDE_LABEL[side];
    const role = `${side}_${item.attribute}` as PartyAutoFillRole;
    return {
      side,
      attribute: item.attribute,
      role,
      key: SYSTEM_PARTY_FIELD_KEYS[side][item.attribute],
      label: item.attribute === "name" ? `${sideLabel}名称` : `${sideLabel}${item.label}`,
      required: item.attribute === "name",
      hint:
        item.attribute === "name"
          ? `从${sideLabel}主体库选择主体，系统会自动带出其余${sideLabel}信息。`
          : `选择${sideLabel}主体后自动带出${item.label}，无需重复填写。`,
    };
  }),
);

const PARTY_ROLES = new Set<string>(
  (["party_a", "party_b"] as PartySide[]).flatMap((side) =>
    PARTY_ATTRIBUTE_META.map((item) => `${side}_${item.attribute}`),
  ),
);

const WAREHOUSE_ROLES = new Set<string>(["warehouse_short_name", "warehouse_address"]);

const SIDE_PATTERNS: { side: PartySide; pattern: RegExp }[] = [
  { side: "party_a", pattern: /party_a|甲方|采购方|委托方|发包方|出租方|许可方/ },
  { side: "party_b", pattern: /party_b|乙方|供应方|服务方|承包方|承租方|被许可方/ },
];

const ATTRIBUTE_PATTERNS: { attribute: PartyAttribute; pattern: RegExp }[] = [
  { attribute: "credit_code", pattern: /统一社会信用代码|社会信用代码|信用代码|credit_code|creditcode/ },
  { attribute: "tax_number", pattern: /纳税人识别号|税号|tax_number|taxno/ },
  { attribute: "bank_name", pattern: /开户行|开户银行|bank_name|bankname/ },
  { attribute: "bank_branch_code", pattern: /联行号|银行行号|行号|bank_branch|branch_code/ },
  { attribute: "account_name", pattern: /户名|账户名|account_name|accountname/ },
  { attribute: "contact_address", pattern: /联系地址|注册地址|地址|address/ },
  { attribute: "contact_phone", pattern: /联系方式|联系电话|电话|手机|contact_phone|phone|mobile/ },
  { attribute: "name", pattern: /主体名称|名称|全称|name/ },
];

export function isPartyAutoFillRole(value: string | undefined): value is PartyAutoFillRole {
  return !!value && PARTY_ROLES.has(value);
}

export function isWarehouseAutoFillRole(
  value: string | undefined,
): value is WarehouseAutoFillRole {
  return !!value && WAREHOUSE_ROLES.has(value);
}

export function isAutoFillRole(value: string | undefined): value is AutoFillRole {
  return isPartyAutoFillRole(value) || isWarehouseAutoFillRole(value);
}

export function roleSide(role: PartyAutoFillRole): PartySide {
  return role.startsWith("party_a_") ? "party_a" : "party_b";
}

export function roleAttribute(role: PartyAutoFillRole): PartyAttribute {
  return role.slice(role.indexOf("_", role.indexOf("_") + 1) + 1) as PartyAttribute;
}

export function isPartyNameRole(role: PartyAutoFillRole | ""): boolean {
  return !!role && roleAttribute(role) === "name";
}

export function partyValueForRole(party: PartyInfo, role: PartyAutoFillRole): string {
  const attribute = roleAttribute(role);
  const meta = PARTY_ATTRIBUTE_META.find((item) => item.attribute === attribute);
  return meta ? String(party[meta.field] || "") : "";
}

export function inferPartyAutoFill(field: TemplateField): PartyAutoFillRole | "" {
  if (field.auto_fill !== undefined) {
    return isPartyAutoFillRole(field.auto_fill) ? field.auto_fill : "";
  }
  const text = `${field.key} ${field.label}`.toLowerCase();
  const matchedSides = SIDE_PATTERNS.filter((item) => item.pattern.test(text));
  if (matchedSides.length !== 1) return "";
  const attribute = ATTRIBUTE_PATTERNS.find((item) => item.pattern.test(text))?.attribute;
  if (!attribute) return "";
  if (attribute === "name") {
    const key = field.key.trim().toLowerCase();
    const label = field.label.trim().replace(/\s+/g, "");
    const exactName =
      /^party_[ab](_name)?$/.test(key) ||
      /^(甲方|乙方)(（[^）]{0,10}）)?(主体)?(名称|全称)?$/.test(label);
    if (!exactName) return "";
  }
  return `${matchedSides[0].side}_${attribute}` as PartyAutoFillRole;
}

export function resolveAutoFill(field: TemplateField): AutoFillRole | "" {
  const text = `${field.key} ${field.label}`.toLowerCase();
  const warehouseNameField = /仓库简称|仓库名称/.test(text);
  if (
    warehouseNameField &&
    (field.auto_fill === undefined || field.auto_fill === "warehouse_address")
  ) {
    return "warehouse_short_name";
  }
  if (field.auto_fill !== undefined) {
    return isAutoFillRole(field.auto_fill) ? field.auto_fill : "";
  }
  if (warehouseNameField) return "warehouse_short_name";
  if (/仓库地址|收货地址|发货地址|交货地址/.test(text)) return "warehouse_address";
  if (/仓库简称|仓库名称/.test(text)) return "warehouse_short_name";
  if (/^仓库$/.test(field.key.trim()) || /^仓库(（[^）]*）)?$/.test(field.label.trim())) {
    return "warehouse_short_name";
  }
  return inferPartyAutoFill(field);
}

export function normalizeAutoFill(field: TemplateField): AutoFillRole | "" {
  const resolved = resolveAutoFill(field);
  if (field.auto_fill === undefined) return resolved;
  if (resolved === "warehouse_short_name" && field.auto_fill === "warehouse_address") {
    return resolved;
  }
  return isAutoFillRole(field.auto_fill) ? field.auto_fill : "";
}

export function isSystemPartyField(field: TemplateField): boolean {
  return isPartyAutoFillRole(resolveAutoFill(field));
}

export function ensureSystemPartyFields(fields: TemplateField[]): TemplateField[] {
  const existingKeys = new Set(fields.map((field) => field.key));
  const result = fields.map((field) => {
    const role = resolveAutoFill(field);
    if (isPartyAutoFillRole(role) && field.auto_fill !== role) {
      return { ...field, auto_fill: role };
    }
    return field;
  });
  const existingRoles = new Set(
    result
      .map((field) => resolveAutoFill(field))
      .filter((role): role is PartyAutoFillRole => isPartyAutoFillRole(role)),
  );

  for (const definition of SYSTEM_PARTY_FIELDS) {
    if (existingRoles.has(definition.role)) continue;
    let key = definition.key;
    let suffix = 2;
    while (existingKeys.has(key)) {
      key = `${definition.key}${suffix}`;
      suffix += 1;
    }
    existingKeys.add(key);
    existingRoles.add(definition.role);
    result.push({
      key,
      label: definition.label,
      type: "text",
      required: definition.required,
      hint: definition.hint,
      placeholder: "",
      options: [],
      auto_fill: definition.role,
    });
  }
  return result;
}
