/**
 * ClaimsTab — displays a list of product claims with source citations,
 * status badges, and inline editing for editor+ users.
 */

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Tooltip } from "@/components/ui/tooltip";
import {
  Pencil,
  Check,
  X,
  ExternalLink,
  FileText,
} from "lucide-react";
import type { ProductClaimRef } from "@/types";
import { ClaimStatus } from "@/types";

// ── Props ────────────────────────────────────────────────────────────────────

interface ClaimsTabProps {
  claims: ProductClaimRef[];
  /** Whether the current user can edit claims (editor+). */
  canEdit: boolean;
  /** Called when a claim text is saved after inline editing. */
  onUpdateClaim: (claimId: number, text: string) => void;
}

// ── Status badge helpers ─────────────────────────────────────────────────────

const statusVariant: Record<
  string,
  "default" | "secondary" | "destructive" | "outline" | "success" | "warning"
> = {
  [ClaimStatus.VERIFIED]: "success",
  [ClaimStatus.FLAGGED]: "warning",
  [ClaimStatus.REJECTED]: "destructive",
  [ClaimStatus.PENDING_REVIEW]: "secondary",
};

const statusLabel: Record<string, string> = {
  [ClaimStatus.VERIFIED]: "Verified",
  [ClaimStatus.FLAGGED]: "Flagged",
  [ClaimStatus.REJECTED]: "Rejected",
  [ClaimStatus.PENDING_REVIEW]: "Pending Review",
};

// ── Component ────────────────────────────────────────────────────────────────

export default function ClaimsTab({
  claims,
  canEdit,
  onUpdateClaim,
}: ClaimsTabProps) {
  return (
    <ScrollArea className="max-h-[60vh] pr-2">
      {claims.length === 0 ? (
        <p className="text-sm text-muted-foreground py-8 text-center">
          No claims yet. Generate content to populate claims with source
          citations.
        </p>
      ) : (
        <ul className="space-y-3">
          {claims.map((claim, idx) => (
            <li key={claim.id}>
              <ClaimItem
                claim={claim}
                canEdit={canEdit}
                onUpdate={onUpdateClaim}
              />
              {idx < claims.length - 1 && <Separator className="mt-3" />}
            </li>
          ))}
        </ul>
      )}
    </ScrollArea>
  );
}

// ── Claim Item ───────────────────────────────────────────────────────────────

function ClaimItem({
  claim,
  canEdit,
  onUpdate,
}: {
  claim: ProductClaimRef;
  canEdit: boolean;
  onUpdate: (claimId: number, text: string) => void;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [editText, setEditText] = useState(claim.claim_text);

  const handleSave = () => {
    onUpdate(claim.id, editText.trim());
    setIsEditing(false);
  };

  const handleCancel = () => {
    setEditText(claim.claim_text);
    setIsEditing(false);
  };

  const hasSource = claim.source_doc_id !== null;

  return (
    <div className="flex flex-col gap-2">
      {/* Status + source badges row */}
      <div className="flex items-center gap-2 flex-wrap">
        <Badge variant={statusVariant[claim.status] ?? "secondary"}>
          {statusLabel[claim.status] ?? claim.status}
        </Badge>
        {hasSource && (
          <Tooltip content="This claim is linked to a source document">
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <FileText className="h-3 w-3" />
              Source linked
            </span>
          </Tooltip>
        )}
      </div>

      {/* Claim text (inline editable) */}
      {isEditing ? (
        <div className="space-y-2">
          <Textarea
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            rows={3}
            className="text-sm"
            autoFocus
          />
          <div className="flex gap-2">
            <Button size="sm" onClick={handleSave} className="gap-1">
              <Check className="h-3 w-3" />
              Save
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={handleCancel}
              className="gap-1"
            >
              <X className="h-3 w-3" />
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm text-foreground">{claim.claim_text}</p>
          {canEdit && (
            <Tooltip content="Edit claim text">
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 shrink-0"
                onClick={() => {
                  setEditText(claim.claim_text);
                  setIsEditing(true);
                }}
              >
                <Pencil className="h-3.5 w-3.5" />
              </Button>
            </Tooltip>
          )}
        </div>
      )}

      {/* Source citation link */}
      {hasSource && (
        <a
          href="#"
          className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
          onClick={(e) => e.preventDefault()}
        >
          <ExternalLink className="h-3 w-3" />
          View source document
        </a>
      )}
    </div>
  );
}
