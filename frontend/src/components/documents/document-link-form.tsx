import { useState } from "react"
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
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { documents } from "@/lib/api-endpoints"
import { useToast } from "@/hooks/use-toast"
import { DocType } from "@/types/product"
import type { ProductDocument } from "@/types"

interface DocumentLinkFormProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  productId: number
  productName: string
  onSuccess: (doc: ProductDocument) => void
}

export function DocumentLinkForm({
  open,
  onOpenChange,
  productId,
  productName,
  onSuccess,
}: DocumentLinkFormProps) {
  const { toast } = useToast()
  const [url, setUrl] = useState("")
  const [docType, setDocType] = useState<string>(DocType.URL)
  const [submitting, setSubmitting] = useState(false)
  const [urlError, setUrlError] = useState("")

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      setUrl("")
      setDocType(DocType.URL)
      setUrlError("")
    }
    onOpenChange(open)
  }

  const validate = (): boolean => {
    const trimmed = url.trim()
    if (!trimmed) {
      setUrlError("URL is required.")
      return false
    }
    try {
      new URL(trimmed)
    } catch {
      setUrlError("Please enter a valid URL (e.g., https://example.com/doc.pdf).")
      return false
    }
    setUrlError("")
    return true
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!validate()) return

    setSubmitting(true)
    try {
      const created = await documents.create(productId, {
        url: url.trim(),
        doc_type: docType as DocType,
      })
      toast({ title: "Document linked", variant: "success" })
      onSuccess(created)
      handleOpenChange(false)
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail ?? err?.message ?? "Failed to link document."
      toast({ title: "Error", description: msg, variant: "destructive" })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Link Document</DialogTitle>
          <DialogDescription>
            Add a source document to <strong>{productName}</strong>. The title
            will be fetched automatically.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="doc-type">Document Type</Label>
            <Select
              value={docType}
              onValueChange={setDocType}
              disabled={submitting}
            >
              <SelectTrigger id="doc-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={DocType.URL}>URL (web page)</SelectItem>
                <SelectItem value={DocType.PDF}>PDF (direct link)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="doc-url">URL *</Label>
            <Input
              id="doc-url"
              value={url}
              onChange={(e) => {
                setUrl(e.target.value)
                if (urlError) setUrlError("")
              }}
              placeholder="https://example.com/product-spec.pdf"
              disabled={submitting}
              aria-invalid={!!urlError}
            />
            {urlError && (
              <p className="text-sm text-destructive">{urlError}</p>
            )}
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Linking…" : "Link Document"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
