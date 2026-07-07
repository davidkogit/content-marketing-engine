import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Simple Tooltip — a hover-activated popover for contextual help.
 *
 * Renders a trigger element and shows a floating tooltip on hover.
 * Uses native CSS for positioning; no Radix dependency.
 */

interface TooltipProps {
  content: React.ReactNode;
  children: React.ReactNode;
  side?: "top" | "bottom" | "left" | "right";
  className?: string;
}

const sideStyles: Record<string, string> = {
  top: "bottom-full left-1/2 -translate-x-1/2 mb-2",
  bottom: "top-full left-1/2 -translate-x-1/2 mt-2",
  left: "right-full top-1/2 -translate-y-1/2 mr-2",
  right: "left-full top-1/2 -translate-y-1/2 ml-2",
};

function Tooltip({
  content,
  children,
  side = "top",
  className,
}: TooltipProps) {
  return (
    <span className={cn("relative inline-flex group", className)}>
      <span className="inline-flex">{children}</span>
      <span
        role="tooltip"
        className={cn(
          "pointer-events-none absolute z-50 opacity-0 group-hover:opacity-100",
          "transition-opacity duration-150",
          "rounded-md bg-popover text-popover-foreground px-2 py-1",
          "text-xs shadow-md border whitespace-nowrap",
          sideStyles[side],
        )}
      >
        {content}
      </span>
    </span>
  );
}

export { Tooltip };
export type { TooltipProps };
