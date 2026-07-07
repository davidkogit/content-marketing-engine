/**
 * Typed API endpoint methods — one method per backend endpoint.
 *
 * Groups endpoints by domain (auth, products, workflow, export, generation,
 * settings) and wraps the shared apiClient so consumers never reach for
 * axios directly.  Every method is typed end-to-end — request payloads
 * and response shapes are enforced by TypeScript.
 */

import apiClient from "./api-client";
import type {
  TokenResponse,
  UserResponse,
  Category,
  CategoryCreate,
  CategoryUpdate,
  Segment,
  SegmentCreate,
  SegmentUpdate,
  ProductListItem,
  ProductResponse,
  ProductCreate,
  ProductUpdate,
  ProductDocument,
  DocumentCreate,
  ProductClaim,
  ClaimCreate,
  ClaimUpdate,
  ProductVersion,
  BoardResponse,
  TransitionRequest,
  TransitionResponse,
  RequestChangesRequest,
  WorkflowHistoryItem,
  PaginatedResponse,
  GeneratedResponse,
  GenerateRequest,
  TaskStatusResponse,
  ExportPreviewResponse,
  ExportMappingConfig,
  ExportHistoryResponse,
  LLMConfigResponse,
  LLMConfigUpdateRequest,
  LLMConfigTestResponse,
  UserListResponse,
  InviteUserRequest,
  ChangeRoleRequest,
  UserActionResponse,
  RuleContentResponse,
  RulePreviewResponse,
  RuleName,
  ClaimStatus,
} from "@/types";

// ── Helpers ──────────────────────────────────────────────────────────────────

/** Extract `response.data` and cast to T — the standard pattern for Axios. */
function unwrap<T>(response: { data: T }): T {
  return response.data;
}

// ── Types (re-exported for convenience) ─────────────────────────────────────

export type {
  TokenResponse,
  UserResponse as UserProfile,
  Category,
  CategoryCreate,
  CategoryUpdate,
  Segment,
  SegmentCreate,
  SegmentUpdate,
  ProductListItem,
  ProductResponse,
  ProductCreate,
  ProductUpdate,
  ProductDocument,
  DocumentCreate,
  ProductClaim,
  ClaimCreate,
  ClaimUpdate,
  ProductVersion,
  BoardResponse,
  TransitionRequest,
  TransitionResponse,
  RequestChangesRequest,
  WorkflowHistoryItem,
  PaginatedResponse,
  GeneratedResponse,
  GenerateRequest,
  TaskStatusResponse,
  ExportPreviewResponse,
  ExportMappingConfig,
  ExportHistoryResponse,
  LLMConfigResponse,
  LLMConfigUpdateRequest,
  LLMConfigTestResponse,
  UserListResponse,
  InviteUserRequest,
  ChangeRoleRequest,
  UserActionResponse,
  RuleContentResponse,
  RulePreviewResponse,
  RuleName,
  ClaimStatus,
};

// ── Auth ─────────────────────────────────────────────────────────────────────

export const auth = {
  login: (email: string, password: string) =>
    apiClient
      .post<TokenResponse>("/auth/login", { email, password })
      .then(unwrap),

  register: (email: string, password: string, role?: string) =>
    apiClient
      .post<TokenResponse>("/auth/register", { email, password, role })
      .then(unwrap),

  me: () =>
    apiClient.get<UserResponse>("/auth/me").then(unwrap),

  refresh: (refreshToken: string) =>
    apiClient
      .post<TokenResponse>("/auth/refresh", { refresh_token: refreshToken })
      .then(unwrap),
};

// ── Categories ───────────────────────────────────────────────────────────────

export const categories = {
  list: () =>
    apiClient.get<Category[]>("/categories").then(unwrap),

  get: (id: number) =>
    apiClient.get<Category>(`/categories/${id}`).then(unwrap),

  create: (body: CategoryCreate) =>
    apiClient.post<Category>("/categories", body).then(unwrap),

  update: (id: number, body: CategoryUpdate) =>
    apiClient.put<Category>(`/categories/${id}`, body).then(unwrap),

  delete: (id: number) =>
    apiClient.delete<void>(`/categories/${id}`).then(unwrap),
};

// ── Segments ─────────────────────────────────────────────────────────────────

export const segments = {
  list: () =>
    apiClient.get<Segment[]>("/segments").then(unwrap),

  get: (id: number) =>
    apiClient.get<Segment>(`/segments/${id}`).then(unwrap),

  create: (body: SegmentCreate) =>
    apiClient.post<Segment>("/segments", body).then(unwrap),

  update: (id: number, body: SegmentUpdate) =>
    apiClient.put<Segment>(`/segments/${id}`, body).then(unwrap),

  delete: (id: number) =>
    apiClient.delete<void>(`/segments/${id}`).then(unwrap),
};

// ── Products ─────────────────────────────────────────────────────────────────

export interface ProductQueryParams {
  category_id?: number;
  segment_id?: number;
  workflow_stage?: string;
  search?: string;
  page?: number;
  page_size?: number;
}

export const products = {
  list: (params?: ProductQueryParams) =>
    apiClient
      .get<PaginatedResponse<ProductListItem>>("/products", { params })
      .then(unwrap),

  get: (id: number) =>
    apiClient.get<ProductResponse>(`/products/${id}`).then(unwrap),

  create: (body: ProductCreate) =>
    apiClient.post<ProductResponse>("/products", body).then(unwrap),

  update: (id: number, body: ProductUpdate) =>
    apiClient.put<ProductResponse>(`/products/${id}`, body).then(unwrap),

  delete: (id: number, permanent = false) =>
    apiClient
      .delete<void>(`/products/${id}`, { params: { permanent } })
      .then(unwrap),
};

// ── Documents ────────────────────────────────────────────────────────────────

export const documents = {
  list: (productId: number) =>
    apiClient
      .get<ProductDocument[]>(`/products/${productId}/documents`)
      .then(unwrap),

  create: (productId: number, body: DocumentCreate) =>
    apiClient
      .post<ProductDocument>(`/products/${productId}/documents`, body)
      .then(unwrap),

  delete: (documentId: number) =>
    apiClient.delete<void>(`/documents/${documentId}`).then(unwrap),
};

// ── Claims ───────────────────────────────────────────────────────────────────

export const claims = {
  list: (productId: number, status?: ClaimStatus) =>
    apiClient
      .get<ProductClaim[]>(`/products/${productId}/claims`, {
        params: status ? { status } : undefined,
      })
      .then(unwrap),

  create: (productId: number, body: ClaimCreate) =>
    apiClient
      .post<ProductClaim>(`/products/${productId}/claims`, body)
      .then(unwrap),

  update: (claimId: number, body: ClaimUpdate) =>
    apiClient.put<ProductClaim>(`/claims/${claimId}`, body).then(unwrap),

  delete: (claimId: number) =>
    apiClient.delete<void>(`/claims/${claimId}`).then(unwrap),
};

// ── Versions ─────────────────────────────────────────────────────────────────

export const versions = {
  list: (productId: number) =>
    apiClient
      .get<{ versions: ProductVersion[]; total: number }>(
        `/products/${productId}/versions`,
      )
      .then(unwrap),

  get: (productId: number, versionNumber: number) =>
    apiClient
      .get<ProductVersion>(
        `/products/${productId}/versions/${versionNumber}`,
      )
      .then(unwrap),

  restore: (productId: number, versionNumber: number) =>
    apiClient
      .post<{ versions: ProductVersion[]; total: number }>(
        `/products/${productId}/versions/${versionNumber}/restore`,
      )
      .then(unwrap),
};

// ── Workflow ─────────────────────────────────────────────────────────────────

export const workflow = {
  board: () =>
    apiClient.get<BoardResponse>("/workflow/board").then(unwrap),

  transition: (productId: number, body: TransitionRequest) =>
    apiClient
      .post<TransitionResponse>(
        `/workflow/products/${productId}/transition`,
        body,
      )
      .then(unwrap),

  approve: (productId: number) =>
    apiClient
      .post<TransitionResponse>(`/workflow/products/${productId}/approve`)
      .then(unwrap),

  requestChanges: (productId: number, body: RequestChangesRequest) =>
    apiClient
      .post<TransitionResponse>(
        `/workflow/products/${productId}/request-changes`,
        body,
      )
      .then(unwrap),

  history: (productId: number) =>
    apiClient
      .get<WorkflowHistoryItem[]>(
        `/workflow/products/${productId}/history`,
      )
      .then(unwrap),
};

// ── Export ───────────────────────────────────────────────────────────────────

export const exportApi = {
  csv: (productId: number) =>
    apiClient
      .get<string>(`/export/products/${productId}`, {
        responseType: "text",
      })
      .then(unwrap),

  preview: (productId: number) =>
    apiClient
      .get<ExportPreviewResponse>(`/export/products/${productId}/preview`)
      .then(unwrap),

  getConfig: () =>
    apiClient.get<ExportMappingConfig>("/export/config").then(unwrap),

  saveConfig: (config: ExportMappingConfig) =>
    apiClient
      .post<{ status: string; message: string }>("/export/config", config)
      .then(unwrap),

  history: (page = 1, pageSize = 20) =>
    apiClient
      .get<ExportHistoryResponse>("/export/history", {
        params: { page, page_size: pageSize },
      })
      .then(unwrap),
};

// ── Generation ───────────────────────────────────────────────────────────────

export const generation = {
  sync: (productId: number, body: GenerateRequest) =>
    apiClient
      .post<GeneratedResponse>(`/generate/${productId}`, body)
      .then(unwrap),

  async: (productId: number, body: GenerateRequest) =>
    apiClient
      .post<{ task_id: string; status: string }>(
        `/generate/async/${productId}`,
        body,
      )
      .then(unwrap),

  status: (taskId: string) =>
    apiClient
      .get<TaskStatusResponse>(`/generate/status/${taskId}`)
      .then(unwrap),
};

// ── Settings: Users ──────────────────────────────────────────────────────────

export const settingsUsers = {
  list: () =>
    apiClient.get<UserListResponse>("/settings/users").then(unwrap),

  invite: (body: InviteUserRequest) =>
    apiClient
      .post<UserActionResponse>("/settings/users/invite", body)
      .then(unwrap),

  changeRole: (userId: number, body: ChangeRoleRequest) =>
    apiClient
      .put<UserActionResponse>(`/settings/users/${userId}/role`, body)
      .then(unwrap),

  deactivate: (userId: number) =>
    apiClient
      .put<UserActionResponse>(`/settings/users/${userId}/deactivate`)
      .then(unwrap),
};

// ── Settings: Brand Rules ────────────────────────────────────────────────────

export const settingsRules = {
  get: (ruleName: RuleName) =>
    apiClient
      .get<RuleContentResponse>(`/settings/rules/${ruleName}`)
      .then(unwrap),

  update: (ruleName: RuleName, content: string) =>
    apiClient
      .put<{ rule_name: string; message: string }>(
        `/settings/rules/${ruleName}`,
        { content },
      )
      .then(unwrap),

  preview: (ruleName: RuleName, content: string, sampleInput?: string) =>
    apiClient
      .post<RulePreviewResponse>(`/settings/rules/${ruleName}/preview`, {
        content,
        sample_input: sampleInput,
      })
      .then(unwrap),
};

// ── Settings: LLM ────────────────────────────────────────────────────────────

export const settingsLlm = {
  get: () =>
    apiClient.get<LLMConfigResponse>("/settings/llm").then(unwrap),

  update: (body: LLMConfigUpdateRequest) =>
    apiClient.put<LLMConfigResponse>("/settings/llm", body).then(unwrap),

  test: () =>
    apiClient
      .post<LLMConfigTestResponse>("/settings/llm/test")
      .then(unwrap),
};
