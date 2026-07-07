/**
 * API types — request/response shapes, error handling, generation, export,
 * and settings endpoints.
 *
 * Mirrors all backend Pydantic schemas under:
 *   auth/, products/, workflow/, llm/, export/, settings/
 */

import type { UserRole } from "./user";

// ── Auth Request/Response ────────────────────────────────────────────────────

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  role?: UserRole;
}

export interface RefreshRequest {
  refresh_token: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

// ── Generic Paginated Response ──────────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// ── ApiError — Centralised Error Class ──────────────────────────────────────

/** Structured API error returned by the backend or constructed client-side. */
export class ApiError extends Error {
  status: number;
  message: string;
  fieldErrors: Record<string, string[]> | null;

  constructor(
    status: number,
    message: string,
    fieldErrors: Record<string, string[]> | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.message = message;
    this.fieldErrors = fieldErrors;
  }
}

// ── Generation Types ─────────────────────────────────────────────────────────

export const GenerationType = {
  PRODUCT_DESCRIPTION: "product_description",
  FEATURE_BULLETS: "feature_bullets",
  SOCIAL_POST: "social_post",
  TAGLINE: "tagline",
  SEO_META: "seo_meta",
  EMAIL_BLAST: "email_blast",
} as const;

export type GenerationType =
  (typeof GenerationType)[keyof typeof GenerationType];

export interface GenerateRequest {
  generation_type?: GenerationType;
}

export interface ExtractedClaim {
  text: string;
  source_doc_id: number | null;
  confidence_score: number;
}

export interface SourceRef {
  doc_id: number;
  title: string;
  relevant_excerpt: string;
}

export interface RuleViolation {
  rule_type: string;
  description: string;
  rule_text: string;
}

export interface GenerationMetadata {
  model: string;
  tokens: number;
  latency: number;
}

export interface GeneratedResponse {
  copy: string;
  claims: ExtractedClaim[];
  flags: string[];
  sources: SourceRef[];
  violations: RuleViolation[];
  metadata: GenerationMetadata;
}

export const TaskStatus = {
  PENDING: "pending",
  RUNNING: "running",
  COMPLETED: "completed",
  FAILED: "failed",
} as const;

export type TaskStatus = (typeof TaskStatus)[keyof typeof TaskStatus];

export interface TaskStatusResponse {
  task_id: string;
  status: TaskStatus;
  result: GeneratedResponse | null;
  error: string | null;
}

// ── Export Types ─────────────────────────────────────────────────────────────

export const ClaimMode = {
  INLINE: "inline",
  EXPANDED: "expanded",
} as const;

export type ClaimMode = (typeof ClaimMode)[keyof typeof ClaimMode];

export interface ExportFieldMapping {
  source: string;
  label: string;
  enabled: boolean;
}

export interface ExportMappingConfig {
  fields: ExportFieldMapping[];
  claim_mode: ClaimMode;
}

export interface ExportPreviewCell {
  column: string;
  value: string | null;
}

export interface ExportPreviewRow {
  row_index: number;
  cells: ExportPreviewCell[];
}

export interface ExportPreviewResponse {
  product_id: number;
  product_name: string;
  claim_mode: string;
  total_rows: number;
  rows: ExportPreviewRow[];
}

export interface ExportHistoryItem {
  id: number;
  product_id: number;
  product_name: string | null;
  exported_by: number;
  exported_by_email: string | null;
  mapping_config: ExportMappingConfig | null;
  exported_at: string;
}

export type ExportHistoryResponse = PaginatedResponse<ExportHistoryItem>;

// ── Settings: LLM ───────────────────────────────────────────────────────────

export const LLMProvider = {
  OPENAI: "openai",
  ANTHROPIC: "anthropic",
} as const;

export type LLMProvider = (typeof LLMProvider)[keyof typeof LLMProvider];

export interface LLMConfigResponse {
  provider: string;
  model: string;
  masked_api_key: string;
  is_active: boolean;
  created_at: string;
}

export interface LLMConfigUpdateRequest {
  provider: string;
  model: string;
  api_key: string;
}

export interface LLMConfigTestResponse {
  success: boolean;
  latency_ms: number;
  message: string;
  model_used: string | null;
}

// ── Settings: User Management ───────────────────────────────────────────────

export interface InviteUserRequest {
  email: string;
  role: UserRole;
}

export interface ChangeRoleRequest {
  role: UserRole;
}

export interface UserListItem {
  id: number;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface UserListResponse {
  items: UserListItem[];
  total: number;
}

export interface UserActionResponse {
  message: string;
  user_id: number;
  email: string;
  role: string;
  is_active: boolean;
}

// ── Settings: Brand Rules ───────────────────────────────────────────────────

export type RuleName = "tone" | "compliance" | "style";

export interface RuleContentResponse {
  rule_name: string;
  content: string;
}

export interface UpdateRuleRequest {
  content: string;
}

export interface PreviewRuleRequest {
  content: string;
  sample_input?: string | null;
}

export interface RulePreviewResponse {
  rule_name: string;
  current_content: string;
  proposed_content: string;
  sample_prompt: string;
  diff_summary: string;
}

// Note: WorkflowStage, ClaimStatus, DocType are exported from ./product
// and available via the barrel import from @/types.
