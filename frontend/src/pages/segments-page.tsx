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
import { SegmentForm } from "@/components/segments/segment-form"
import { SegmentList } from "@/components/segments/segment-list"
import { segments } from "@/lib/api-endpoints"
import { useAuth } from "@/hooks/use-auth"
import { UserRole } from "@/types/user"
import { Plus, RefreshCw, AlertCircle } from "lucide-react"
import type { Segment } from "@/types"

export default function SegmentsPage() {
  const { hasRole } = useAuth()
  const canCreate = hasRole(UserRole.ADMIN)

  const [items, setItems] = useState<Segment[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<Segment | null>(null)

  const fetchSegments = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await segments.list()
      setItems(data)
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail ?? err?.message ?? "Failed to load segments."
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchSegments()
  }, [fetchSegments])

  const handleEdit = (segment: Segment) => {
    setEditTarget(segment)
    setFormOpen(true)
  }

  const handleFormSuccess = () => {
    setEditTarget(null)
    fetchSegments()
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
            Market Segments
          </h1>
          <p className="text-muted-foreground">
            Define target audiences and tone profiles for personalised content.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="icon"
            onClick={fetchSegments}
            disabled={loading}
            title="Refresh"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </Button>
          {canCreate && (
            <Button onClick={() => setFormOpen(true)}>
              <Plus className="h-4 w-4" />
              <span className="hidden sm:inline">New Segment</span>
            </Button>
          )}
        </div>
      </div>

      {/* ── Content ────────────────────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">All Segments</CardTitle>
          <CardDescription>
            {loading
              ? "Loading…"
              : `${items.length} segment${items.length === 1 ? "" : "s"}`}
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
                Failed to load segments
              </p>
              <p className="text-sm text-muted-foreground mb-4">{error}</p>
              <Button variant="outline" onClick={fetchSegments}>
                <RefreshCw className="h-4 w-4 mr-1" /> Retry
              </Button>
            </div>
          )}

          {/* Data */}
          {!loading && !error && (
            <SegmentList
              items={items}
              onRefresh={fetchSegments}
              onEdit={handleEdit}
            />
          )}
        </CardContent>
      </Card>

      {/* ── Create / Edit Dialog ───────────────────────────────────── */}
      <SegmentForm
        open={formOpen}
        onOpenChange={handleFormOpenChange}
        segment={editTarget}
        onSuccess={handleFormSuccess}
      />
    </div>
  )
}
