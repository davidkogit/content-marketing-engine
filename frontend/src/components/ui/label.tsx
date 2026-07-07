/**
 * Label — accessible form label component.
 *
 * Uses the `peer` pattern: when an associated input is disabled, the
 * label inherits the muted + cursor-not-allowed styling via Tailwind's
 * `peer-disabled:` variant.
 */

import * as React from "react";
import { cn } from "@/lib/utils";

const Label = React.forwardRef<
  HTMLLabelElement,
  React.LabelHTMLAttributes<HTMLLabelElement>
>(({ className, ...props }, ref) => (
  <label
    ref={ref}
    className={cn(
      "text-sm font-medium leading-none",
      "peer-disabled:cursor-not-allowed peer-disabled:opacity-70",
      className,
    )}
    {...props}
  />
));
Label.displayName = "Label";

export { Label };
