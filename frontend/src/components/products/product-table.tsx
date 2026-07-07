/**
 * ProductTable — sortable, paginated data table for the product list.
 *
 * Features:
 * - Sortable column headers (click to toggle asc / desc)
 * - Status badge on the workflow stage column
 * - Row click → edit callback
 * - Delete button per row (visible only to super_admin)
 * - Loading skeleton rows
 * - Empty state with CTA
 * - Pagination controls with configurable page size
 * - Responsive: full table on md+, stacked card list on mobile
 */

import {
  useMemo,
  type ReactNode,
} from "react";
import {
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Plus,
  Trash2,
  ChevronLeft,
  ChevronRight,
  PackageOpen,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { EnrichedProduct } from "@/hooks/use-products";
import type { ProductSortColumn, SortState } from "@/hooks/use-products";
import { WorkflowStage } from "@/types";

// ── Column Definition ─────────────────────────────────────────────────────────

interface ColumnDef {
  key: ProductSortColumn;
  label: string;
  sortable: boolean;
  /** If true, the column is hidden on mobile card view. */
  hideOnMobile?: boolean;
}

const COLUMNS: ColumnDef[] = [
  { key: "sku", label: "SKU", sortable: true },
  { key: "name", label: "Name", sortable: true },
  { key: "category_name", label: "Category", sortable: true },
  { key: "segment_name", label: "Segment", sortable: true },
  { key: "workflow_stage", label: "Stage", sortable: true },
  { key: "claims_count", label: "Claims", sortable: true },
  { key: "updated_at", label: "Updated", sortable: true },
];

// ── Stage Badge Mapping ───────────────────────────────────────────────────────

const STAGE_BADGE: Record<string, { label: string; variant: "success" | "warning" | "secondary" | "default" | "outline" }> = {
  [WorkflowStage.INGEST]: { label: "Ingest", variant: "secondary" },
  [WorkflowStage.DRAFT]: { label: "Draft", variant: "warning" },
  [WorkflowStage.REVIEW]: { label: "Review", variant: "default" },
  [WorkflowStage.APPROVED]: { label: "Approved", variant: "success" },
  [WorkflowStage.EXPORTED]: { label: "Exported", variant: "outline" },
};

function StageBadge({ stage }: { stage: string }) {
  const info = STAGE_BADGE[stage] ?? { label: stage, variant: "secondary" as const };
  return <Badge variant={info.variant}>{info.label}</Badge>;
}

// ── Sort Icon ─────────────────────────────────────────────────────────────────

function SortIcon({
  column,
  currentSort,
}: {
  column: ProductSortColumn;
  currentSort: SortState;
}) {
  if (currentSort.column !== column) {
    return <ArrowUpDown className="ml-1 h-3.5 w-3.5 opacity-40" />;
  }
  return currentSort.direction === "asc" ? (
    <ArrowUp className="ml-1 h-3.5 w-3.5" />
  ) : (
    <ArrowDown className="ml-1 h-3.5 w-3.5" />
  );
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function SkeletonRow() {
  return (
    <TableRow>
      <TableCell colSpan={COLUMNS.length}>
        <div className="space-y-2 py-1">
          {Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              className="h-4 animate-pulse rounded bg-muted"
              style={{ width: `${60 + Math.random() * 30}%` }}
            />
          ))}
        </div>
      </TableCell>
    </TableRow>
  );
}

// ── Empty State ───────────────────────────────────────────────────────────────

interface EmptyStateProps {
  hasFilters: boolean;
  onCreateClick: () => void;
}

function EmptyState({ hasFilters, onCreateClick }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <PackageOpen className="h-12 w-12 text-muted-foreground/60" />
      {hasFilters ? (
        <>
          <h3 className="mt-4 text-lg font-semibold">No matching products</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Try adjusting your search or filters.
          </p>
        </>
      ) : (
        <>
          <h3 className="mt-4 text-lg font-semibold">No products yet</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Create your first product to get started.
          </p>
          <Button className="mt-4" onClick={onCreateClick}>
            <Plus className="mr-2 h-4 w-4" />
            Create Your First Product
          </Button>
        </>
      )}
    </div>
  );
}

// ── Pagination ────────────────────────────────────────────────────────────────

interface PaginationBarProps {
  page: number;
  totalPages: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
}

const PAGE_SIZE_OPTIONS = [10, 25, 50];

function PaginationBar({
  page,
  totalPages,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
}: PaginationBarProps) {
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);

  return (
    <div className="flex flex-col items-center gap-3 sm:flex-row sm:justify-between">
      {/* ── Page Size ──────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <span>Rows per page</span>
        <select
          value={pageSize}
          onChange={(e) => onPageSizeChange(Number(e.target.value))}
          className="rounded border bg-background px-2 py-1 text-sm"
        >
          {PAGE_SIZE_OPTIONS.map((size) => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </select>
      </div>

      {/* ── Info ───────────────────────────────────────────────────────── */}
      <span className="text-sm text-muted-foreground">
        {total === 0
          ? "No results"
          : `${start}–${end} of ${total}`}
      </span>

      {/* ── Navigation ─────────────────────────────────────────────────── */}
      <div className="flex items-center gap-1">
        <Button
          variant="outline"
          size="icon"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          aria-label="Previous page"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className="min-w-[3rem] text-center text-sm">
          {page} / {totalPages || 1}
        </span>
        <Button
          variant="outline"
          size="icon"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          aria-label="Next page"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

// ── Card View (Mobile) ────────────────────────────────────────────────────────

function MobileCard({
  product,
  onEdit,
  onDelete,
  canDelete,
}: {
  product: EnrichedProduct;
  onEdit: (p: EnrichedProduct) => void;
  onDelete: (p: EnrichedProduct) => void;
  canDelete: boolean;
}) {
  return (
    <div
      className="cursor-pointer rounded-lg border bg-card p-4 shadow-sm transition-colors hover:bg-muted/50"
      onClick={() => onEdit(product)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onEdit(product);
      }}
    >
      <div className="flex items-start justify-between">
        <div className="min-w-0 flex-1">
          <h4 className="truncate font-semibold">{product.name}</h4>
          <p className="text-sm text-muted-foreground">{product.sku}</p>
        </div>
        <StageBadge stage={product.workflow_stage} />
      </div>

      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        <span className="text-muted-foreground">Category</span>
        <span>{product.category_name ?? "—"}</span>
        <span className="text-muted-foreground">Segment</span>
        <span>{product.segment_name ?? "—"}</span>
        <span className="text-muted-foreground">Claims</span>
        <span>{product.claims_count}</span>
        <span className="text-muted-foreground">Updated</span>
        <span>
          {new Date(product.updated_at).toLocaleDateString()}
        </span>
      </div>

      {canDelete && (
        <div className="mt-3 flex justify-end border-t pt-2">
          <Button
            variant="ghost"
            size="sm"
            className="text-destructive hover:text-destructive"
            onClick={(e) => {
              e.stopPropagation();
              onDelete(product);
            }}
          >
            <Trash2 className="mr-1 h-4 w-4" />
            Delete
          </Button>
        </div>
      )}
    </div>
  );
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface ProductTableProps {
  products: EnrichedProduct[];
  sort: SortState;
  onSortChange: (s: SortState) => void;
  isLoading: boolean;
  isEmpty: boolean;
  hasActiveFilters: boolean;
  pagination: {
    page: number;
    pageSize: number;
    total: number;
    totalPages: number;
  };
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  onEdit: (product: EnrichedProduct) => void;
  onDelete: (product: EnrichedProduct) => void;
  onCreate: () => void;
  canDelete: boolean;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function ProductTable({
  products,
  sort,
  onSortChange,
  isLoading,
  isEmpty,
  hasActiveFilters,
  pagination,
  onPageChange,
  onPageSizeChange,
  onEdit,
  onDelete,
  onCreate,
  canDelete,
}: ProductTableProps) {
  // ── Sort Toggle ─────────────────────────────────────────────────────────
  function toggleSort(column: ProductSortColumn) {
    if (sort.column === column) {
      onSortChange({
        column,
        direction: sort.direction === "asc" ? "desc" : "asc",
      });
    } else {
      onSortChange({ column, direction: "asc" });
    }
  }

  // ── Format cell value ───────────────────────────────────────────────────
  function renderCell(product: EnrichedProduct, col: ColumnDef): ReactNode {
    switch (col.key) {
      case "sku":
        return product.sku;
      case "name":
        return <span className="font-medium">{product.name}</span>;
      case "category_name":
        return product.category_name ?? "—";
      case "segment_name":
        return product.segment_name ?? "—";
      case "workflow_stage":
        return <StageBadge stage={product.workflow_stage} />;
      case "claims_count":
        return product.claims_count;
      case "updated_at":
        return new Date(product.updated_at).toLocaleDateString();
      default:
        return null;
    }
  }

  // ── Build column visibility for responsive ─────────────────────────────
  const desktopColumns = useMemo(
    () => COLUMNS,
    [],
  );

  const hasFilters = hasActiveFilters;

  // ── Render ───────────────────────────────────────────────────────────
  return (
    <div className="space-y-4">
      {/* ═══ Desktop Table ══════════════════════════════════════════════ */}
      <div className="hidden overflow-hidden rounded-md border md:block">
        <Table>
          <TableHeader>
            <TableRow>
              {desktopColumns.map((col) => (
                <TableHead
                  key={col.key}
                  className={cn(
                    col.sortable && "cursor-pointer select-none",
                    col.key === "claims_count" && "text-center",
                  )}
                  onClick={col.sortable ? () => toggleSort(col.key) : undefined}
                >
                  <div className="flex items-center">
                    {col.label}
                    {col.sortable && (
                      <SortIcon column={col.key} currentSort={sort} />
                    )}
                  </div>
                </TableHead>
              ))}
              {canDelete && <TableHead className="w-[60px]" />}
            </TableRow>
          </TableHeader>

          <TableBody>
            {/* Loading Skeleton */}
            {isLoading &&
              Array.from({ length: pagination.pageSize }).map((_, i) => (
                <SkeletonRow key={`skel-${i}`} />
              ))}

            {/* Empty */}
            {isEmpty && (
              <TableRow>
                <TableCell colSpan={desktopColumns.length + (canDelete ? 1 : 0)}>
                  <EmptyState
                    hasFilters={hasFilters}
                    onCreateClick={onCreate}
                  />
                </TableCell>
              </TableRow>
            )}

            {/* Data Rows */}
            {!isLoading &&
              products.map((p) => (
                <TableRow
                  key={p.id}
                  className="cursor-pointer"
                  onClick={() => onEdit(p)}
                >
                  {desktopColumns.map((col) => (
                    <TableCell
                      key={col.key}
                      className={cn(
                        col.key === "claims_count" && "text-center",
                      )}
                    >
                      {renderCell(p, col)}
                    </TableCell>
                  ))}
                  {canDelete && (
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="text-muted-foreground hover:text-destructive"
                        onClick={(e) => {
                          e.stopPropagation();
                          onDelete(p);
                        }}
                        aria-label={`Delete ${p.name}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </div>

      {/* ═══ Mobile Card List ════════════════════════════════════════════ */}
      <div className="space-y-3 md:hidden">
        {isLoading &&
          Array.from({ length: 5 }).map((_, i) => (
            <div
              key={`mob-skel-${i}`}
              className="animate-pulse rounded-lg border p-4"
            >
              <div className="mb-2 h-5 w-2/3 rounded bg-muted" />
              <div className="mb-1 h-4 w-1/3 rounded bg-muted" />
              <div className="mt-3 grid grid-cols-2 gap-2">
                {Array.from({ length: 4 }).map((_, j) => (
                  <div key={j} className="h-4 rounded bg-muted" />
                ))}
              </div>
            </div>
          ))}

        {isEmpty && (
          <div className="rounded-lg border p-8">
            <EmptyState
              hasFilters={hasFilters}
              onCreateClick={onCreate}
            />
          </div>
        )}

        {!isLoading &&
          products.map((p) => (
            <MobileCard
              key={p.id}
              product={p}
              onEdit={onEdit}
              onDelete={onDelete}
              canDelete={canDelete}
            />
          ))}
      </div>

      {/* ═══ Pagination ─══════════════════════════════════════════════════ */}
      {!isLoading && !isEmpty && (
        <PaginationBar
          page={pagination.page}
          totalPages={pagination.totalPages}
          pageSize={pagination.pageSize}
          total={pagination.total}
          onPageChange={onPageChange}
          onPageSizeChange={onPageSizeChange}
        />
      )}
    </div>
  );
}
