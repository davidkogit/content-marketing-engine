import { useState, useMemo } from "react"
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
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
import {
  Search,
  Trash2,
  ExternalLink,
  FileText,
  Globe,
} from "lucide-react"
import { documents } from "@/lib/api-endpoints"
import { useToast } from "@/hooks/use-toast"
import { useAuth } from "@/hooks/use-auth"
import { UserRole } from "@/types/user"
import { DocType } from "@/types/product"
import type { ProductDocument, ProductListItem } from "@/types"

/** Denormalised document row: doc data + product context. */
export interface DocumentRow extends ProductDocument {
  product_name: string
  product_sku: string
}

interface DocumentListProps {
  docs: DocumentRow[]
  products: ProductListItem[]
  loading: boolean
  onRefresh: () => void
  onLinkDocument: (productId: number, productName: string) => void
}

/** Heuristic status derived from extracted_text presence. */
function getProcessingStatus(doc: DocumentRow): "processed" | "pending" {
  return doc.extracted_text ? "processed" : "pending"
}

const DOC_TYPE_ICON: Record<string, React.ReactNode> = {
  [DocType.PDF]: <FileText className="h-3.5 w-3.5" />,
  [DocType.URL]: <Globe className="h-3.5 w-3.5" />,
}

export function DocumentList({
  docs,
  products,
  loading,
  onRefresh,
  onLinkDocument,
}: DocumentListProps) {
  const { toast } = useToast()
  const { hasRole } = useAuth()
  const canDelete = hasRole(UserRole.ADMIN)

  const [search, setSearch] = useState("")
  const [productFilter, setProductFilter] = useState("all")
  const [deleteTarget, setDeleteTarget] = useState<DocumentRow | null>(null)
  const [deleting, setDeleting] = useState(false)

  // ── Filtering ─────────────────────────────────────────────────────────

  const filtered = useMemo(() => {
    let result = docs
    const query = search.toLowerCase().trim()
    if (query) {
      result = result.filter(
        (d) =>
          d.title.toLowerCase().includes(query) ||
          d.url.toLowerCase().includes(query) ||
          d.product_name.toLowerCase().includes(query),
      )
    }
    if (productFilter !== "all") {
      const pid = Number(productFilter)
      if (!isNaN(pid)) {
        result = result.filter((d) => d.product_id === pid)
      }
    }
    return result
  }, [docs, search, productFilter])

  // ── Delete ────────────────────────────────────────────────────────────

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await documents.delete(deleteTarget.id)
      toast({ title: "Document removed", variant: "success" })
      setDeleteTarget(null)
      onRefresh()
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? "Delete failed."
      toast({ title: "Error", description: msg, variant: "destructive" })
    } finally {
      setDeleting(false)
    }
  }

  // ── Empty state ───────────────────────────────────────────────────────

  if (!loading && docs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <FileText className="h-12 w-12 text-muted-foreground/50 mb-4" />
        <p className="text-muted-foreground mb-2">No documents linked yet.</p>
        <p className="text-sm text-muted-foreground mb-4">
          Link source documents to products to enable content generation.
        </p>
        {products.length > 0 && canDelete && (
          <Button
            variant="outline"
            onClick={() => onLinkDocument(products[0].id, products[0].name)}
          >
            Link your first document
          </Button>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* ── Filters Bar ──────────────────────────────────────────────── */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search documents…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select
          value={productFilter}
          onValueChange={setProductFilter}
        >
          <SelectTrigger className="w-full sm:w-[220px]">
            <SelectValue placeholder="Filter by product" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All products</SelectItem>
            {products.map((p) => (
              <SelectItem key={p.id} value={String(p.id)}>
                {p.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* ── Table ────────────────────────────────────────────────────── */}
      {filtered.length === 0 ? (
        <div className="py-12 text-center text-muted-foreground">
          No documents match your search or filter.
        </div>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[25%]">Title</TableHead>
                <TableHead className="w-[18%]">Product</TableHead>
                <TableHead className="w-[8%]">Type</TableHead>
                <TableHead className="w-[12%]">Status</TableHead>
                <TableHead className="w-[10%]">Date</TableHead>
                {canDelete && (
                  <TableHead className="w-[10%] text-right">Actions</TableHead>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((doc) => {
                const status = getProcessingStatus(doc)
                return (
                  <TableRow key={doc.id}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <span className="truncate max-w-[220px] font-medium">
                          {doc.title}
                        </span>
                        <a
                          href={doc.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="shrink-0 text-muted-foreground hover:text-foreground"
                          title="Open URL"
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                        </a>
                      </div>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {doc.product_name}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="gap-1">
                        {DOC_TYPE_ICON[doc.doc_type] ?? null}
                        {doc.doc_type.toUpperCase()}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={status === "processed" ? "success" : "warning"}
                      >
                        {status === "processed" ? "Processed" : "Pending"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">
                      {new Date(doc.created_at).toLocaleDateString()}
                    </TableCell>
                    {canDelete && (
                      <TableCell className="text-right">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-destructive"
                          onClick={() => setDeleteTarget(doc)}
                          title="Delete document"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    )}
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Delete Confirmation */}
      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove Document</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to remove{" "}
              <strong>{deleteTarget?.title}</strong> from{" "}
              <strong>{deleteTarget?.product_name}</strong>? Its associated
              claims will also be deleted. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              disabled={deleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleting ? "Removing…" : "Remove"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
