/**
 * EvidencePanel — right split-panel for product evidence/source data.
 *
 * Contains a tabbed interface with:
 *   1. Claims — product claims list with source links, status, inline editing
 *   2. Documents — linked source documents with add/remove
 *   3. Versions — product version timeline with restore
 */

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  ScrollText,
  FileText,
  History,
} from "lucide-react";
import ClaimsTab from "@/components/products/claims-tab";
import DocumentsTab from "@/components/products/documents-tab";
import VersionsTab from "@/components/products/versions-tab";
import type {
  ProductClaimRef,
  ProductDocumentRef,
  ProductVersion,
  DocType,
} from "@/types";

// ── Props ────────────────────────────────────────────────────────────────────

interface EvidencePanelProps {
  claims: ProductClaimRef[];
  documents: ProductDocumentRef[];
  versions: ProductVersion[];
  canEdit: boolean;
  canManageDocs: boolean;
  canRestore: boolean;
  onUpdateClaim: (claimId: number, text: string) => void;
  onAddDocument: (url: string, docType: DocType) => void;
  onRemoveDocument: (documentId: number) => void;
  onRestoreVersion: (versionNumber: number) => void;
  restoringVersionNumber?: number | null;
}

// ── Component ────────────────────────────────────────────────────────────────

export default function EvidencePanel({
  claims,
  documents,
  versions,
  canEdit,
  canManageDocs,
  canRestore,
  onUpdateClaim,
  onAddDocument,
  onRemoveDocument,
  onRestoreVersion,
  restoringVersionNumber,
}: EvidencePanelProps) {
  return (
    <Card className="h-full flex flex-col min-h-0">
      <CardHeader className="pb-2">
        <CardTitle className="text-lg">Evidence & Sources</CardTitle>
      </CardHeader>
      <CardContent className="flex-1 min-h-0 pt-0">
        <Tabs defaultValue="claims" className="flex flex-col h-full">
          <TabsList className="w-full justify-start mb-4">
            <TabsTrigger value="claims" className="gap-1.5">
              <ScrollText className="h-4 w-4" />
              Claims
              {claims.length > 0 && (
                <Badge variant="secondary" className="ml-1 h-5 px-1.5 text-[10px]">
                  {claims.length}
                </Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="documents" className="gap-1.5">
              <FileText className="h-4 w-4" />
              Documents
              {documents.length > 0 && (
                <Badge variant="secondary" className="ml-1 h-5 px-1.5 text-[10px]">
                  {documents.length}
                </Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="versions" className="gap-1.5">
              <History className="h-4 w-4" />
              Versions
              {versions.length > 0 && (
                <Badge variant="secondary" className="ml-1 h-5 px-1.5 text-[10px]">
                  {versions.length}
                </Badge>
              )}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="claims" className="flex-1 min-h-0 mt-0">
            <ClaimsTab
              claims={claims}
              canEdit={canEdit}
              onUpdateClaim={onUpdateClaim}
            />
          </TabsContent>

          <TabsContent value="documents" className="flex-1 min-h-0 mt-0">
            <DocumentsTab
              documents={documents}
              canManage={canManageDocs}
              onAdd={onAddDocument}
              onRemove={onRemoveDocument}
            />
          </TabsContent>

          <TabsContent value="versions" className="flex-1 min-h-0 mt-0">
            <VersionsTab
              versions={versions}
              canRestore={canRestore}
              onRestore={onRestoreVersion}
              restoringVersionNumber={restoringVersionNumber}
            />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
