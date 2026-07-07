/**
 * ProductsPage — the full product list page with search, filters,
 * CRUD forms, delete confirmation, and sortable / paginated table.
 *
 * Composes the following children:
 *   ProductFilters    — search + category/segment/stage dropdowns
 *   ProductTable      — sortable table (md+) / card list (mobile)
 *   ProductForm       — create/edit dialog
 *   ProductDeleteDialog — destructive confirmation (super_admin only)
 *
 * Data and state management are delegated to the useProducts() hook.
 * Auth context provides role checks for the delete action.
 */

import { useState, useCallback } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/hooks/use-auth";
import { useToast } from "@/hooks/use-toast";
import { useProducts } from "@/hooks/use-products";
import type { EnrichedProduct } from "@/hooks/use-products";
import { ProductFilters } from "@/components/products/product-filters";
import { ProductTable } from "@/components/products/product-table";
import { ProductForm } from "@/components/products/product-form";
import { ProductDeleteDialog } from "@/components/products/product-delete-dialog";
import type { ProductCreate, ProductUpdate } from "@/types";

// ── Component ─────────────────────────────────────────────────────────────────

export default function ProductsPage() {
  const { toast } = useToast();
  const { hasRole } = useAuth();
  const canDelete = hasRole("super_admin");

  const {
    products,
    pagination,
    categories,
    segments,
    isLoading,
    isError,
    errorMessage,
    isEmpty,
    sort,
    filters,
    setSearch,
    setCategoryId,
    setSegmentId,
    setStage,
    setPage,
    setPageSize,
    setSort,
    clearFilters,
    createProduct,
    updateProduct,
    deleteProduct,
    refetch,
  } = useProducts();

  // ── Dialog State ────────────────────────────────────────────────────────
  const [formOpen, setFormOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState<EnrichedProduct | null>(
    null,
  );
  const [formSubmitting, setFormSubmitting] = useState(false);

  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deletingProduct, setDeletingProduct] =
    useState<EnrichedProduct | null>(null);
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);

  // ── Open Create Dialog ──────────────────────────────────────────────────
  const openCreate = useCallback(() => {
    setEditingProduct(null);
    setFormOpen(true);
  }, []);

  // ── Open Edit Dialog ────────────────────────────────────────────────────
  const openEdit = useCallback((p: EnrichedProduct) => {
    setEditingProduct(p);
    setFormOpen(true);
  }, []);

  // ── Close Form ──────────────────────────────────────────────────────────
  const closeForm = useCallback(() => {
    setFormOpen(false);
    setEditingProduct(null);
  }, []);

  // ── Open Delete Dialog ──────────────────────────────────────────────────
  const openDelete = useCallback(
    (p: EnrichedProduct) => {
      if (!canDelete) return;
      setDeletingProduct(p);
      setDeleteOpen(true);
    },
    [canDelete],
  );

  // ── Close Delete ────────────────────────────────────────────────────────
  const closeDelete = useCallback(() => {
    setDeleteOpen(false);
    setDeletingProduct(null);
  }, []);

  // ── Submit Create / Update ──────────────────────────────────────────────
  const handleFormSubmit = useCallback(
    async (data: ProductCreate, editId?: number) => {
      setFormSubmitting(true);
      try {
        if (editId != null) {
          const updateData: ProductUpdate = {
            name: data.name,
            description: data.description,
            category_id: data.category_id,
            segment_id: data.segment_id,
          };
          await updateProduct(editId, updateData);
          toast({ title: "Product updated", description: data.name });
        } else {
          await createProduct(data);
          toast({ title: "Product created", description: data.name });
        }
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : "Something went wrong";
        toast({
          title: "Error",
          description: message,
          variant: "destructive",
        });
        throw err; // keep dialog open so user can retry
      } finally {
        setFormSubmitting(false);
      }
    },
    [createProduct, updateProduct, toast],
  );

  // ── Confirm Delete ──────────────────────────────────────────────────────
  const handleDeleteConfirm = useCallback(async () => {
    if (!deletingProduct) return;
    setDeleteSubmitting(true);
    try {
      await deleteProduct(deletingProduct.id);
      toast({
        title: "Product deleted",
        description: deletingProduct.name,
      });
      closeDelete();
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to delete product";
      toast({
        title: "Error",
        description: message,
        variant: "destructive",
      });
    } finally {
      setDeleteSubmitting(false);
    }
  }, [deletingProduct, deleteProduct, closeDelete, toast]);

  // ── Has Active Filters ─────────────────────────────────────────────────
  const hasActiveFilters =
    filters.search !== "" ||
    filters.categoryId !== null ||
    filters.segmentId !== null ||
    filters.stage !== null;

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div className="container mx-auto flex flex-col gap-6 p-4 sm:p-6 lg:p-8">
      {/* ── Page Header ────────────────────────────────────────────────── */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">
            Products
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Manage your product information, content pipeline, and claims.
          </p>
        </div>

        <Button onClick={openCreate}>
          <Plus className="mr-2 h-4 w-4" />
          Create Product
        </Button>
      </div>

      {/* ── Filters ────────────────────────────────────────────────────── */}
      <ProductFilters
        searchValue={filters.search}
        onSearchChange={setSearch}
        categoryId={filters.categoryId}
        onCategoryChange={setCategoryId}
        segmentId={filters.segmentId}
        onSegmentChange={setSegmentId}
        stage={filters.stage}
        onStageChange={setStage}
        categories={categories}
        segments={segments}
        onClear={clearFilters}
      />

      {/* ── Error Banner ───────────────────────────────────────────────── */}
      {isError && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <p className="font-medium">Failed to load products</p>
          {errorMessage && (
            <p className="mt-1 text-destructive/80">{errorMessage}</p>
          )}
          <Button
            variant="link"
            size="sm"
            className="mt-1 h-auto p-0 text-destructive underline"
            onClick={refetch}
          >
            Try again
          </Button>
        </div>
      )}

      {/* ── Table / Cards ──────────────────────────────────────────────── */}
      <ProductTable
        products={products}
        sort={sort}
        onSortChange={setSort}
        isLoading={isLoading}
        isEmpty={isEmpty}
        hasActiveFilters={hasActiveFilters}
        pagination={pagination}
        onPageChange={setPage}
        onPageSizeChange={setPageSize}
        onEdit={openEdit}
        onDelete={openDelete}
        onCreate={openCreate}
        canDelete={canDelete}
      />

      {/* ── Create / Edit Dialog ────────────────────────────────────────── */}
      <ProductForm
        open={formOpen}
        onClose={closeForm}
        product={
          editingProduct
            ? {
                id: editingProduct.id,
                sku: editingProduct.sku,
                name: editingProduct.name,
                description: editingProduct.description,
                category_id: editingProduct.category_id,
                segment_id: editingProduct.segment_id,
              }
            : null
        }
        categories={categories}
        segments={segments}
        onSubmit={handleFormSubmit}
        isSubmitting={formSubmitting}
      />

      {/* ── Delete Dialog ───────────────────────────────────────────────── */}
      <ProductDeleteDialog
        open={deleteOpen}
        onClose={closeDelete}
        product={
          deletingProduct
            ? { sku: deletingProduct.sku, name: deletingProduct.name }
            : null
        }
        onConfirm={handleDeleteConfirm}
        isDeleting={deleteSubmitting}
      />
    </div>
  );
}
