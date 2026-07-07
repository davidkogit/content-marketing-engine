import { useState, useEffect } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { categories } from "@/lib/api-endpoints"
import { useToast } from "@/hooks/use-toast"
import type { Category, CategoryCreate, CategoryUpdate } from "@/types"

interface CategoryFormProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  category?: Category | null
  onSuccess: (category: Category) => void
}

export function CategoryForm({
  open,
  onOpenChange,
  category,
  onSuccess,
}: CategoryFormProps) {
  const { toast } = useToast()
  const isEditing = !!category

  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [nameError, setNameError] = useState("")

  useEffect(() => {
    if (open && category) {
      setName(category.name)
      setDescription(category.description ?? "")
    } else if (open) {
      setName("")
      setDescription("")
    }
    setNameError("")
  }, [open, category])

  const validate = (): boolean => {
    const trimmed = name.trim()
    if (!trimmed) {
      setNameError("Name is required.")
      return false
    }
    if (trimmed.length > 120) {
      setNameError("Name must be 120 characters or fewer.")
      return false
    }
    setNameError("")
    return true
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!validate()) return

    setSubmitting(true)
    try {
      if (isEditing && category) {
        const payload: CategoryUpdate = { name: name.trim() }
        if (description !== (category.description ?? "")) {
          payload.description = description.trim() || null
        }
        const updated = await categories.update(category.id, payload)
        toast({ title: "Category updated", variant: "success" })
        onSuccess(updated)
      } else {
        const payload: CategoryCreate = {
          name: name.trim(),
          description: description.trim() || null,
        }
        const created = await categories.create(payload)
        toast({ title: "Category created", variant: "success" })
        onSuccess(created)
      }
      onOpenChange(false)
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail ?? err?.message ?? "An error occurred."
      if (msg.toLowerCase().includes("already exists")) {
        setNameError("A category with this name already exists.")
      } else {
        toast({ title: "Error", description: msg, variant: "destructive" })
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{isEditing ? "Edit Category" : "New Category"}</DialogTitle>
          <DialogDescription>
            {isEditing
              ? "Update the category details below."
              : "Create a new product category. Category names must be unique."}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="cat-name">Name *</Label>
            <Input
              id="cat-name"
              value={name}
              onChange={(e) => {
                setName(e.target.value)
                if (nameError) setNameError("")
              }}
              placeholder="e.g. Electronics"
              maxLength={120}
              disabled={submitting}
              aria-invalid={!!nameError}
            />
            {nameError && (
              <p className="text-sm text-destructive">{nameError}</p>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="cat-desc">Description</Label>
            <Textarea
              id="cat-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Optional description of this category"
              rows={3}
              disabled={submitting}
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Saving…" : isEditing ? "Save Changes" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
