/**
 * ProductDeleteDialog — destructive confirmation dialog for deleting a product.
 *
 * This action is restricted to super_admin users.  The dialog renders
 * nothing when the user lacks the required role (enforced by the parent
 * via the `open` / `showButton` props).
 *
 * The dialog prompts the user to confirm the delete, listing the
 * product SKU and name so there are no accidental deletions.
 */

import { AlertTriangle, Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

// ── Props ─────────────────────────────────────────────────────────────────────

interface ProductDeleteDialogProps {
  open: boolean;
  onClose: () => void;
  /** Product info shown in the confirmation message. */
  product: { sku: string; name: string } | null;
  /** Called when the user confirms deletion. */
  onConfirm: () => Promise<void>;
  /** Whether the delete request is in flight. */
  isDeleting?: boolean;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function ProductDeleteDialog({
  open,
  onClose,
  product,
  onConfirm,
  isDeleting = false,
}: ProductDeleteDialogProps) {
  if (!product) return null;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader className="gap-2">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
            <AlertTriangle className="h-6 w-6 text-destructive" />
          </div>
          <DialogTitle className="text-center">Delete Product</DialogTitle>
          <DialogDescription className="text-center">
            Are you sure you want to delete{" "}
            <span className="font-semibold text-foreground">
              {product.name}
            </span>{" "}
            <span className="text-muted-foreground">({product.sku})</span>?
            This action cannot be undone.
          </DialogDescription>
        </DialogHeader>

        <DialogFooter className="sm:justify-center">
          <Button
            variant="outline"
            onClick={onClose}
            disabled={isDeleting}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={onConfirm}
            disabled={isDeleting}
          >
            {isDeleting && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            Delete Product
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
