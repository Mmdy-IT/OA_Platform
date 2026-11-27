import type {
  Contract,
  ContractAttachment,
  BundleRule,
  BundleRulePayload,
  BundleRequirement,
  ContractTableAdjustments,
  ContractPayload,
  ContractSummary,
  DashboardData,
  ListResponse,
  NotificationItem,
  PartyInfo,
  PermissionKey,
  PermissionModule,
  PermissionRequestRecord,
  Template,
  TemplateImportDraft,
  TemplatePayload,
  User,
  UserPermissionRecord,
  WarehouseInfo,
} from "./types";

export class ApiError extends Error {
  status: number;
  fields?: string[];

  constructor(message: string, status: number, fields?: string[]) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fields = fields;
  }
}

function extractError(payload: unknown): { message: string; fields?: string[] } {
  if (typeof payload === "string") return { message: payload };
  if (payload && typeof payload === "object") {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string") return { message: detail };
    if (Array.isArray(detail)) {
      const first = detail[0] as { msg?: string } | undefined;
      return { message: first?.msg || "请求参数有误" };
    }
    if (detail && typeof detail === "object") {
      const value = detail as { message?: string; fields?: string[] };
      return {
        message: value.message || "请求处理失败",
        fields: value.fields,
      };
    }
  }
  return { message: "请求处理失败，请稍后重试" };
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`/api${path}`, {
    ...options,
    headers,
    credentials: "include",
  });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const error = extractError(payload);
    throw new ApiError(error.message, response.status, error.fields);
  }
  return payload as T;
}

export const api = {
  login: (username: string, password: string) =>
    request<{ user: User }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  feishuConfig: () => request<{ enabled: boolean }>("/auth/feishu/config"),
  logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }),
  me: () => request<{ user: User }>("/auth/me"),
  dashboard: () => request<DashboardData>("/dashboard"),
  notifications: () =>
    request<{ items: NotificationItem[]; unread_count: number }>("/notifications"),
  parties: (q = "", partyType = "") => {
    const search = new URLSearchParams();
    if (q) search.set("q", q);
    if (partyType) search.set("party_type", partyType);
    const suffix = search.toString();
    return request<{ items: PartyInfo[] }>(`/parties${suffix ? `?${suffix}` : ""}`);
  },
  createParty: (payload: PartyInfo) =>
    request<PartyInfo>("/parties", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateParty: (creditCode: string, payload: PartyInfo) =>
    request<PartyInfo>(`/parties/${encodeURIComponent(creditCode)}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  warehouses: () => request<{ items: WarehouseInfo[] }>("/warehouses"),

  adminPermissions: () =>
    request<{ modules: PermissionModule[]; items: UserPermissionRecord[] }>("/admin/permissions"),
  updateUserPermission: (
    id: number,
    payload: { permissions: PermissionKey[]; union_id: string },
  ) =>
    request<UserPermissionRecord>(`/admin/permissions/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  permissionRequests: () =>
    request<{
      items: PermissionRequestRecord[];
      modules: PermissionModule[];
      can_approve: boolean;
    }>("/permission-requests"),
  createPermissionRequest: (payload: { permissions: PermissionKey[]; reason: string }) =>
    request<PermissionRequestRecord>("/permission-requests", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  reviewPermissionRequest: (
    id: number,
    payload: { decision: "approve" | "reject"; comment: string },
  ) =>
    request<PermissionRequestRecord>(`/permission-requests/${id}/review`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  templates: (params?: { q?: string; status?: string }) => {
    const search = new URLSearchParams();
    if (params?.q) search.set("q", params.q);
    if (params?.status) search.set("status", params.status);
    const query = search.toString();
    return request<ListResponse<Template>>(`/templates${query ? `?${query}` : ""}`);
  },
  templateCategories: () => request<{ items: string[] }>("/template-categories"),
  template: (id: number | string) => request<Template>(`/templates/${id}`),
  createTemplate: (payload: TemplatePayload) =>
    request<Template>("/templates", { method: "POST", body: JSON.stringify(payload) }),
  updateTemplate: (id: number | string, payload: TemplatePayload) =>
    request<Template>(`/templates/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  importTemplate: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<TemplateImportDraft>("/templates/import", {
      method: "POST",
      body: form,
    });
  },
  archiveTemplate: (id: number | string) =>
    request<{ ok: boolean; message: string }>(`/templates/${id}`, { method: "DELETE" }),
  permanentlyDeleteTemplate: (id: number | string) =>
    request<{ ok: boolean; message: string }>(`/templates/${id}/permanent`, {
      method: "DELETE",
    }),

  contracts: (params?: { q?: string; status?: string; template_id?: number; scope?: "mine" | "all" }) => {
    const search = new URLSearchParams();
    if (params?.q) search.set("q", params.q);
    if (params?.status) search.set("status", params.status);
    if (params?.template_id) search.set("template_id", String(params.template_id));
    if (params?.scope) search.set("scope", params.scope);
    const query = search.toString();
    return request<ListResponse<ContractSummary>>(`/contracts${query ? `?${query}` : ""}`);
  },
  contract: (id: number | string) => request<Contract>(`/contracts/${id}`),
  createContract: (payload: ContractPayload) =>
    request<Contract>("/contracts", { method: "POST", body: JSON.stringify(payload) }),
  createContractBundle: (payload: ContractPayload) =>
    request<Contract>("/contracts/bundle", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  ensureBundleCompanions: (id: number | string) =>
    request<{
      created_contract_ids: number[];
      next_contract_id: number | null;
      contract: Contract;
    }>(`/contracts/${id}/bundle-companions`, { method: "POST" }),
  bundleRequirements: (templateId: number) =>
    request<{ items: BundleRequirement[] }>(
      `/bundle-requirements?template_id=${templateId}`,
    ),
  bundleRules: () => request<{ items: BundleRule[] }>("/bundle-rules"),
  createBundleRule: (payload: BundleRulePayload) =>
    request<BundleRule>("/bundle-rules", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateBundleRule: (id: number, payload: BundleRulePayload) =>
    request<BundleRule>(`/bundle-rules/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  deleteBundleRule: (id: number) =>
    request<{ ok: boolean }>(`/bundle-rules/${id}`, { method: "DELETE" }),
  updateContract: (
    id: number | string,
    payload: {
      title: string;
      field_values: Record<string, string>;
      table_adjustments?: ContractTableAdjustments;
    },
  ) =>
    request<Contract>(`/contracts/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  submitContract: (id: number | string) =>
    request<Contract>(`/contracts/${id}/submit`, { method: "POST" }),
  withdrawContract: (id: number | string) =>
    request<Contract>(`/contracts/${id}/withdraw`, { method: "POST" }),
  reviewContract: (
    id: number | string,
    payload: { decision: "approve" | "reject"; comment: string },
  ) =>
    request<Contract>(`/contracts/${id}/review`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deleteContract: (id: number | string) =>
    request<{ ok: boolean }>(`/contracts/${id}`, { method: "DELETE" }),
  contractAttachments: (id: number | string) =>
    request<{ items: ContractAttachment[] }>(`/contracts/${id}/attachments`),
  uploadContractAttachments: (id: number | string, files: File[]) => {
    const form = new FormData();
    for (const file of files) form.append("files", file);
    return request<{ items: ContractAttachment[] }>(`/contracts/${id}/attachments`, {
      method: "POST",
      body: form,
    });
  },
  deleteContractAttachment: (id: number) =>
    request<{ ok: boolean }>(`/attachments/${id}`, { method: "DELETE" }),
  downloadContractAttachment: async (attachment: ContractAttachment) => {
    const response = await fetch(`/api/attachments/${attachment.id}/download`, {
      credentials: "include",
    });
    if (!response.ok) {
      const contentType = response.headers.get("content-type") || "";
      const payload = contentType.includes("application/json")
        ? await response.json()
        : await response.text();
      const error = extractError(payload);
      throw new ApiError(error.message, response.status, error.fields);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = attachment.original_name;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  },
  downloadContract: async (contract: Contract) => {
    const response = await fetch(`/api/contracts/${contract.id}/pdf`, {
      credentials: "include",
    });
    if (!response.ok) {
      const contentType = response.headers.get("content-type") || "";
      const payload = contentType.includes("application/json")
        ? await response.json()
        : await response.text();
      const error = extractError(payload);
      throw new ApiError(error.message, response.status, error.fields);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${contract.contract_no}-${contract.title}.pdf`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  },
};
