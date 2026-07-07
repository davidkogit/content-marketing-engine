/**
 * DashboardPage — main Kanban board view with loading, error, and role-aware logic.
 *
 * Layout:
 *   - Loading state: skeleton columns with placeholder cards
 *   - Error state: centered error message with retry button
 *   - Success state: full Kanban board with 5 workflow columns
 *
 * The board fetches data via GET /workflow/board and handles stage
 * transitions via POST /workflow/products/{id}/transition.
 *
 * Role-aware: viewers and editors see a read-only board (drag disabled).
 * Admin and super_admin can drag cards between columns.
 */

import { useAuth } from "@/hooks/use-auth";
import { useKanban } from "@/hooks/use-kanban";
import { KanbanBoard } from "@/components/kanban/kanban-board";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle, RefreshCw } from "lucide-react";

// ── Loading Skeleton ──────────────────────────────────────────────────────

function BoardSkeleton() {
  return (
    <div className="flex gap-4 overflow-x-auto pb-4 flex-1">
      {Array.from({ length: 5 }).map((_, i) => (
        <div
          key={i}
          className="flex w-[300px] min-w-[300px] shrink-0 flex-col rounded-lg border bg-card"
        >
          <div className="flex items-center justify-between border-l-4 px-3 py-2.5">
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-4 w-6 rounded-full" />
          </div>
          <div className="flex-1 p-2 space-y-2">
            {Array.from({ length: 3 }).map((_, j) => (
              <Skeleton
                key={j}
                className="h-[88px] w-full rounded-lg"
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Error State ────────────────────────────────────────────────────────────

function BoardError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="flex flex-1 items-center justify-center">
      <div className="flex flex-col items-center gap-4 text-center max-w-sm">
        <div className="rounded-full bg-destructive/10 p-4">
          <AlertCircle className="h-8 w-8 text-destructive" />
        </div>
        <div>
          <h2 className="text-lg font-semibold">Failed to load board</h2>
          <p className="mt-1 text-sm text-muted-foreground">{message}</p>
        </div>
        <Button variant="outline" onClick={onRetry}>
          <RefreshCw className="h-4 w-4" />
          Retry
        </Button>
      </div>
    </div>
  );
}

// ── Dashboard Page ─────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { hasRole } = useAuth();
  const { columns, isLoading, error, fetchBoard, moveProductLocally, transitionProduct } =
    useKanban();

  // Viewer and editor cannot drag cards (read-only board).
  // Admin and super_admin can move cards.
  const isReadOnly = !hasRole("admin");

  // ── Error State ──────────────────────────────────────────────────────

  if (error) {
    return (
      <div className="flex h-full flex-col">
        <div className="mb-4">
          <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Kanban board and content overview.
          </p>
        </div>
        <BoardError message={error} onRetry={fetchBoard} />
      </div>
    );
  }

  // ── Loading State ────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex h-full flex-col">
        <div className="mb-4">
          <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Kanban board and content overview.
          </p>
        </div>
        <BoardSkeleton />
      </div>
    );
  }

  // ── Success State ────────────────────────────────────────────────────

  return (
    <div className="flex h-full flex-col">
      <div className="mb-4">
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Drag cards between columns to update workflow stages.
        </p>
      </div>
      <KanbanBoard
        columns={columns}
        isLoading={isLoading}
        isReadOnly={isReadOnly}
        moveProductLocally={moveProductLocally}
        transitionProduct={transitionProduct}
      />
    </div>
  );
}
