/**
 * useProducts — data-fetching hook for the product list page.
 *
 * Responsibilities:
 * - Fetch paginated products with search, filter, and sort params
 * - Fetch categories & segments for filter dropdowns
 * - Debounced text search (300 ms)
 * - Client-side sort (column + direction)
 * - CRUD mutations (create, update, delete) with cache-bust reloads
 * - Loading / error / empty states exposed to the UI
 *
 * Dependencies:
 *   lib/api-endpoints (products, categories, segments)
 *   types (ProductListItem, ProductCreate, ProductUpdate, etc.)
 */

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { products, categories, segments } from "@/lib/api-endpoints";
import type {
  ProductListItem,
  ProductCreate,
  ProductUpdate,
  Category,
  Segment,
  PaginatedResponse,
} from "@/types";

// ── Enriched Product ──────────────────────────────────────────────────────────

/**
 * Product list item enriched with resolved names and computed fields
 * so the UI never has to join data from multiple sources.
 */
export interface EnrichedProduct extends ProductListItem {
  category_name: string | null;
  segment_name: string | null;
  claims_count: number;
}

// ── Sortable Columns ──────────────────────────────────────────────────────────

export const PRODUCT_SORT_COLUMNS = [
  "sku",
  "name",
  "category_name",
  "segment_name",
  "workflow_stage",
  "claims_count",
  "updated_at",
] as const;

export type ProductSortColumn = (typeof PRODUCT_SORT_COLUMNS)[number];

export interface SortState {
  column: ProductSortColumn;
  direction: "asc" | "desc";
}

// ── Filter / Query State ─────────────────────────────────────────────────────

export interface ProductFilters {
  search: string;
  categoryId: number | null;
  segmentId: number | null;
  stage: string | null;
}

export interface PaginationState {
  page: number;
  pageSize: number;
}

// ── Return Type ───────────────────────────────────────────────────────────────

export interface UseProductsReturn {
  /** Enriched & sorted products for the current page. */
  products: EnrichedProduct[];
  /** Raw pagination metadata from the API. */
  pagination: {
    page: number;
    pageSize: number;
    total: number;
    totalPages: number;
  };
  /** Reference data for filter dropdowns. */
  categories: Category[];
  segments: Segment[];
  /** Loading / error / empty flags. */
  isLoading: boolean;
  isError: boolean;
  errorMessage: string | null;
  isEmpty: boolean;
  /** Active sort state. */
  sort: SortState;
  /** Active filter state. */
  filters: ProductFilters;
  /** Setters. */
  setSearch: (v: string) => void;
  setCategoryId: (v: number | null) => void;
  setSegmentId: (v: number | null) => void;
  setStage: (v: string | null) => void;
  setPage: (v: number) => void;
  setPageSize: (v: number) => void;
  setSort: (s: SortState) => void;
  clearFilters: () => void;
  /** CRUD operations that reload the list on success. */
  createProduct: (body: ProductCreate) => Promise<EnrichedProduct>;
  updateProduct: (id: number, body: ProductUpdate) => Promise<EnrichedProduct>;
  deleteProduct: (id: number) => Promise<void>;
  /** Force-refresh the product list. */
  refetch: () => void;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 300;
const INITIAL_PAGINATION: PaginationState = { page: 1, pageSize: 10 };

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Resolve category/segment names from ID lists. */
function enrichProducts(
  items: ProductListItem[],
  categoryMap: Map<number, string>,
  segmentMap: Map<number, string>,
): EnrichedProduct[] {
  return items.map((p) => ({
    ...p,
    category_name: p.category_id != null ? categoryMap.get(p.category_id) ?? null : null,
    segment_name: p.segment_id != null ? segmentMap.get(p.segment_id) ?? null : null,
    claims_count: 0, // TODO: populate from backend when list endpoint supports it
  }));
}

/** Client-side sort.  Treats nulls as lowest value regardless of direction. */
function sortProducts(
  list: EnrichedProduct[],
  { column, direction }: SortState,
): EnrichedProduct[] {
  const dir = direction === "asc" ? 1 : -1;

  return [...list].sort((a, b) => {
    const aVal = a[column as keyof EnrichedProduct];
    const bVal = b[column as keyof EnrichedProduct];

    // nulls last
    if (aVal == null && bVal == null) return 0;
    if (aVal == null) return 1;
    if (bVal == null) return -1;

    if (typeof aVal === "string" && typeof bVal === "string") {
      return aVal.localeCompare(bVal) * dir;
    }
    if (typeof aVal === "number" && typeof bVal === "number") {
      return (aVal - bVal) * dir;
    }
    return String(aVal).localeCompare(String(bVal)) * dir;
  });
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useProducts(): UseProductsReturn {
  // ── State ─────────────────────────────────────────────────────────────────
  const [items, setItems] = useState<ProductListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isError, setIsError] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [categoriesList, setCategoriesList] = useState<Category[]>([]);
  const [segmentsList, setSegmentsList] = useState<Segment[]>([]);

  const [filters, setFilters] = useState<ProductFilters>({
    search: "",
    categoryId: null,
    segmentId: null,
    stage: null,
  });
  const [pagination, setPagination] =
    useState<PaginationState>(INITIAL_PAGINATION);
  const [sort, setSort] = useState<SortState>({
    column: "updated_at",
    direction: "desc",
  });

  // Debounce ref for search
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [debouncedSearch, setDebouncedSearch] = useState("");

  // Track whether filters changed to reset to page 1
  const prevFiltersRef = useRef<string>("");

  // ── Debounce Search ──────────────────────────────────────────────────────
  const setSearch = useCallback((v: string) => {
    setFilters((prev) => ({ ...prev, search: v }));
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => setDebouncedSearch(v), DEBOUNCE_MS);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, []);

  // ── Derived Setters ──────────────────────────────────────────────────────
  const setCategoryId = useCallback(
    (v: number | null) => setFilters((p) => ({ ...p, categoryId: v })),
    [],
  );
  const setSegmentId = useCallback(
    (v: number | null) => setFilters((p) => ({ ...p, segmentId: v })),
    [],
  );
  const setStage = useCallback(
    (v: string | null) => setFilters((p) => ({ ...p, stage: v })),
    [],
  );
  const clearFilters = useCallback(() => {
    setFilters({ search: "", categoryId: null, segmentId: null, stage: null });
    setDebouncedSearch("");
  }, []);

  // ── Reset page when filters change ───────────────────────────────────────
  const filtersKey = JSON.stringify({
    ...filters,
    search: debouncedSearch,
  });

  useEffect(() => {
    if (prevFiltersRef.current && prevFiltersRef.current !== filtersKey) {
      setPagination((p) => ({ ...p, page: 1 }));
    }
    prevFiltersRef.current = filtersKey;
  }, [filtersKey]);

  // ── Fetch Reference Data (categories + segments) ─────────────────────────
  const [refDataLoaded, setRefDataLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadRefData() {
      try {
        const [cats, segs] = await Promise.all([
          categories.list(),
          segments.list(),
        ]);
        if (!cancelled) {
          setCategoriesList(cats);
          setSegmentsList(segs);
          setRefDataLoaded(true);
        }
      } catch {
        // Non-fatal — filters will just have fewer options
        if (!cancelled) {
          setRefDataLoaded(true);
        }
      }
    }

    loadRefData();
    return () => { cancelled = true; };
  }, []);

  // ── Fetch Products ───────────────────────────────────────────────────────
  const [fetchKey, setFetchKey] = useState(0);
  const refetch = useCallback(() => setFetchKey((k) => k + 1), []);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setIsLoading(true);
      setIsError(false);
      setErrorMessage(null);

      try {
        const response: PaginatedResponse<ProductListItem> =
          await products.list({
            search: debouncedSearch || undefined,
            category_id: filters.categoryId ?? undefined,
            segment_id: filters.segmentId ?? undefined,
            workflow_stage: filters.stage ?? undefined,
            page: pagination.page,
            page_size: pagination.pageSize,
          });

        if (!cancelled) {
          setItems(response.items);
          setTotal(response.total);
          setTotalPages(response.total_pages);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          setIsError(true);
          setErrorMessage(
            err instanceof Error ? err.message : "Failed to load products",
          );
          setItems([]);
          setTotal(0);
          setTotalPages(0);
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [
    debouncedSearch,
    filters.categoryId,
    filters.segmentId,
    filters.stage,
    pagination.page,
    pagination.pageSize,
    fetchKey,
  ]);

  // ── Build category / segment lookup maps ─────────────────────────────────
  const categoryMap = useMemo(() => {
    const map = new Map<number, string>();
    categoriesList.forEach((c) => map.set(c.id, c.name));
    return map;
  }, [categoriesList]);

  const segmentMap = useMemo(() => {
    const map = new Map<number, string>();
    segmentsList.forEach((s) => map.set(s.id, s.name));
    return map;
  }, [segmentsList]);

  // ── Enrich & Sort ───────────────────────────────────────────────────────
  const enriched = useMemo(
    () => sortProducts(enrichProducts(items, categoryMap, segmentMap), sort),
    [items, categoryMap, segmentMap, sort],
  );

  // ── Derived Flags ────────────────────────────────────────────────────────
  const isEmpty = !isLoading && !isError && items.length === 0;

  // ── CRUD Mutations ───────────────────────────────────────────────────────
  const createProduct = useCallback(
    async (body: ProductCreate): Promise<EnrichedProduct> => {
      const created = await products.create(body);
      refetch();
      // Rebuild enriched from the full response
      return {
        ...created,
        category_name:
          created.category_id != null
            ? categoryMap.get(created.category_id) ?? null
            : null,
        segment_name:
          created.segment_id != null
            ? segmentMap.get(created.segment_id) ?? null
            : null,
        claims_count: created.claims?.length ?? 0,
      };
    },
    [refetch, categoryMap, segmentMap],
  );

  const updateProduct = useCallback(
    async (id: number, body: ProductUpdate): Promise<EnrichedProduct> => {
      const updated = await products.update(id, body);
      refetch();
      return {
        ...updated,
        category_name:
          updated.category_id != null
            ? categoryMap.get(updated.category_id) ?? null
            : null,
        segment_name:
          updated.segment_id != null
            ? segmentMap.get(updated.segment_id) ?? null
            : null,
        claims_count: updated.claims?.length ?? 0,
      };
    },
    [refetch, categoryMap, segmentMap],
  );

  const deleteProduct = useCallback(
    async (id: number): Promise<void> => {
      await products.delete(id);
      refetch();
    },
    [refetch],
  );

  return {
    products: enriched,
    pagination: {
      page: pagination.page,
      pageSize: pagination.pageSize,
      total,
      totalPages,
    },
    categories: categoriesList,
    segments: segmentsList,
    isLoading: isLoading || !refDataLoaded,
    isError,
    errorMessage,
    isEmpty,
    sort,
    filters,
    setSearch,
    setCategoryId,
    setSegmentId,
    setStage,
    setPage: useCallback((v: number) => setPagination((p) => ({ ...p, page: v })), []),
    setPageSize: useCallback(
      (v: number) => setPagination({ page: 1, pageSize: v }),
      [],
    ),
    setSort,
    clearFilters,
    createProduct,
    updateProduct,
    deleteProduct,
    refetch,
  };
}
