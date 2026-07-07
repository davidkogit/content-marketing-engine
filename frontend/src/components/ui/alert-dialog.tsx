import * as React from "react"
import { cn } from "@/lib/utils"
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { buttonVariants } from "@/components/ui/button"

// ── AlertDialog — confirm / destructive action wrapper over Dialog ────────────

const AlertDialog = Dialog
const AlertDialogTrigger = DialogTrigger

interface AlertDialogContentProps
  extends React.ComponentPropsWithoutRef<typeof DialogContent> {}

const AlertDialogContent = React.forwardRef<
  React.ElementRef<typeof DialogContent>,
  AlertDialogContentProps
>(({ className, ...props }, ref) => (
  <DialogContent ref={ref} className={cn("max-w-md", className)} {...props} />
))
AlertDialogContent.displayName = "AlertDialogContent"

const AlertDialogHeader = DialogHeader
const AlertDialogFooter = DialogFooter
const AlertDialogTitle = DialogTitle
const AlertDialogDescription = DialogDescription

// ── Actions ───────────────────────────────────────────────────────────────────

interface AlertDialogActionProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  destructive?: boolean
}

function AlertDialogAction({
  className,
  destructive,
  children,
  ...props
}: AlertDialogActionProps) {
  return (
    <button
      className={cn(
        buttonVariants({
          variant: destructive ? "destructive" : "default",
        }),
        className,
      )}
      {...props}
    >
      {children}
    </button>
  )
}

// ── Cancel ────────────────────────────────────────────────────────────────────

function AlertDialogCancel({
  className,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={cn(buttonVariants({ variant: "outline" }), className)}
      {...props}
    >
      {children ?? "Cancel"}
    </button>
  )
}

export {
  AlertDialog,
  AlertDialogTrigger,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogAction,
  AlertDialogCancel,
}
