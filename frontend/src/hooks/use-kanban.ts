/**
 * useKanban — fetches and manages the Kanban board state.
 *
 * Provides:
 *   - columns: BoardColumn array grouped by workflow stage
 *   - isLoading / error: UI state flags
 *   - fetchBoard(): refresh the entire board from the API
 *   - transitionProduct(id, stage): move a product to a new stage,
 *     with optimistic local update + rollback on failure
 *   - moveProductLocally(id, fromStage, toStage): optimistic reorder
 *     within the local state (used by drag-and-drop before API call)
 *
 * The board is fetched from GET /workflow/board and transitions are
 * posted to POST /workflow/products/{id}/transition.
 */

import { useState, useEffect, useCallback } from "react";
import { workflow } from "@/lib/api-endpoints";
import type { BoardColumn, BoardProductItem } from "@/types/workflow";
import type { WorkflowStage } from "@/types/product";

// ── Stage Order (canonical column ordering) ──────────────────────────────

export const STAGE_ORDER = [
  "ingest",
  "draft",
  "review",
  "approved",
  "exported",
] as const;

export type StageValue = (typeof STAGE_ORDER)[number];

// ── Hook Return Type ─────────────────────────────────────────────────────

export interface UseKanbanReturn {
  columns: BoardColumn[];
  isLoading: boolean;
  error: string | null;
  fetchBoard: () => Promise<void>;
  transitionProduct: (productId: number, toStage: WorkflowStage) => Promise<void>;
  moveProductLocally: (
    productId: number,
    fromStage: string,
    toStage: string,
    overIndex?: number,
  ) => void;
}

// ── Helpers ───────────────────────────────────────────────────────────────

/**
 * Find a product across all columns. Returns the stage and product,
 * or null if not found.
 */
function findProduct(
  columns: BoardColumn[],
  productId: number,
): { stageIndex: number; productIndex: number; item: BoardProductItem } | null {
  for (let si = 0; si < columns.length; si++) {
    const products = columns[si].products;
    for (let pi = 0; pi < products.length; pi++) {
      if (products[pi].id === productId) {
        return { stageIndex: si, productIndex: pi, item: products[pi] };
      }
    }
  }
  return null;
}

// ── Hook ──────────────────────────────────────────────────────────────────

export function useKanban(): UseKanbanReturn {
  const [columns, setColumns] = useState<BoardColumn[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // ── fetchBoard ────────────────────────────────────────────────────────

  const fetchBoard = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const data = await workflow.board();
      setColumns(data.columns);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to load board data.";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    fetchBoard();
  }, [fetchBoard]);

  // ── moveProductLocally (optimistic reorder) ──────────────────────────

  const moveProductLocally = useCallback(
    (
      productId: number,
      fromStage: string,
      toStage: string,
      overIndex?: number,
    ) => {
      setColumns((prev) => {
        const next = prev.map((col) => ({
          ...col,
          products: [...col.products],
        }));

        // Find the product in the source column
        const fromColIndex = next.findIndex((c) => c.stage === fromStage);
        if (fromColIndex === -1) return prev;

        const productIndex = next[fromColIndex].products.findIndex(
          (p) => p.id === productId,
        );
        if (productIndex === -1) return prev;

        // Remove from source
        const [product] = next[fromColIndex].products.splice(productIndex, 1);
        next[fromColIndex] = {
          ...next[fromColIndex],
          count: next[fromColIndex].products.length,
          products: next[fromColIndex].products,
        };

        // Update the product's stage locally
        product.workflow_stage = toStage;

        // Insert into target column
        const toColIndex = next.findIndex((c) => c.stage === toStage);
        if (toColIndex === -1) return prev;

        const targetProducts = next[toColIndex].products;
        const insertAt =
          overIndex !== undefined && overIndex >= 0 && overIndex <= targetProducts.length
            ? overIndex
            : targetProducts.length;

        targetProducts.splice(insertAt, 0, product);
        next[toColIndex] = {
          ...next[toColIndex],
          count: targetProducts.length,
          products: targetProducts,
        };

        return next;
      });
    },
    [],
  );

  // ── transitionProduct (API call + optimistic update) ──────────────────

  const transitionProduct = useCallback(
    async (productId: number, toStage: WorkflowStage) => {
      // Snapshot columns before the transition for potential rollback.
      const snapshot = columns;

      // Find current stage
      const found = findProduct(columns, productId);
      if (!found) return;

      const fromStage = found.item.workflow_stage;

      // Optimistic update
      moveProductLocally(productId, fromStage, toStage);

      try {
        await workflow.transition(productId, { to_stage: toStage });
      } catch {
        // Rollback on failure
        setColumns(snapshot);
        throw new Error(
          `Failed to move product to "${toStage}". The change has been reverted.`,
        );
      }
    },
    [columns, moveProductLocally],
  );

  return {
    columns,
    isLoading,
    error,
    fetchBoard,
    transitionProduct,
    moveProductLocally,
  };
}
