import { useCallback, useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { CategoryForm } from "@/components/categories/category-form"
import { CategoryList } from "@/components/categories/category-list"
import { categories } from "@/lib/api-endpoints"
import { useAuth } from "@/hooks/use-auth"
import { UserRole } from "@/types/user"
import { Plus, RefreshCw, AlertCircle } from "lucide-react"
import type { Category } from "@/types"

export default function CategoriesPage() {
  const { hasRole } = useAuth()
  const canCreate = hasRole(UserRole.ADMIN)

  const [items, setItems] = useState<Category[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<Category | null>(null)

  const fetchCategories = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await categories.list()
      setItems(data)
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? err?.message ?? "Failed to load categories."
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchCategories()
  }, [fetchCategories])

  const handleEdit = (category: Category) => {
    setEditTarget(category)
    setFormOpen(true)
  }

  const handleFormSuccess = () => {
    setEditTarget(null)
    fetchCategories()
  }

  const handleFormOpenChange = (open: boolean) => {
    if (!open) setEditTarget(null)
    setFormOpen(open)
  }

  return (
    <div className="space-y-6">
      {/* ── Page Header ──────────────────────────────────────────────── */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight md:text-3xl">
            Categories
          </h1>
          <p className="text-muted-foreground">
            Organize products into categories for structured content management.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="icon"
            onClick={fetchCategories}
            disabled={loading}
            title="Refresh"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </Button>
          {canCreate && (
            <Button onClick={() => setFormOpen(true)}>
              <Plus className="h-4 w-4" />
              <span className="hidden sm:inline">New Category</span>
            </Button>
          )}
        </div>
      </div>

      {/* ── Content ────────────────────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">All Categories</CardTitle>
          <CardDescription>
            {loading
              ? "Loading…"
              : `${items.length} categor${items.length === 1 ? "y" : "ies"}`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {/* Loading state */}
          {loading && (
            <div className="space-y-3">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          )}

          {/* Error state */}
          {!loading && error && (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <AlertCircle className="h-10 w-10 text-destructive mb-3" />
              <p className="text-destructive font-medium mb-1">
                Failed to load categories
              </p>
              <p className="text-sm text-muted-foreground mb-4">{error}</p>
              <Button variant="outline" onClick={fetchCategories}>
                <RefreshCw className="h-4 w-4 mr-1" /> Retry
              </Button>
            </div>
          )}

          {/* Data */}
          {!loading && !error && (
            <CategoryList
              items={items}
              onRefresh={fetchCategories}
              onEdit={handleEdit}
            />
          )}
        </CardContent>
      </Card>

      {/* ── Create / Edit Dialog ───────────────────────────────────── */}
      <CategoryForm
        open={formOpen}
        onOpenChange={handleFormOpenChange}
        category={editTarget}
        onSuccess={handleFormSuccess}
      />
    </div>
  )
}
