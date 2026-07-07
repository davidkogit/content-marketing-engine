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
import {
  DocumentList,
  type DocumentRow,
} from "@/components/documents/document-list"
import { DocumentLinkForm } from "@/components/documents/document-link-form"
import { documents, products as productsApi } from "@/lib/api-endpoints"
import { useAuth } from "@/hooks/use-auth"
import { UserRole } from "@/types/user"
import { Plus, RefreshCw, AlertCircle } from "lucide-react"
import type { ProductListItem, ProductDocument } from "@/types"

export default function DocumentsPage() {
  const { hasRole } = useAuth()
  const canLink = hasRole(UserRole.ADMIN)

  const [docRows, setDocRows] = useState<DocumentRow[]>([])
  const [productList, setProductList] = useState<ProductListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [linkFormOpen, setLinkFormOpen] = useState(false)
  const [linkProductId, setLinkProductId] = useState<number | null>(null)
  const [linkProductName, setLinkProductName] = useState("")

  // ── Fetch all documents by aggregating across products ──────────────

  const fetchAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      // Fetch all products (paginated, get all pages)
      const allProducts: ProductListItem[] = []
      let page = 1
      let hasMore = true
      while (hasMore) {
        const result = await productsApi.list({ page, page_size: 100 })
        allProducts.push(...result.items)
        hasMore = page < result.total_pages
        page++
      }
      setProductList(allProducts)

      // Fetch documents for each product
      const allDocs: DocumentRow[] = []
      await Promise.all(
        allProducts.map(async (p) => {
          try {
            const productDocs = await documents.list(p.id)
            productDocs.forEach((doc: ProductDocument) => {
              allDocs.push({
                ...doc,
                product_name: p.name,
                product_sku: p.sku,
              })
            })
          } catch {
            // Skip products where document listing fails
          }
        }),
      )

      // Sort by created_at descending
      allDocs.sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      )
      setDocRows(allDocs)
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail ?? err?.message ?? "Failed to load documents."
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAll()
  }, [fetchAll])

  const handleLinkDocument = (productId: number, productName: string) => {
    setLinkProductId(productId)
    setLinkProductName(productName)
    setLinkFormOpen(true)
  }

  const handleLinkSuccess = () => {
    fetchAll()
  }

  return (
    <div className="space-y-6">
      {/* ── Page Header ──────────────────────────────────────────────── */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight md:text-3xl">
            Documents
          </h1>
          <p className="text-muted-foreground">
            Manage source documents linked to products for content generation.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="icon"
            onClick={fetchAll}
            disabled={loading}
            title="Refresh"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </Button>
          {canLink && productList.length > 0 && (
            <Button
              onClick={() =>
                handleLinkDocument(productList[0].id, productList[0].name)
              }
            >
              <Plus className="h-4 w-4" />
              <span className="hidden sm:inline">Link Document</span>
            </Button>
          )}
        </div>
      </div>

      {/* ── Content ────────────────────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">All Documents</CardTitle>
          <CardDescription>
            {loading
              ? "Loading…"
              : `${docRows.length} document${docRows.length === 1 ? "" : "s"} across ${productList.length} product${productList.length === 1 ? "" : "s"}`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {/* Loading state */}
          {loading && (
            <div className="space-y-3">
              <div className="flex gap-3">
                <Skeleton className="h-10 flex-1" />
                <Skeleton className="h-10 w-[220px]" />
              </div>
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
                Failed to load documents
              </p>
              <p className="text-sm text-muted-foreground mb-4">{error}</p>
              <Button variant="outline" onClick={fetchAll}>
                <RefreshCw className="h-4 w-4 mr-1" /> Retry
              </Button>
            </div>
          )}

          {/* Data */}
          {!loading && !error && (
            <DocumentList
              docs={docRows}
              products={productList}
              loading={loading}
              onRefresh={fetchAll}
              onLinkDocument={handleLinkDocument}
            />
          )}
        </CardContent>
      </Card>

      {/* ── Link Document Dialog ────────────────────────────────────── */}
      {linkProductId !== null && (
        <DocumentLinkForm
          open={linkFormOpen}
          onOpenChange={(open) => {
            if (!open) {
              setLinkProductId(null)
              setLinkProductName("")
            }
            setLinkFormOpen(open)
          }}
          productId={linkProductId}
          productName={linkProductName}
          onSuccess={handleLinkSuccess}
        />
      )}
    </div>
  )
}
