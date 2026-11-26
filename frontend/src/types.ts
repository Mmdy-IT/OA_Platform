export type Role = "admin" | "legal" | "business";
export type PermissionKey = "dashboard" | "contracts" | "reviews" | "templates";

export interface User {
  id: number;
  username: string;
  display_name: string;
  role: Role;
  department: string;
  job_title: string;
  permissions: PermissionKey[];
}

export interface PermissionModule {
  key: PermissionKey;
  label: string;
  group: string;
  description: string;
}

export interface UserPermissionRecord {
  id: number;
  oa_user_id: number | null;
  union_id: string;
  username: string;
  display_name: string;
  role: Role;
  department: string;
  permissions: PermissionKey[];
  updated_at: string;
}

export type TemplateFieldType =
  | "text"
  | "textarea"
  | "date"
  | "number"
  | "currency"
  | "select";

export type PartySide = "party_a" | "party_b";

export type PartyAttribute =
  | "name"
  | "credit_code"
  | "account_name"
  | "bank_name"
  | "bank_branch_code"
  | "tax_number"
  | "contact_address"
  | "contact_phone";

export type PartyAutoFillRole = `${PartySide}_${PartyAttribute}`;
export type WarehouseAutoFillRole = "warehouse_short_name" | "warehouse_address";
export type AutoFillRole = PartyAutoFillRole | WarehouseAutoFillRole;

export interface PartyInfo {
  entity_name: string;
  unified_social_credit_code: string;
  account_name: string;
  bank_name: string;
  bank_branch_code: string;
  tax_number: string;
  contact_address: string;
  contact_phone: string;
}

export interface WarehouseInfo {
  warehouse_short_name: string;
  warehouse_address: string;
}

export interface TemplateField {
  key: string;
  label: string;
  type: TemplateFieldType;
  required: boolean;
  hint: string;
  placeholder: string;
  options: string[];
  auto_fill?: AutoFillRole | "";
}

export interface Template {
  id: number;
  name: string;
  contract_code: string;
  category: string;
  description: string;
  instructions: string;
  content: string;
  fields: TemplateField[];
  version: string;
  status: "active" | "archived";
  created_by: number;
  created_at: string;
  updated_at: string;
  creator_name: string;
  usage_count: number;
}

export type ContractStatus = "draft" | "pending" | "approved" | "rejected";

export interface ContractTableNewRow {
  id: string;
  cells: string[];
}

export type ContractTableRow = number | null | ContractTableNewRow;
export type ContractTableAdjustments = Record<string, ContractTableRow[]>;

export interface ContractSummary {
  id: number;
  contract_no: string;
  contract_code: string;
  title: string;
  template_name: string;
  template_version: string;
  status: ContractStatus;
  creator_id: number;
  creator_name: string;
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
  reviewed_at: string | null;
  review_comment: string;
}

export interface ContractEvent {
  id: number;
  action: string;
  actor_name: string;
  from_status: string | null;
  to_status: string | null;
  comment: string;
  created_at: string;
}

export interface Contract extends ContractSummary {
  template_id: number;
  template_content: string;
  fields_schema: TemplateField[];
  field_values: Record<string, string>;
  table_adjustments: ContractTableAdjustments;
  creator_id: number;
  reviewer_name: string | null;
  events: ContractEvent[];
}

export interface DashboardData {
  scope: "mine" | "all";
  stats: {
    total: number;
    draft: number;
    pending: number;
    approved: number;
    rejected: number;
    templates: number;
  };
  recent_contracts: ContractSummary[];
  pending_contracts: ContractSummary[];
}

export type NotificationKind = "review" | "rejected" | "approved";

export interface NotificationItem {
  id: string;
  kind: NotificationKind;
  title: string;
  description: string;
  contract_id: number;
  contract_no: string;
  status: ContractStatus;
  created_at: string;
}

export interface ListResponse<T> {
  items: T[];
  total: number;
}

export interface TemplatePayload {
  name: string;
  contract_code: string;
  category: string;
  description: string;
  instructions: string;
  content: string;
  fields: TemplateField[];
}

export interface TemplateImportDraft {
  name: string;
  contract_code: string;
  category: string;
  description: string;
  instructions: string;
  content: string;
  fields: TemplateField[];
  source: {
    filename: string;
    type: "docx" | "pdf";
    warnings: string[];
    placeholder_count: number;
  };
}

export interface ContractPayload {
  template_id: number;
  title: string;
  field_values: Record<string, string>;
  table_adjustments?: ContractTableAdjustments;
}
