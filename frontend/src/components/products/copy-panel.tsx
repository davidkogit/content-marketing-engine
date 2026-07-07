/**
 * CopyPanel — left split-panel showing product header, generation controls,
 * and generated content with flags, violations, and source citations.
 */

import { useCallback, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tooltip } from "@/components/ui/tooltip";
import {
  Copy,
  Check,
  AlertTriangle,
  AlertCircle,
  FileText,
  Tag,
  Layers,
  FolderTree,
  Users,
} from "lucide-react";
import GenerationControls from "@/components/products/generation-controls";
import WorkflowActions from "@/components/products/workflow-actions";
import type {
  ProductResponse,
  GeneratedResponse,
  GenerationType,
} from "@/types";
import { WorkflowStage } from "@/types";

// ── Props ────────────────────────────────────────────────────────────────────

interface CopyPanelProps {
  product: ProductResponse;
  generatedResult: GeneratedResponse | null;
  isGenerating: boolean;
  onGenerate: (type: GenerationType) => void;
  canTransition: boolean;
  canApprove: boolean;
  canRequestChanges: boolean;
  onTransition: (toStage: string) => void;
}

// ── Stage badge variants ─────────────────────────────────────────────────────

const stageVariant: Record<string, "default" | "secondary" | "success" | "outline" | "warning"> = {
  [WorkflowStage.INGEST]: "secondary",
  [WorkflowStage.DRAFT]: "outline",
  [WorkflowStage.REVIEW]: "warning",
  [WorkflowStage.APPROVED]: "success",
  [WorkflowStage.EXPORTED]: "default",
};

const stageLabel: Record<string, string> = {
  [WorkflowStage.INGEST]: "Ingest",
  [WorkflowStage.DRAFT]: "Draft",
  [WorkflowStage.REVIEW]: "Review",
  [WorkflowStage.APPROVED]: "Approved",
  [WorkflowStage.EXPORTED]: "Exported",
};

// ── Component ────────────────────────────────────────────────────────────────

export default function CopyPanel({
  product,
  generatedResult,
  isGenerating,
  onGenerate,
  canTransition,
  canApprove,
  canRequestChanges,
  onTransition,
}: CopyPanelProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    if (!generatedResult?.copy) return;
    navigator.clipboard.writeText(generatedResult.copy).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [generatedResult]);

  return (
    <div className="flex flex-col gap-4 h-full">
      {/* ── Product Header Card ─────────────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-2">
            <div className="space-y-1 min-w-0">
              <CardTitle className="text-xl truncate">
                {product.name}
              </CardTitle>
              <div className="flex items-center gap-2 flex-wrap text-sm text-muted-foreground">
                <span className="flex items-center gap-1">
                  <Tag className="h-3.5 w-3.5" />
                  {product.sku}
                </span>
                {product.category && (
                  <span className="flex items-center gap-1">
                    <FolderTree className="h-3.5 w-3.5" />
                    {product.category.name}
                  </span>
                )}
                {product.segment && (
                  <span className="flex items-center gap-1">
                    <Users className="h-3.5 w-3.5" />
                    {product.segment.name}
                  </span>
                )}
              </div>
            </div>
            <Badge variant={stageVariant[product.workflow_stage] ?? "outline"}>
              {stageLabel[product.workflow_stage] ?? product.workflow_stage}
            </Badge>
          </div>
        </CardHeader>

        {product.description && (
          <CardContent className="pt-0">
            <p className="text-sm text-muted-foreground line-clamp-2">
              {product.description}
            </p>
          </CardContent>
        )}
      </Card>

      {/* ── Workflow Actions ────────────────────────────────────────────── */}
      <WorkflowActions
        currentStage={product.workflow_stage}
        canApprove={canApprove}
        canRequestChanges={canRequestChanges}
        canTransition={canTransition}
        onTransition={onTransition}
      />

      {/* ── Generation Controls ─────────────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Content Generation</CardTitle>
        </CardHeader>
        <CardContent>
          <GenerationControls
            isGenerating={isGenerating}
            onGenerate={onGenerate}
          />
        </CardContent>
      </Card>

      {/* ── Generated Copy Display ──────────────────────────────────────── */}
      <Card className="flex-1 flex flex-col min-h-0">
        <CardHeader className="pb-2 flex-row items-center justify-between">
          <CardTitle className="text-base">Generated Copy</CardTitle>
          {generatedResult?.copy && (
            <Tooltip content={copied ? "Copied!" : "Copy to clipboard"}>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleCopy}
                className="gap-1"
              >
                {copied ? (
                  <Check className="h-4 w-4 text-green-500" />
                ) : (
                  <Copy className="h-4 w-4" />
                )}
                {copied ? "Copied" : "Copy"}
              </Button>
            </Tooltip>
          )}
        </CardHeader>
        <CardContent className="flex-1 min-h-0 pt-0">
          <ScrollArea className="h-full max-h-[400px]">
            {!generatedResult ? (
              <div className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-2">
                <FileText className="h-8 w-8 opacity-30" />
                <p className="text-sm">
                  Select a generation type and click Generate to create
                  content.
                </p>
              </div>
            ) : (
              <GeneratedContent result={generatedResult} />
            )}
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}

// ── Generated Content Sub-Component ──────────────────────────────────────────

function GeneratedContent({ result }: { result: GeneratedResponse }) {
  return (
    <div className="space-y-4">
      {/* Flags / warnings */}
      {result.flags.length > 0 && (
        <div className="rounded-md border border-amber-200 bg-amber-50 dark:bg-amber-950/30 p-3">
          <div className="flex items-center gap-2 text-amber-700 dark:text-amber-400 text-sm font-medium mb-1">
            <AlertTriangle className="h-4 w-4" />
            Warnings
          </div>
          <ul className="list-disc list-inside text-xs text-amber-600 dark:text-amber-300 space-y-0.5">
            {result.flags.map((flag, i) => (
              <li key={i}>{flag}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Violations */}
      {result.violations.length > 0 && (
        <div className="rounded-md border border-red-200 bg-red-50 dark:bg-red-950/30 p-3">
          <div className="flex items-center gap-2 text-red-700 dark:text-red-400 text-sm font-medium mb-1">
            <AlertCircle className="h-4 w-4" />
            Rule Violations
          </div>
          <ul className="space-y-2 text-xs">
            {result.violations.map((v, i) => (
              <li key={i}>
                <span className="font-medium text-red-600 dark:text-red-300">
                  {v.rule_type}:
                </span>{" "}
                <span className="text-red-600 dark:text-red-300">
                  {v.description}
                </span>
                <blockquote className="mt-0.5 pl-2 border-l-2 border-red-200 dark:border-red-800 italic text-muted-foreground">
                  &ldquo;{v.rule_text}&rdquo;
                </blockquote>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Main copy */}
      <div className="prose prose-sm dark:prose-invert max-w-none">
        <pre className="whitespace-pre-wrap font-sans text-sm text-foreground bg-muted/30 rounded-lg p-4">
          {result.copy}
        </pre>
      </div>

      {/* Source references */}
      {result.sources.length > 0 && (
        <div className="rounded-md border bg-muted/20 p-3">
          <div className="flex items-center gap-2 text-sm font-medium mb-2">
            <Layers className="h-4 w-4 text-muted-foreground" />
            Source References
          </div>
          <ul className="space-y-1.5">
            {result.sources.map((src) => (
              <li key={src.doc_id} className="text-xs">
                <span className="font-medium">{src.title}</span>
                {src.relevant_excerpt && (
                  <span className="text-muted-foreground">
                    {" "}
                    — &ldquo;{src.relevant_excerpt}&rdquo;
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Generation metadata */}
      {result.metadata && (
        <p className="text-[11px] text-muted-foreground">
          Generated by {result.metadata.model} &middot;{" "}
          {result.metadata.tokens} tokens &middot;{" "}
          {result.metadata.latency.toFixed(1)}s
        </p>
      )}
    </div>
  );
}
