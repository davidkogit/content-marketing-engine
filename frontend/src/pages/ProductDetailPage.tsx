/**
 * ProductDetailPage — split-panel product detail view.
 *
 * Left panel: product header, workflow actions, generation controls,
 *             and generated copy display
 * Right panel: evidence tabs (claims, documents, versions) with
 *              source citations, document management, and version history
 *
 * Responsive: panels stack vertically on tablet/mobile (<1024px),
 *             side-by-side on desktop (>= 1024px).
 */

import { useCallback } from "react";
import { useParams } from "react-router-dom";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertTriangle } from "lucide-react";
import { useProductDetail } from "@/hooks/use-product-detail";
import { useAuth } from "@/hooks/use-auth";
import CopyPanel from "@/components/products/copy-panel";
import EvidencePanel from "@/components/products/evidence-panel";
import { workflow } from "@/lib/api-endpoints";
import { useToast } from "@/hooks/use-toast";
import type { GenerationType, DocType } from "@/types";
import { UserRole, WorkflowStage } from "@/types";

// ── Inline Alert (standalone, no radix dependency) ─────────────────────────
function InlineAlert({
  variant = "default",
  children,
}: {
  variant?: "default" | "destructive";
  children: React.ReactNode;
}) {
  return (
    <div
      className={`rounded-lg border p-4 ${
        variant === "destructive"
          ? "border-destructive/50 bg-destructive/10 text-destructive"
          : "border-border bg-muted/30 text-foreground"
      }`}
    >
      {children}
    </div>
  );
}

// ── Loading Skeleton ─────────────────────────────────────────────────────────

function ProductDetailSkeleton() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 p-6">
      <div className="space-y-4">
        <Skeleton className="h-32 w-full rounded-lg" />
        <Skeleton className="h-48 w-full rounded-lg" />
        <Skeleton className="h-24 w-full rounded-lg" />
      </div>
      <div className="space-y-4">
        <Skeleton className="h-[500px] w-full rounded-lg" />
      </div>
    </div>
  );
}

// ── Page Component ───────────────────────────────────────────────────────────

export default function ProductDetailPage() {
  const { id } = useParams<{ id: string }>();
  const productId = id ? Number(id) : null;
  const { user } = useAuth();
  const { toast } = useToast();

  const {
    product,
    generatedResult,
    isLoading,
    isGenerating,
    error,
    generate,
    addDocument,
    removeDocument,
    updateClaim,
    restoreVersion,
    refresh,
  } = useProductDetail(productId);

  // ── Role checks ────────────────────────────────────────────────────────

  const userRole = user?.role ?? UserRole.VIEWER;
  const isSuperAdmin = userRole === UserRole.SUPER_ADMIN;
  const isAdmin = userRole === UserRole.ADMIN;
  const isEditor = userRole === UserRole.EDITOR;
  const canApprove = isSuperAdmin || isAdmin;
  const canEdit = canApprove || isEditor;
  const canManageDocs = canEdit;
  const canRestore = canEdit;
  const canTransition = canEdit;

  // ── Handlers ────────────────────────────────────────────────────────────

  const handleGenerate = useCallback(
    async (genType: GenerationType) => {
      try {
        await generate(genType);
      } catch {
        // Error state already managed by the hook; suppress re-throw.
      }
    },
    [generate],
  );

  const handleTransition = useCallback(
    async (toStage: string) => {
      if (!product) return;
      try {
        await workflow.transition(product.id, {
          to_stage: toStage as WorkflowStage,
          comment: `Moved to ${toStage}`,
        });
        // Re-fetch product data to reflect the new workflow stage.
        await refresh();
      } catch (err: unknown) {
        toast({
          title: "Transition failed",
          description:
            err instanceof Error ? err.message : "Unknown error",
          variant: "destructive",
        });
      }
    },
    [product, toast, refresh],
  );

  const handleUpdateClaim = useCallback(
    (claimId: number, text: string) => {
      updateClaim(claimId, { claim_text: text }).catch((err: unknown) => {
        toast({
          title: "Failed to update claim",
          description:
            err instanceof Error ? err.message : "Unknown error",
          variant: "destructive",
        });
      });
    },
    [updateClaim, toast],
  );

  const handleAddDocument = useCallback(
    (url: string, docType: DocType) => {
      addDocument({ url, doc_type: docType }).catch((err: unknown) => {
        toast({
          title: "Failed to add document",
          description:
            err instanceof Error ? err.message : "Unknown error",
          variant: "destructive",
        });
      });
    },
    [addDocument, toast],
  );

  const handleRemoveDocument = useCallback(
    (documentId: number) => {
      removeDocument(documentId).catch((err: unknown) => {
        toast({
          title: "Failed to remove document",
          description:
            err instanceof Error ? err.message : "Unknown error",
          variant: "destructive",
        });
      });
    },
    [removeDocument, toast],
  );

  const handleRestoreVersion = useCallback(
    (versionNumber: number) => {
      restoreVersion(versionNumber).catch((err: unknown) => {
        toast({
          title: "Failed to restore version",
          description:
            err instanceof Error ? err.message : "Unknown error",
          variant: "destructive",
        });
      });
    },
    [restoreVersion, toast],
  );

  // ── Loading state ───────────────────────────────────────────────────────

  if (isLoading) {
    return <ProductDetailSkeleton />;
  }

  // ── Error state ─────────────────────────────────────────────────────────

  if (error) {
    return (
      <div className="container mx-auto p-8">
        <InlineAlert variant="destructive">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5" />
            <span className="font-medium">Error loading product</span>
          </div>
          <p className="mt-1 text-sm">{error}</p>
        </InlineAlert>
      </div>
    );
  }

  // ── Empty state ─────────────────────────────────────────────────────────

  if (!product) {
    return (
      <div className="container mx-auto p-8">
        <InlineAlert>
          <p className="text-muted-foreground">Product not found.</p>
        </InlineAlert>
      </div>
    );
  }

  // ── Main content ────────────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full">
      {/* Page header */}
      <div className="flex items-center justify-between px-6 py-4 border-b bg-background">
        <div>
          <h1 className="text-xl font-bold">Product Detail</h1>
          <p className="text-sm text-muted-foreground">
            {product.name} — Edit content, review evidence, and manage
            workflow.
          </p>
        </div>
      </div>

      <Separator />

      {/* Split-panel content */}
      <div className="flex-1 min-h-0 overflow-auto p-4 lg:p-6">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 h-full">
          {/* Left: Copy Panel */}
          <div className="min-h-0">
            <CopyPanel
              product={product}
              generatedResult={generatedResult}
              isGenerating={isGenerating}
              onGenerate={handleGenerate}
              canTransition={canTransition}
              canApprove={canApprove}
              canRequestChanges={canApprove}
              onTransition={handleTransition}
            />
          </div>

          {/* Right: Evidence Panel */}
          <div className="min-h-0">
            <EvidencePanel
              claims={product.claims ?? []}
              documents={product.documents ?? []}
              versions={product.versions ?? []}
              canEdit={canEdit}
              canManageDocs={canManageDocs}
              canRestore={canRestore}
              onUpdateClaim={handleUpdateClaim}
              onAddDocument={handleAddDocument}
              onRemoveDocument={handleRemoveDocument}
              onRestoreVersion={handleRestoreVersion}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
