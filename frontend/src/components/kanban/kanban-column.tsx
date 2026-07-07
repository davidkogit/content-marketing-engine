/**
 * KanbanColumn — a single workflow stage column within the Kanban board.
 *
 * Each column:
 *   - Uses @dnd-kit/core's useDroppable as a drop target
 *   - Wraps its cards in a @dnd-kit/sortable SortableContext
 *   - Shows a header with stage name and product count
 *   - Renders an empty-state placeholder when no cards exist
 *   - Renders skeleton placeholders during loading
 *   - Is independently scrollable when cards overflow
 *   - Highlights visually when a card is dragged over it
 */

import { useDroppable } from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { KanbanCard } from "@/components/kanban/kanban-card";
import type { BoardColumn } from "@/types/workflow";

// ── Props ─────────────────────────────────────────────────────────────────

interface KanbanColumnProps {
  column: BoardColumn;
  isLoading: boolean;
  isReadOnly: boolean;
}

// ── Stage Display Names ───────────────────────────────────────────────────

const STAGE_LABELS: Record<string, string> = {
  ingest: "Ingest",
  draft: "Draft",
  review: "Review",
  approved: "Approved",
  exported: "Exported",
};

const STAGE_COLORS: Record<string, string> = {
  ingest: "border-l-amber-400",
  draft: "border-l-blue-400",
  review: "border-l-purple-400",
  approved: "border-l-emerald-400",
  exported: "border-l-slate-400",
};

const STAGE_DESCRIPTIONS: Record<string, string> = {
  ingest: "New products waiting to be processed.",
  draft: "Content drafts in progress.",
  review: "Pending review and approval.",
  approved: "Approved and ready for export.",
  exported: "Already exported.",
};

// ── Component ─────────────────────────────────────────────────────────────

export function KanbanColumn({
  column,
  isLoading,
  isReadOnly,
}: KanbanColumnProps) {
  const { setNodeRef, isOver } = useDroppable({
    id: `column-${column.stage}`,
    disabled: isReadOnly,
  });

  const itemIds = column.products.map((p) => `product-${p.id}`);
  const stageLabel = STAGE_LABELS[column.stage] ?? column.stage;

  return (
    <div
      className={cn(
        "flex w-[300px] min-w-[300px] shrink-0 flex-col rounded-lg border bg-card",
        isOver && !isReadOnly && "ring-2 ring-accent border-accent",
      )}
    >
      {/* ── Column Header ───────────────────────────────────────────── */}
      <div
        className={cn(
          "flex items-center justify-between border-l-4 px-3 py-2.5",
          STAGE_COLORS[column.stage] ?? "border-l-muted",
        )}
      >
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold">{stageLabel}</h3>
          {!isLoading && (
            <Badge variant="secondary" className="text-[10px] px-1.5">
              {column.count}
            </Badge>
          )}
        </div>
      </div>

      {/* ── Card List (scrollable) ──────────────────────────────────── */}
      <div
        ref={setNodeRef}
        className="flex-1 overflow-y-auto p-2 space-y-2 min-h-[120px]"
      >
        <SortableContext
          items={itemIds}
          strategy={verticalListSortingStrategy}
        >
          {/* ── Loading state ────────────────────────────────────────── */}
          {isLoading &&
            Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-[88px] w-full rounded-lg" />
            ))}

          {/* ── Cards + Empty state ──────────────────────────────────── */}
          {!isLoading &&
            column.products.length > 0 &&
            column.products.map((product) => (
              <KanbanCard
                key={product.id}
                product={product}
                isReadOnly={isReadOnly}
              />
            ))}

          {!isLoading && column.products.length === 0 && (
            <div className="flex h-full min-h-[100px] items-center justify-center px-3 py-6">
              <p className="text-xs text-muted-foreground text-center">
                {STAGE_DESCRIPTIONS[column.stage] ??
                  `No products in ${stageLabel}.`}
              </p>
            </div>
          )}
        </SortableContext>
      </div>
    </div>
  );
}
