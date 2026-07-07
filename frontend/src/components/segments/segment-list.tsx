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
import { segments } from "@/lib/api-endpoints"
import { useToast } from "@/hooks/use-toast"
import { useAuth } from "@/hooks/use-auth"
import { UserRole } from "@/types/user"
import type { Segment } from "@/types"

const TONE_LABEL: Record<string, string> = {
  professional: "Professional",
  casual: "Casual",
  technical: "Technical",
  persuasive: "Persuasive",
}

interface SegmentListProps {
  items: Segment[]
  onRefresh: () => void
  onEdit: (segment: Segment) => void
}

export function SegmentList({ items, onRefresh, onEdit }: SegmentListProps) {
  const { toast } = useToast()
  const { hasRole } = useAuth()
  const canEdit = hasRole(UserRole.ADMIN)

  const [editingId, setEditingId] = useState<number | null>(null)
  const [editName, setEditName] = useState("")
  const [editDesc, setEditDesc] = useState("")
  const [deleteTarget, setDeleteTarget] = useState<Segment | null>(null)
  const [deleting, setDeleting] = useState(false)

  // ── Inline Edit Handlers ──────────────────────────────────────────────

  const startEditing = (seg: Segment) => {
    setEditingId(seg.id)
    setEditName(seg.name)
    setEditDesc(seg.description ?? "")
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
      await segments.update(id, {
        name: trimmed,
        description: editDesc.trim() || null,
      })
      toast({ title: "Segment updated", variant: "success" })
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
      await segments.delete(deleteTarget.id)
      toast({ title: "Segment deleted", variant: "success" })
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
        <p className="text-muted-foreground mb-2">No segments found.</p>
        <p className="text-sm text-muted-foreground">
          Create your first market segment to target specific audiences.
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
              <TableHead className="w-[20%]">Name</TableHead>
              <TableHead className="w-[25%]">Description</TableHead>
              <TableHead className="w-[20%]">Target Audience</TableHead>
              <TableHead className="w-[10%]">Tone</TableHead>
              <TableHead className="w-[10%] text-right">Products</TableHead>
              {canEdit && (
                <TableHead className="w-[15%] text-right">Actions</TableHead>
              )}
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((seg) => (
              <TableRow key={seg.id}>
                {/* Name — inline-editable */}
                <TableCell className="font-medium">
                  {editingId === seg.id ? (
                    <Input
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      className="h-8"
                      autoFocus
                    />
                  ) : (
                    <span
                      className={
                        canEdit ? "cursor-pointer hover:underline" : ""
                      }
                      onClick={canEdit ? () => startEditing(seg) : undefined}
                      title={canEdit ? "Click to edit" : undefined}
                    >
                      {seg.name}
                    </span>
                  )}
                </TableCell>
                {/* Description — inline-editable */}
                <TableCell className="text-muted-foreground">
                  {editingId === seg.id ? (
                    <Input
                      value={editDesc}
                      onChange={(e) => setEditDesc(e.target.value)}
                      className="h-8"
                      placeholder="Description (optional)"
                    />
                  ) : (
                    <span
                      className={
                        canEdit ? "cursor-pointer hover:underline" : ""
                      }
                      onClick={canEdit ? () => startEditing(seg) : undefined}
                      title={canEdit ? "Click to edit" : undefined}
                    >
                      {seg.description || "—"}
                    </span>
                  )}
                </TableCell>
                {/* Target Audience */}
                <TableCell className="text-muted-foreground">
                  {seg.target_audience || "—"}
                </TableCell>
                {/* Tone */}
                <TableCell>
                  {seg.tone ? (
                    <Badge variant="outline">
                      {TONE_LABEL[seg.tone] ?? seg.tone}
                    </Badge>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                {/* Product count */}
                <TableCell className="text-right">
                  <Badge variant="secondary">{seg.product_count}</Badge>
                </TableCell>
                {/* Actions */}
                {canEdit && (
                  <TableCell className="text-right">
                    {editingId === seg.id ? (
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-green-600"
                          onClick={() => saveEditing(seg.id)}
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
                          onClick={() => onEdit(seg)}
                          title="Edit in dialog"
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-destructive"
                          onClick={() => setDeleteTarget(seg)}
                          title={
                            seg.product_count > 0
                              ? "Cannot delete: products exist"
                              : "Delete segment"
                          }
                          disabled={seg.product_count > 0}
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
            <AlertDialogTitle>Delete Segment</AlertDialogTitle>
            <AlertDialogDescription>
              {deleteTarget?.product_count && deleteTarget.product_count > 0 ? (
                <>
                  This segment has{" "}
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
