/**
 * WorkflowActionsBar — displays transition buttons based on current
 * workflow stage and user role.
 *
 * Stages: ingest → draft → review → approved → exported
 * Each stage has valid forward/backward transitions with role gates.
 */

import { Button, type ButtonProps } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import {
  ArrowRight,
  CheckCircle,
  RotateCcw,
  FileDown,
} from "lucide-react";
import { WorkflowStage } from "@/types";

// ── Props ────────────────────────────────────────────────────────────────────

interface WorkflowActionsProps {
  currentStage: string;
  /** Whether the current user can approve content (admin/super_admin). */
  canApprove: boolean;
  /** Whether the current user can request changes (admin/super_admin). */
  canRequestChanges: boolean;
  /** Whether the user can move product forward (editor+). */
  canTransition: boolean;
  /** Called when a transition action is triggered. */
  onTransition: (toStage: string, comment?: string) => void;
  /** Whether a transition is currently in progress. */
  isTransitioning?: boolean;
}

type TransitionDef = {
  to: string;
  label: string;
  icon: React.ReactNode;
  variant?: NonNullable<ButtonProps["variant"]>;
  requiresApprovalGate?: boolean;
};

const transitions: Record<string, TransitionDef[]> = {
  ingest: [
    {
      to: WorkflowStage.DRAFT,
      label: "Move to Draft",
      icon: <ArrowRight className="h-4 w-4" />,
    },
  ],
  draft: [
    {
      to: WorkflowStage.REVIEW,
      label: "Submit for Review",
      icon: <ArrowRight className="h-4 w-4" />,
      variant: "default",
    },
  ],
  review: [
    {
      to: WorkflowStage.APPROVED,
      label: "Approve",
      icon: <CheckCircle className="h-4 w-4" />,
      variant: "default",
      requiresApprovalGate: true,
    },
    {
      to: WorkflowStage.DRAFT,
      label: "Request Changes",
      icon: <RotateCcw className="h-4 w-4" />,
      variant: "secondary",
      requiresApprovalGate: true,
    },
  ],
  approved: [
    {
      to: WorkflowStage.EXPORTED,
      label: "Mark as Exported",
      icon: <FileDown className="h-4 w-4" />,
    },
  ],
  exported: [],
};

// ── Component ────────────────────────────────────────────────────────────────

export default function WorkflowActions({
  currentStage,
  canApprove,
  canRequestChanges,
  canTransition,
  onTransition,
  isTransitioning = false,
}: WorkflowActionsProps) {
  const stageTransitions: TransitionDef[] = transitions[currentStage] ?? [];

  if (stageTransitions.length === 0) return null;

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="text-xs text-muted-foreground font-medium">
        Actions:
      </span>
      {stageTransitions.map((t) => {
        // Gate checks
        let disabled = isTransitioning || !canTransition;
        let tooltipText = "";

        if (t.requiresApprovalGate) {
          const isApprovalMove = t.to === WorkflowStage.APPROVED;
          if (isApprovalMove && !canApprove) {
            disabled = true;
            tooltipText = "Admin or Super Admin approval required";
          } else if (!isApprovalMove && !canRequestChanges) {
            disabled = true;
            tooltipText = "Admin or Super Admin required to request changes";
          }
        }

        const button = (
          <Button
            key={t.to}
            variant={t.variant ?? "outline"}
            size="sm"
            onClick={() => onTransition(t.to)}
            disabled={disabled}
            className="gap-1"
          >
            {t.icon}
            {t.label}
          </Button>
        );

        if (tooltipText) {
          return (
            <Tooltip key={t.to} content={tooltipText}>
              {button}
            </Tooltip>
          );
        }

        return button;
      })}
    </div>
  );
}

export type { WorkflowActionsProps };
