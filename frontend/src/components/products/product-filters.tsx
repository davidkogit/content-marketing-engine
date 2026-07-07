/**
 * ProductFilters — search bar + filter dropdowns for the product list page.
 *
 * Provides debounced text search and filter selects for category,
 * segment, and workflow stage.  All state lives in the parent
 * (via useProducts()) — this component is purely presentational.
 */

import { Search, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Category, Segment } from "@/types";
import { WorkflowStage } from "@/types";

// ── Stage Display Labels ──────────────────────────────────────────────────────

const STAGE_LABELS: Record<string, string> = {
  [WorkflowStage.INGEST]: "Ingest",
  [WorkflowStage.DRAFT]: "Draft",
  [WorkflowStage.REVIEW]: "Review",
  [WorkflowStage.APPROVED]: "Approved",
  [WorkflowStage.EXPORTED]: "Exported",
};

// ── Props ─────────────────────────────────────────────────────────────────────

interface ProductFiltersProps {
  searchValue: string;
  onSearchChange: (v: string) => void;
  categoryId: number | null;
  onCategoryChange: (v: number | null) => void;
  segmentId: number | null;
  onSegmentChange: (v: number | null) => void;
  stage: string | null;
  onStageChange: (v: string | null) => void;
  categories: Category[];
  segments: Segment[];
  onClear: () => void;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function hasActiveFilters(
  search: string,
  catId: number | null,
  segId: number | null,
  stg: string | null,
): boolean {
  return search !== "" || catId !== null || segId !== null || stg !== null;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function ProductFilters({
  searchValue,
  onSearchChange,
  categoryId,
  onCategoryChange,
  segmentId,
  onSegmentChange,
  stage,
  onStageChange,
  categories,
  segments,
  onClear,
}: ProductFiltersProps) {
  const showClear = hasActiveFilters(searchValue, categoryId, segmentId, stage);

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
      {/* ── Search ──────────────────────────────────────────────────────── */}
      <div className="relative flex-1">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search by name or SKU…"
          value={searchValue}
          onChange={(e) => onSearchChange(e.target.value)}
          className="pl-9"
        />
      </div>

      {/* ── Category Filter ─────────────────────────────────────────────── */}
      <Select
        value={categoryId != null ? String(categoryId) : "all"}
        onValueChange={(v) =>
          onCategoryChange(v === "all" ? null : Number(v))
        }
      >
        <SelectTrigger className="w-[160px]">
          <SelectValue placeholder="Category" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All Categories</SelectItem>
          {categories.map((cat) => (
            <SelectItem key={cat.id} value={String(cat.id)}>
              {cat.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* ── Segment Filter ──────────────────────────────────────────────── */}
      <Select
        value={segmentId != null ? String(segmentId) : "all"}
        onValueChange={(v) =>
          onSegmentChange(v === "all" ? null : Number(v))
        }
      >
        <SelectTrigger className="w-[160px]">
          <SelectValue placeholder="Segment" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All Segments</SelectItem>
          {segments.map((seg) => (
            <SelectItem key={seg.id} value={String(seg.id)}>
              {seg.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* ── Stage Filter ────────────────────────────────────────────────── */}
      <Select
        value={stage ?? "all"}
        onValueChange={(v) => onStageChange(v === "all" ? null : v)}
      >
        <SelectTrigger className="w-[140px]">
          <SelectValue placeholder="Stage" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All Stages</SelectItem>
          {Object.entries(STAGE_LABELS).map(([value, label]) => (
            <SelectItem key={value} value={value}>
              {label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* ── Clear ───────────────────────────────────────────────────────── */}
      {showClear && (
        <Button
          variant="ghost"
          size="sm"
          onClick={onClear}
          className="shrink-0"
        >
          <X className="mr-1 h-4 w-4" />
          Clear
        </Button>
      )}
    </div>
  );
}
