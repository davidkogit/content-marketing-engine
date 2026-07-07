/**
 * Workflow types — Kanban board, stage transitions, approval gates,
 * and workflow history timeline.
 *
 * Mirrors: backend/app/workflow/workflow_schemas.py
 */

import type { WorkflowStage } from "./product";

// ── Board Types ──────────────────────────────────────────────────────────────

/** Minimal product info displayed on Kanban board cards. */
export interface BoardProductItem {
  id: number;
  sku: string;
  name: string;
  workflow_stage: string;
  /** Category name for badge display (may not be in all API responses). */
  category_name?: string | null;
  /** ISO 8601 timestamp of last product update. */
  updated_at?: string | null;
  /** Number of claims attached to this product. */
  claim_count?: number | null;
}

/** A single Kanban column — one workflow stage with its products and count. */
export interface BoardColumn {
  stage: string;
  count: number;
  products: BoardProductItem[];
}

/** Full Kanban board view — all columns with products grouped by stage. */
export interface BoardResponse {
  columns: BoardColumn[];
}

// ── Transition Types ─────────────────────────────────────────────────────────

export interface TransitionRequest {
  to_stage: WorkflowStage;
  comment?: string | null;
}

export interface RequestChangesRequest {
  comment: string;
}

export interface TransitionResponse {
  product_id: number;
  from_stage: string;
  to_stage: string;
  version_number: number;
  comment: string | null;
}

// ── History Types ────────────────────────────────────────────────────────────

export interface WorkflowHistoryItem {
  id: number;
  version_number: number;
  from_stage: string;
  to_stage: string;
  change_summary: string | null;
  comment: string | null;
  created_by: number;
  created_at: string;
}
