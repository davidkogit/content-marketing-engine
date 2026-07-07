/**
 * Product types — PIM core entities: categories, segments, products,
 * documents, claims, versions, and related enums.
 *
 * Mirrors backend/app/models/* + backend/app/products/*_schemas.py
 */

// ── Enums ────────────────────────────────────────────────────────────────────

/** Kanban workflow stages for the content marketing pipeline. */
export const WorkflowStage = {
  INGEST: "ingest",
  DRAFT: "draft",
  REVIEW: "review",
  APPROVED: "approved",
  EXPORTED: "exported",
} as const;

export type WorkflowStage = (typeof WorkflowStage)[keyof typeof WorkflowStage];

/** Verification status for generated product claims. */
export const ClaimStatus = {
  PENDING_REVIEW: "pending_review",
  VERIFIED: "verified",
  FLAGGED: "flagged",
  REJECTED: "rejected",
} as const;

export type ClaimStatus = (typeof ClaimStatus)[keyof typeof ClaimStatus];

/** Supported document source types. */
export const DocType = {
  PDF: "pdf",
  URL: "url",
} as const;

export type DocType = (typeof DocType)[keyof typeof DocType];

// ── Category ─────────────────────────────────────────────────────────────────

export interface Category {
  id: number;
  name: string;
  description: string | null;
  product_count: number;
  created_at: string;
  updated_at: string;
}

export interface CategoryCreate {
  name: string;
  description?: string | null;
}

export interface CategoryUpdate {
  name?: string | null;
  description?: string | null;
}

// ── Segment ──────────────────────────────────────────────────────────────────

export interface Segment {
  id: number;
  name: string;
  description: string | null;
  target_audience: string | null;
  tone: string | null;
  created_at: string;
  product_count: number;
}

export interface SegmentCreate {
  name: string;
  description?: string | null;
  target_audience?: string | null;
  tone?: string | null;
}

export interface SegmentUpdate {
  name?: string | null;
  description?: string | null;
  target_audience?: string | null;
  tone?: string | null;
}

// ── ProductDocument ──────────────────────────────────────────────────────────

export interface ProductDocument {
  id: number;
  product_id: number;
  title: string;
  url: string;
  doc_type: string;
  extracted_text: string | null;
  created_at: string;
}

export interface DocumentCreate {
  url: string;
  doc_type: DocType;
}

// ── ProductClaim ─────────────────────────────────────────────────────────────

export interface ProductClaim {
  id: number;
  product_id: number;
  claim_text: string;
  source_doc_id: number | null;
  status: string;
  assigned_to: number | null;
  created_at: string;
  source_doc?: ClaimDocumentRef | null;
}

export interface ClaimDocumentRef {
  id: number;
  title: string;
  url: string;
}

export interface ClaimCreate {
  claim_text: string;
  source_doc_id?: number | null;
  status?: ClaimStatus;
}

export interface ClaimUpdate {
  claim_text?: string | null;
  status?: ClaimStatus | null;
}

// ── ProductVersion ───────────────────────────────────────────────────────────

export interface ProductVersion {
  id: number;
  version_number: number;
  snapshot_json: string;
  change_summary: string | null;
  created_by: number;
  created_at: string;
}

// ── Product ──────────────────────────────────────────────────────────────────

/** Nested category reference inside product responses. */
export interface ProductCategoryRef {
  id: number;
  name: string;
}

/** Nested segment reference inside product responses. */
export interface ProductSegmentRef {
  id: number;
  name: string;
}

/** Nested document reference inside product responses. */
export interface ProductDocumentRef {
  id: number;
  title: string;
  url: string;
  doc_type: string;
}

/** Nested claim reference inside product responses. */
export interface ProductClaimRef {
  id: number;
  claim_text: string;
  source_doc_id: number | null;
  status: string;
}

/** Flat product representation (list items). */
export interface ProductListItem {
  id: number;
  sku: string;
  name: string;
  description: string | null;
  category_id: number | null;
  segment_id: number | null;
  workflow_stage: string;
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
}

/** Full product detail with nested relationships. */
export interface ProductResponse extends ProductListItem {
  category: ProductCategoryRef | null;
  segment: ProductSegmentRef | null;
  documents: ProductDocumentRef[];
  claims: ProductClaimRef[];
  versions: ProductVersion[];
}

export interface ProductCreate {
  sku: string;
  name: string;
  description?: string | null;
  category_id?: number | null;
  segment_id?: number | null;
}

export interface ProductUpdate {
  name?: string | null;
  description?: string | null;
  category_id?: number | null;
  segment_id?: number | null;
  workflow_stage?: WorkflowStage | null;
}
