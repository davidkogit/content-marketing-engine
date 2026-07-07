/**
 * DocumentsTab — lists linked source documents with add/remove controls.
 *
 * Allows adding documents by URL, showing their title, type, and a link.
 * Supports removal with confirmation.
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tooltip } from "@/components/ui/tooltip";
import {
  Plus,
  Trash2,
  ExternalLink,
  FileText,
  Globe,
} from "lucide-react";
import type { ProductDocumentRef, DocType } from "@/types";
import { DocType as DocTypeEnum } from "@/types";

// ── Props ────────────────────────────────────────────────────────────────────

interface DocumentsTabProps {
  documents: ProductDocumentRef[];
  /** Whether the current user can manage documents. */
  canManage: boolean;
  /** Called when a new document is submitted. */
  onAdd: (url: string, docType: DocType) => void;
  /** Called when a document is removed. */
  onRemove: (documentId: number) => void;
  isAdding?: boolean;
}

const docTypeIcon: Record<string, React.ReactNode> = {
  pdf: <FileText className="h-4 w-4 text-red-500" />,
  url: <Globe className="h-4 w-4 text-blue-500" />,
};

// ── Component ────────────────────────────────────────────────────────────────

export default function DocumentsTab({
  documents,
  canManage,
  onAdd,
  onRemove,
  isAdding = false,
}: DocumentsTabProps) {
  const [url, setUrl] = useState("");
  const [docType, setDocType] = useState<DocType>(DocTypeEnum.URL);
  const [isFormOpen, setIsFormOpen] = useState(false);

  const handleSubmit = () => {
    if (!url.trim()) return;
    onAdd(url.trim(), docType);
    setUrl("");
    setIsFormOpen(false);
  };

  return (
    <div className="space-y-4">
      {/* Add document button */}
      {canManage && (
        <div className="flex justify-end">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setIsFormOpen(!isFormOpen)}
            className="gap-1"
          >
            <Plus className="h-4 w-4" />
            Add Document
          </Button>
        </div>
      )}

      {/* Add document form */}
      {isFormOpen && (
        <div className="rounded-lg border bg-muted/30 p-4 space-y-3">
          <div className="flex gap-3">
            <Input
              placeholder="Document URL (https://...)"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="flex-1"
              disabled={isAdding}
            />
            <Select
              value={docType}
              onValueChange={(value) => setDocType(value as DocType)}
              disabled={isAdding}
            >
              <SelectTrigger className="w-[110px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={DocTypeEnum.URL}>URL</SelectItem>
                <SelectItem value={DocTypeEnum.PDF}>PDF</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={handleSubmit}
              disabled={!url.trim() || isAdding}
            >
              {isAdding ? "Adding…" : "Add"}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setIsFormOpen(false)}
              disabled={isAdding}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}

      <Separator />

      {/* Document list */}
      <ScrollArea className="max-h-[50vh] pr-2">
        {documents.length === 0 ? (
          <p className="text-sm text-muted-foreground py-8 text-center">
            No linked documents. Add source documents to provide evidence for
            generated content.
          </p>
        ) : (
          <ul className="space-y-2">
            {documents.map((doc) => (
              <li
                key={doc.id}
                className="flex items-center justify-between gap-2 rounded-lg border bg-card p-3"
              >
                <div className="flex items-center gap-3 min-w-0">
                  {docTypeIcon[doc.doc_type] ?? (
                    <Globe className="h-4 w-4 shrink-0" />
                  )}
                  <div className="min-w-0">
                    <Tooltip content={doc.url}>
                      <a
                        href={doc.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-sm font-medium text-foreground hover:text-primary truncate max-w-[300px]"
                      >
                        {doc.title}
                        <ExternalLink className="h-3 w-3 shrink-0" />
                      </a>
                    </Tooltip>
                    <p className="text-xs text-muted-foreground truncate max-w-[300px]">
                      {doc.url}
                    </p>
                  </div>
                  <Badge variant="outline" className="text-[10px] shrink-0">
                    {doc.doc_type.toUpperCase()}
                  </Badge>
                </div>

                {canManage && (
                  <Tooltip content="Remove document">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 shrink-0 text-destructive hover:text-destructive"
                      onClick={() => onRemove(doc.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </Tooltip>
                )}
              </li>
            ))}
          </ul>
        )}
      </ScrollArea>
    </div>
  );
}
