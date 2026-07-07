/**
 * KanbanCard — a single draggable product card within a Kanban column.
 *
 * Features:
 *   - Drag handle using @dnd-kit/sortable's useSortable
 *   - Visual feedback: reduced opacity when dragging
 *   - Displays: product name, SKU, category badge, last updated, claim count
 *   - Click navigates to product detail page (/products/:id)
 *   - Disabled drag when isReadOnly is true (viewer/editor roles)
 *
 * Uses the @dnd-kit/sortable useSortable hook with a unique id
 * prefixed as "product-{id}".
 */

import { useNavigate } from "react-router-dom";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { GripVertical } from "lucide-react";
import { cn } from "@/lib/utils";
import type { BoardProductItem } from "@/types/workflow";

// ── Props ─────────────────────────────────────────────────────────────────

interface KanbanCardProps {
  product: BoardProductItem;
  isReadOnly: boolean;
}

// ── Helpers ───────────────────────────────────────────────────────────────

/** Format an ISO datetime string into a short relative or absolute format. */
function formatTimeAgo(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    const date = new Date(iso);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60_000);
    const diffHours = Math.floor(diffMs / 3_600_000);
    const diffDays = Math.floor(diffMs / 86_400_000);

    if (diffMins < 1) return "just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

// ── Component ─────────────────────────────────────────────────────────────

export function KanbanCard({ product, isReadOnly }: KanbanCardProps) {
  const navigate = useNavigate();

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: `product-${product.id}`,
    disabled: isReadOnly,
  });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  };

  function handleClick() {
    navigate(`/products/${product.id}`);
  }

  return (
    <Card
      ref={setNodeRef}
      style={style}
      className={cn(
        "group cursor-pointer select-none transition-shadow hover:shadow-md",
        isDragging && "shadow-lg ring-2 ring-accent",
        isReadOnly && "cursor-default",
      )}
      onClick={handleClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          handleClick();
        }
      }}
      tabIndex={0}
      role="button"
      aria-label={`View product ${product.name}`}
    >
      <CardContent className="p-3 space-y-2">
        {/* ── Top row: drag handle + name ─────────────────────────── */}
        <div className="flex items-start gap-2">
          {!isReadOnly && (
            <button
              {...attributes}
              {...listeners}
              className="mt-0.5 cursor-grab text-muted-foreground hover:text-foreground touch-none"
              aria-label="Drag to reorder"
              tabIndex={-1}
            >
              <GripVertical className="h-4 w-4" />
            </button>
          )}
          <div className="min-w-0 flex-1">
            <p className="font-medium text-sm leading-tight truncate">
              {product.name}
            </p>
            <p className="text-xs text-muted-foreground font-mono">
              {product.sku}
            </p>
          </div>
        </div>

        {/* ── Bottom row: meta badges ─────────────────────────────── */}
        <div className="flex items-center gap-1.5 flex-wrap">
          {product.category_name && (
            <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
              {product.category_name}
            </Badge>
          )}
          {product.claim_count !== null && product.claim_count !== undefined && (
            <span className="text-[10px] text-muted-foreground">
              {product.claim_count}{" "}
              {product.claim_count === 1 ? "claim" : "claims"}
            </span>
          )}
          {product.updated_at && (
            <span className="text-[10px] text-muted-foreground ml-auto whitespace-nowrap">
              {formatTimeAgo(product.updated_at)}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
