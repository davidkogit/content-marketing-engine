import * as React from "react"
import { cn } from "@/lib/utils"
import { ChevronDown } from "lucide-react"

// ── Types ─────────────────────────────────────────────────────────────────────

/** Root accordion context — holds the currently expanded value. */
interface AccordionContextValue {
  value: string | null
  onValueChange: (value: string) => void
}

const AccordionContext = React.createContext<AccordionContextValue | null>(null)

function useAccordionContext() {
  const ctx = React.useContext(AccordionContext)
  if (!ctx) {
    throw new Error("AccordionTrigger/Content must be used within an Accordion")
  }
  return ctx
}

/** Per-item context — holds this item's unique value string. */
interface AccordionItemContextValue {
  itemValue: string
}

const AccordionItemContext =
  React.createContext<AccordionItemContextValue | null>(null)

function useAccordionItemContext() {
  const ctx = React.useContext(AccordionItemContext)
  if (!ctx) {
    throw new Error(
      "AccordionTrigger/Content must be used within an AccordionItem",
    )
  }
  return ctx
}

// ── Root ──────────────────────────────────────────────────────────────────────

interface AccordionProps {
  type: "single" | "multiple"
  value?: string | string[]
  defaultValue?: string | string[]
  onValueChange?: (value: string) => void
  collapsible?: boolean
  className?: string
  children: React.ReactNode
}

function Accordion({
  onValueChange,
  defaultValue,
  collapsible = true,
  className,
  children,
}: AccordionProps) {
  const [internalValue, setInternalValue] = React.useState<string | null>(
    () => {
      if (defaultValue !== undefined) {
        return typeof defaultValue === "string" ? defaultValue : defaultValue[0] ?? null
      }
      return null
    },
  )

  const handleValueChange = React.useCallback(
    (itemValue: string) => {
      const next = internalValue === itemValue && collapsible ? null : itemValue
      setInternalValue(next)
      if (onValueChange && next) {
        onValueChange(next)
      }
    },
    [internalValue, collapsible, onValueChange],
  )

  const ctxValue = React.useMemo<AccordionContextValue>(
    () => ({ value: internalValue, onValueChange: handleValueChange }),
    [internalValue, handleValueChange],
  )

  return (
    <AccordionContext.Provider value={ctxValue}>
      <div className={cn("space-y-0.5", className)}>{children}</div>
    </AccordionContext.Provider>
  )
}

// ── Item ──────────────────────────────────────────────────────────────────────

interface AccordionItemProps extends React.HTMLAttributes<HTMLDivElement> {
  value: string
}

function AccordionItem({
  value,
  className,
  children,
  ...props
}: AccordionItemProps) {
  const ctxValue = React.useMemo<AccordionItemContextValue>(
    () => ({ itemValue: value }),
    [value],
  )

  return (
    <AccordionItemContext.Provider value={ctxValue}>
      <div
        className={cn("rounded-lg border bg-card", className)}
        {...props}
      >
        {children}
      </div>
    </AccordionItemContext.Provider>
  )
}

// ── Trigger ───────────────────────────────────────────────────────────────────

interface AccordionTriggerProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  children: React.ReactNode
}

function AccordionTrigger({
  className,
  children,
  ...props
}: AccordionTriggerProps) {
  const { value, onValueChange } = useAccordionContext()
  const { itemValue } = useAccordionItemContext()

  const isOpen = value === itemValue

  return (
    <button
      type="button"
      onClick={() => onValueChange(itemValue)}
      className={cn(
        "flex w-full items-center justify-between px-4 py-3 text-sm font-medium transition-colors hover:bg-muted/50 [&[data-state=open]>svg]:rotate-180",
        className,
      )}
      data-state={isOpen ? "open" : "closed"}
      aria-expanded={isOpen}
      {...props}
    >
      {children}
      <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200" />
    </button>
  )
}

// ── Content ───────────────────────────────────────────────────────────────────

interface AccordionContentProps
  extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode
}

function AccordionContent({
  className,
  children,
  ...props
}: AccordionContentProps) {
  const { value } = useAccordionContext()
  const { itemValue } = useAccordionItemContext()
  const contentRef = React.useRef<HTMLDivElement>(null)
  const [height, setHeight] = React.useState(0)

  const isOpen = value === itemValue

  React.useEffect(() => {
    if (contentRef.current) {
      const inner = contentRef.current.firstElementChild as HTMLElement | null
      setHeight(inner?.scrollHeight ?? 0)
    }
  }, [children, isOpen])

  return (
    <div
      ref={contentRef}
      className={cn(
        "overflow-hidden transition-[height] duration-200 ease-in-out",
        className,
      )}
      style={{ height: isOpen ? height : 0 }}
      data-state={isOpen ? "open" : "closed"}
      aria-hidden={!isOpen}
      {...props}
    >
      <div className="px-4 pb-4 pt-0">{children}</div>
    </div>
  )
}

export {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
}
