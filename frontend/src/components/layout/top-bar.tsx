/**
 * TopBar — fixed top bar with hamburger menu (mobile) and auto-generated
 * breadcrumbs.
 *
 * The hamburger button is only visible on mobile (<md).  When clicked it
 * calls `onMenuClick` so the parent AppShell can open the mobile Sheet.
 */

import { Menu } from "lucide-react"
import { Button } from "@/components/ui/button"
import { BreadcrumbNav } from "@/components/layout/breadcrumb-nav"
import { cn } from "@/lib/utils"

interface TopBarProps {
  /** Called when the hamburger button is clicked (mobile only). */
  onMenuClick?: () => void
  /** Extra class for the outer wrapper. */
  className?: string
}

export function TopBar({ onMenuClick, className }: TopBarProps) {
  return (
    <header
      className={cn(
        "sticky top-0 z-30 flex h-14 shrink-0 items-center gap-3 border-b bg-background px-4",
        className,
      )}
    >
      {/* Hamburger — visible only below `md` breakpoint */}
      <Button
        variant="ghost"
        size="icon"
        className="md:hidden"
        onClick={onMenuClick}
        aria-label="Open navigation menu"
      >
        <Menu className="h-5 w-5" />
      </Button>

      {/* Breadcrumbs */}
      <BreadcrumbNav />
    </header>
  )
}
