/**
 * ProductForm — create/edit product dialog.
 *
 * Used in both "create" and "edit" modes. When a product is passed
 * via the `product` prop the form pre-fills all fields; otherwise
 * it starts empty for a new product.
 *
 * Submits via `onSubmit(sku, name, description, categoryId, segmentId)`.
 */

import { useState, useEffect, type FormEvent } from "react";
import { Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Category, Segment, ProductCreate } from "@/types";

// ── Props ─────────────────────────────────────────────────────────────────────

interface ProductFormProps {
  /** Whether the dialog is open. */
  open: boolean;
  /** Called when the dialog should close (cancel / backdrop click). */
  onClose: () => void;
  /**
   * When provided the form operates in "edit" mode and pre-fills all
   * fields.  SKU is read-only in edit mode.
   */
  product?: {
    id: number;
    sku: string;
    name: string;
    description: string | null;
    category_id: number | null;
    segment_id: number | null;
  } | null;
  /** Reference data for the dropdowns. */
  categories: Category[];
  segments: Segment[];
  /** Called on submit. */
  onSubmit: (
    data: ProductCreate,
    editId?: number,
  ) => Promise<void>;
  /** Whether a submit is in progress. */
  isSubmitting?: boolean;
}

// ── Validation ────────────────────────────────────────────────────────────────

interface FieldErrors {
  sku?: string;
  name?: string;
}

function validate(sku: string, name: string, isEdit: boolean): FieldErrors {
  const errors: FieldErrors = {};
  if (!isEdit && sku.trim().length === 0) {
    errors.sku = "SKU is required";
  }
  if (name.trim().length === 0) {
    errors.name = "Name is required";
  }
  return errors;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function ProductForm({
  open,
  onClose,
  product,
  categories,
  segments,
  onSubmit,
  isSubmitting = false,
}: ProductFormProps) {
  const isEdit = product != null;

  // ── Local form state ────────────────────────────────────────────────────
  const [sku, setSku] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [segmentId, setSegmentId] = useState<number | null>(null);
  const [errors, setErrors] = useState<FieldErrors>({});

  // ── Populate fields when `product` changes ──────────────────────────────
  useEffect(() => {
    if (open) {
      if (product) {
        setSku(product.sku);
        setName(product.name);
        setDescription(product.description ?? "");
        setCategoryId(product.category_id);
        setSegmentId(product.segment_id);
      } else {
        setSku("");
        setName("");
        setDescription("");
        setCategoryId(null);
        setSegmentId(null);
      }
      setErrors({});
    }
  }, [open, product]);

  // ── Submit Handler ──────────────────────────────────────────────────────
  async function handleSubmit(e: FormEvent) {
    e.preventDefault();

    const fieldErrors = validate(sku, name, isEdit);
    if (Object.keys(fieldErrors).length > 0) {
      setErrors(fieldErrors);
      return;
    }

    const data: ProductCreate = {
      sku: sku.trim(),
      name: name.trim(),
      description: description.trim() || null,
      category_id: categoryId,
      segment_id: segmentId,
    };

    try {
      await onSubmit(data, isEdit ? product!.id : undefined);
      onClose();
    } catch {
      // Error handling is delegated to the parent (toast, etc.)
    }
  }

  // ── Render ──────────────────────────────────────────────────────────────
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Edit Product" : "Create Product"}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? "Update the product details below."
              : "Fill in the details to create a new product."}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {/* ── SKU ────────────────────────────────────────────────────── */}
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="pf-sku"
              className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
            >
              SKU
            </label>
            <Input
              id="pf-sku"
              placeholder="e.g. ACME-001"
              value={sku}
              onChange={(e) => {
                setSku(e.target.value);
                if (errors.sku) setErrors((p) => ({ ...p, sku: undefined }));
              }}
              disabled={isEdit || isSubmitting}
            />
            {errors.sku && (
              <p className="text-xs text-destructive">{errors.sku}</p>
            )}
          </div>

          {/* ── Name ───────────────────────────────────────────────────── */}
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="pf-name"
              className="text-sm font-medium leading-none"
            >
              Name
            </label>
            <Input
              id="pf-name"
              placeholder="Product name"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                if (errors.name) setErrors((p) => ({ ...p, name: undefined }));
              }}
              disabled={isSubmitting}
            />
            {errors.name && (
              <p className="text-xs text-destructive">{errors.name}</p>
            )}
          </div>

          {/* ── Description ────────────────────────────────────────────── */}
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="pf-desc"
              className="text-sm font-medium leading-none"
            >
              Description
            </label>
            <Textarea
              id="pf-desc"
              placeholder="Optional description…"
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={isSubmitting}
            />
          </div>

          {/* ── Category ───────────────────────────────────────────────── */}
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium leading-none">
              Category
            </label>
            <Select
              value={categoryId != null ? String(categoryId) : "none"}
              onValueChange={(v) =>
                setCategoryId(v === "none" ? null : Number(v))
              }
              disabled={isSubmitting}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select category" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">None</SelectItem>
                {categories.map((cat) => (
                  <SelectItem key={cat.id} value={String(cat.id)}>
                    {cat.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* ── Segment ────────────────────────────────────────────────── */}
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium leading-none">
              Segment
            </label>
            <Select
              value={segmentId != null ? String(segmentId) : "none"}
              onValueChange={(v) =>
                setSegmentId(v === "none" ? null : Number(v))
              }
              disabled={isSubmitting}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select segment" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">None</SelectItem>
                {segments.map((seg) => (
                  <SelectItem key={seg.id} value={String(seg.id)}>
                    {seg.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* ── Actions ────────────────────────────────────────────────── */}
          <DialogFooter className="mt-2">
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              {isEdit ? "Save Changes" : "Create Product"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
