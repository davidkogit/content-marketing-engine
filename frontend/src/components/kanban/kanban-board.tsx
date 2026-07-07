/**
 * KanbanBoard — full drag-and-drop Kanban board with 5 workflow columns.
 *
 * Features:
 *   - Uses @dnd-kit/core DndContext with closestCorners collision detection
 *   - Uses @dnd-kit/sortable for vertical card reordering within columns
 *   - Cross-column drag-and-drop: cards can be moved between stages
 *   - DragOverlay shows a floating clone of the dragged card
 *   - PointerSensor with 8px activation distance prevents accidental drags
 *   - Role-aware: read-only mode for viewer/editor roles
 *   - Responsive: columns scroll horizontally on desktop, stack on mobile
 *
 * When a card is dropped on a different column, the hook's
 * transitionProduct() is called to persist the stage change via the
 * POST /workflow/products/{id}/transition API endpoint.
 *
 * Within-column reordering is purely visual (local state only) since
 * the backend does not track order — only the stage transition matters.
 *
 * All data and loading/error state is received from the parent via props.
 * The DnD logic (sensors, handlers, overlay) lives entirely in this component.
 */

import { useState, useCallback, useMemo } from "react";
import {
  DndContext,
  DragOverlay,
  closestCorners,
  PointerSensor,
  useSensor,
  useSensors,
  type DragStartEvent,
  type DragEndEvent,
} from "@dnd-kit/core";
import { KanbanColumn } from "@/components/kanban/kanban-column";
import { KanbanCard } from "@/components/kanban/kanban-card";
import type { BoardColumn, BoardProductItem } from "@/types/workflow";
import type { WorkflowStage } from "@/types/product";

// ── Props ─────────────────────────────────────────────────────────────────

export interface KanbanBoardProps {
  columns: BoardColumn[];
  isLoading: boolean;
  isReadOnly: boolean;
  moveProductLocally: (
    productId: number,
    fromStage: string,
    toStage: string,
    overIndex?: number,
  ) => void;
  transitionProduct: (productId: number, toStage: WorkflowStage) => Promise<void>;
}

// ── Component ─────────────────────────────────────────────────────────────

export function KanbanBoard({
  columns,
  isLoading,
  isReadOnly,
  moveProductLocally,
  transitionProduct,
}: KanbanBoardProps) {
  // ── Drag state ──────────────────────────────────────────────────────

  const [activeProduct, setActiveProduct] = useState<BoardProductItem | null>(
    null,
  );

  // ── Sensors ──────────────────────────────────────────────────────────

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 8 },
    }),
  );

  // ── Lookup helpers ───────────────────────────────────────────────────

  /** Maps "product-{id}" back to the product across all columns. */
  const productMap = useMemo(() => {
    const map = new Map<string, BoardProductItem>();
    for (const col of columns) {
      for (const p of col.products) {
        map.set(`product-${p.id}`, p);
      }
    }
    return map;
  }, [columns]);

  /**
   * Determine which stage a given droppable/over ID belongs to.
   * Over IDs can be "column-{stage}" or "product-{id}".
   */
  function resolveTargetStage(overId: string): string | null {
    if (overId.startsWith("column-")) {
      return overId.slice("column-".length);
    }
    if (overId.startsWith("product-")) {
      const product = productMap.get(overId);
      return product?.workflow_stage ?? null;
    }
    return null;
  }

  // ── Drag handlers ────────────────────────────────────────────────────

  const handleDragStart = useCallback(
    (event: DragStartEvent) => {
      const id = event.active.id as string;
      const product = productMap.get(id) ?? null;
      setActiveProduct(product);
    },
    [productMap],
  );

  const handleDragEnd = useCallback(
    async (event: DragEndEvent) => {
      setActiveProduct(null);

      const { active, over } = event;
      if (!over) return; // dropped outside any droppable — no-op

      const activeId = active.id as string;
      if (!activeId.startsWith("product-")) return;

      const productId = Number(activeId.slice("product-".length));
      const product = productMap.get(activeId);
      if (!product) return;

      const targetStage = resolveTargetStage(over.id as string);
      if (!targetStage) return;

      const currentStage = product.workflow_stage;

      // Determine insert position in the target column
      let overIndex: number | undefined;
      if ((over.id as string).startsWith("product-")) {
        const targetCol = columns.find((c) => c.stage === targetStage);
        if (targetCol) {
          overIndex = targetCol.products.findIndex(
            (p) => `product-${p.id}` === (over.id as string),
          );
          if (overIndex === -1) overIndex = undefined;
        }
      }

      // Optimistic local update
      moveProductLocally(productId, currentStage, targetStage, overIndex);

      // Persist stage change only if stage actually changed
      if (currentStage !== targetStage) {
        try {
          await transitionProduct(productId, targetStage as WorkflowStage);
        } catch {
          // Rollback is handled inside transitionProduct,
          // which restores the column snapshot on failure.
        }
      }
    },
    [columns, productMap, moveProductLocally, transitionProduct],
  );

  // ── Render ───────────────────────────────────────────────────────────

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      {/* ── Board: horizontally scrollable on desktop, stacked on mobile ── */}
      <div className="flex gap-4 overflow-x-auto pb-4 flex-1 lg:flex-row flex-col lg:items-start items-stretch">
        {columns.map((column) => (
          <KanbanColumn
            key={column.stage}
            column={column}
            isLoading={isLoading}
            isReadOnly={isReadOnly}
          />
        ))}
      </div>

      {/* ── Drag Overlay (floating clone) ──────────────────────────────── */}
      <DragOverlay dropAnimation={null}>
        {activeProduct && (
          <div className="w-[300px]">
            <KanbanCard product={activeProduct} isReadOnly />
          </div>
        )}
      </DragOverlay>
    </DndContext>
  );
}
