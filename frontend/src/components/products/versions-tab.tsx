/**
 * VersionsTab — displays a timeline of product versions with restore capability.
 *
 * Each version shows its number, creation date, change summary, and a
 * restore button to revert the product to that snapshot.
 */

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tooltip } from "@/components/ui/tooltip";
import {
  RotateCcw,
  Clock,
  GitCommit,
} from "lucide-react";
import type { ProductVersion } from "@/types";

// ── Props ────────────────────────────────────────────────────────────────────

interface VersionsTabProps {
  versions: ProductVersion[];
  /** Whether the current user can restore versions. */
  canRestore: boolean;
  /** Called when a version is selected for restore. */
  onRestore: (versionNumber: number) => void;
  /** The current version number being restored (for loading state). */
  restoringVersionNumber?: number | null;
}

/** Format an ISO date string to a readable local datetime. */
function formatDate(iso: string): string {
  try {
    const date = new Date(iso);
    return date.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

// ── Component ────────────────────────────────────────────────────────────────

export default function VersionsTab({
  versions,
  canRestore,
  onRestore,
  restoringVersionNumber,
}: VersionsTabProps) {
  const sorted = [...versions].sort(
    (a, b) => b.version_number - a.version_number,
  );

  return (
    <ScrollArea className="max-h-[60vh] pr-2">
      {sorted.length === 0 ? (
        <p className="text-sm text-muted-foreground py-8 text-center">
          No versions yet. Versions are created when the product moves through
          workflow stages.
        </p>
      ) : (
        <div className="relative pl-6">
          {/* Timeline vertical line */}
          <div className="absolute left-[7px] top-2 bottom-2 w-px bg-border" />

          <ul className="space-y-4">
            {sorted.map((version, idx) => (
              <li key={version.id} className="relative">
                {/* Timeline dot */}
                <span className="absolute -left-[22px] top-1.5 flex h-4 w-4 items-center justify-center rounded-full border-2 border-primary bg-background">
                  <span className="h-1.5 w-1.5 rounded-full bg-primary" />
                </span>

                <div className="rounded-lg border bg-card p-3">
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <div className="flex items-center gap-2">
                      <GitCommit className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="text-sm font-semibold">
                        v{version.version_number}
                      </span>
                      {idx === 0 && (
                        <Badge
                          variant="secondary"
                          className="text-[10px]"
                        >
                          Latest
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Clock className="h-3 w-3" />
                        {formatDate(version.created_at)}
                      </span>
                      {canRestore && (
                        <Tooltip content="Restore this version">
                          <Button
                            variant="outline"
                            size="icon"
                            className="h-7 w-7"
                            onClick={() => onRestore(version.version_number)}
                            disabled={
                              restoringVersionNumber ===
                              version.version_number
                            }
                          >
                            <RotateCcw className="h-3.5 w-3.5" />
                          </Button>
                        </Tooltip>
                      )}
                    </div>
                  </div>

                  {version.change_summary && (
                    <p className="text-xs text-muted-foreground mt-1">
                      {version.change_summary}
                    </p>
                  )}
                </div>

                {idx < sorted.length - 1 && (
                  <Separator className="mt-4" />
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </ScrollArea>
  );
}
