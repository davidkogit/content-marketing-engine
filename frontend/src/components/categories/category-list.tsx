import { useState } from "react"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Pencil, Trash2, Check, X } from "lucide-react"
import { categories } from "@/lib/api-endpoints"
import { useToast } from "@/hooks/use-toast"
import { useAuth } from "@/hooks/use-auth"
import { UserRole } from "@/types/user"
import type { Category } from "@/types"

interface CategoryListProps {
  items: Category[]
  onRefresh: () => void
  onEdit: (category: Category) => void
}

export function CategoryList({ items, onRefresh, onEdit }: CategoryListProps) {
  const { toast } = useToast()
  const { hasRole } = useAuth()
  const canEdit = hasRole(UserRole.ADMIN)

  const [editingId, setEditingId] = useState<number | null>(null)
  const [editName, setEditName] = useState("")
  const [editDesc, setEditDesc] = useState("")
  const [deleteTarget, setDeleteTarget] = useState<Category | null>(null)
  const [deleting, setDeleting] = useState(false)

  // ── Inline Edit Handlers ──────────────────────────────────────────────

  const startEditing = (cat: Category) => {
    setEditingId(cat.id)
    setEditName(cat.name)
    setEditDesc(cat.description ?? "")
  }

  const cancelEditing = () => {
    setEditingId(null)
    setEditName("")
    setEditDesc("")
  }

  const saveEditing = async (id: number) => {
    const trimmed = editName.trim()
    if (!trimmed) {
      toast({ title: "Name is required.", variant: "destructive" })
      return
    }
    try {
      await categories.update(id, {
        name: trimmed,
        description: editDesc.trim() || null,
      })
      toast({ title: "Category updated", variant: "success" })
      cancelEditing()
      onRefresh()
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? "Update failed."
      toast({ title: "Error", description: msg, variant: "destructive" })
    }
  }

  // ── Delete Handlers ───────────────────────────────────────────────────

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await categories.delete(deleteTarget.id)
      toast({ title: "Category deleted", variant: "success" })
      setDeleteTarget(null)
      onRefresh()
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? "Delete failed."
      toast({ title: "Error", description: msg, variant: "destructive" })
    } finally {
      setDeleting(false)
    }
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <p className="text-muted-foreground mb-2">No categories found.</p>
        <p className="text-sm text-muted-foreground">
          Create your first category to start organizing products.
        </p>
      </div>
    )
  }

  return (
    <>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[30%]">Name</TableHead>
              <TableHead className="w-[40%]">Description</TableHead>
              <TableHead className="w-[15%] text-right">Products</TableHead>
              {canEdit && <TableHead className="w-[15%] text-right">Actions</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((cat) => (
              <TableRow key={cat.id}>
                {/* Name cell — inline-editable */}
                <TableCell className="font-medium">
                  {editingId === cat.id ? (
                    <Input
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      className="h-8"
                      autoFocus
                    />
                  ) : (
                    <span
                      className={canEdit ? "cursor-pointer hover:underline" : ""}
                      onClick={canEdit ? () => startEditing(cat) : undefined}
                      title={canEdit ? "Click to edit" : undefined}
                    >
                      {cat.name}
                    </span>
                  )}
                </TableCell>
                {/* Description cell — inline-editable */}
                <TableCell className="text-muted-foreground">
                  {editingId === cat.id ? (
                    <Input
                      value={editDesc}
                      onChange={(e) => setEditDesc(e.target.value)}
                      className="h-8"
                      placeholder="Description (optional)"
                    />
                  ) : (
                    <span
                      className={canEdit ? "cursor-pointer hover:underline" : ""}
                      onClick={canEdit ? () => startEditing(cat) : undefined}
                      title={canEdit ? "Click to edit" : undefined}
                    >
                      {cat.description || "—"}
                    </span>
                  )}
                </TableCell>
                {/* Product count */}
                <TableCell className="text-right">
                  <Badge variant="secondary">{cat.product_count}</Badge>
                </TableCell>
                {/* Actions */}
                {canEdit && (
                  <TableCell className="text-right">
                    {editingId === cat.id ? (
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-green-600"
                          onClick={() => saveEditing(cat.id)}
                          title="Save"
                        >
                          <Check className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          onClick={cancelEditing}
                          title="Cancel"
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </div>
                    ) : (
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          onClick={() => onEdit(cat)}
                          title="Edit in dialog"
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-destructive"
                          onClick={() => setDeleteTarget(cat)}
                          title={
                            cat.product_count > 0
                              ? "Cannot delete: products exist"
                              : "Delete category"
                          }
                          disabled={cat.product_count > 0}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    )}
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Delete Confirmation AlertDialog */}
      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Category</AlertDialogTitle>
            <AlertDialogDescription>
              {deleteTarget?.product_count && deleteTarget.product_count > 0 ? (
                <>
                  This category has{" "}
                  <strong>{deleteTarget.product_count} product(s)</strong>{" "}
                  assigned to it. You must reassign or remove them before
                  deleting.
                </>
              ) : (
                <>
                  Are you sure you want to delete{" "}
                  <strong>{deleteTarget?.name}</strong>? This action cannot be
                  undone.
                </>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
            {(deleteTarget?.product_count ?? 0) === 0 && (
              <AlertDialogAction
                onClick={handleDelete}
                disabled={deleting}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                {deleting ? "Deleting…" : "Delete"}
              </AlertDialogAction>
            )}
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
