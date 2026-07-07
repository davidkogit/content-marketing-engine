import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Simple ScrollArea — a scrollable container with styled scrollbars.
 *
 * Wraps content in a fixed-height container with overflow scrolling
 * and custom scrollbar styling via Tailwind CSS.
 */

interface ScrollAreaProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Max height for the scrollable area (Tailwind h-* classes or custom). */
  className?: string;
  children: React.ReactNode;
}

const ScrollArea = React.forwardRef<HTMLDivElement, ScrollAreaProps>(
  ({ className, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          "overflow-y-auto overflow-x-hidden",
          "scrollbar-thin scrollbar-thumb-muted-foreground/20 scrollbar-track-transparent",
          className,
        )}
        {...props}
      >
        {children}
      </div>
    );
  },
);
ScrollArea.displayName = "ScrollArea";

export { ScrollArea };
export type { ScrollAreaProps };
