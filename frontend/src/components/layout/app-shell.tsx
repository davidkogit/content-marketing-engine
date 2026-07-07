/**
 * AppShell — main application layout with responsive sidebar + top bar.
 *
 * Layout:
 *   ┌──────────┬──────────────────────────────┐
 *   │          │  TopBar (sticky)              │
 *   │ Sidebar  ├──────────────────────────────┤
 *   │          │  <Outlet />  (scrollable)     │
 *   │          │                              │
 *   └──────────┴──────────────────────────────┘
 *
 * Responsive behaviour:
 *   Desktop (lg+)  : full sidebar (w-64) with labels, toggleable
 *   Tablet  (md)   : icon-only sidebar (w-16), toggleable to full
 *   Mobile  (<md)  : sidebar hidden; hamburger → Sheet overlay
 *
 * The sidebar defaults to expanded on desktop and collapsed on tablet.
 * A toggle button inside the sidebar lets the user switch at any size.
 */

import { useState, useEffect, useCallback } from "react"
import { Outlet } from "react-router-dom"
import { Sheet, SheetContent } from "@/components/ui/sheet"
import { Sidebar, SidebarContent } from "@/components/layout/sidebar"
import { TopBar } from "@/components/layout/top-bar"

// ── Media-Query Hook ─────────────────────────────────────────────────────

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === "undefined") return false
    return window.matchMedia(query).matches
  })

  useEffect(() => {
    const mq = window.matchMedia(query)
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches)

    // Sync on mount in case initial value is stale (SSR)
    setMatches(mq.matches)

    mq.addEventListener("change", handler)
    return () => mq.removeEventListener("change", handler)
  }, [query])

  return matches
}

// ── AppShell ─────────────────────────────────────────────────────────────

export function AppShell() {
  const isMobile = useMediaQuery("(max-width: 767px)")
  const isTablet = useMediaQuery(
    "(min-width: 768px) and (max-width: 1023px)",
  )
  const isDesktop = useMediaQuery("(min-width: 1024px)")

  const [mobileOpen, setMobileOpen] = useState(false)

  // Start collapsed on tablet, expanded on desktop.
  const [collapsed, setCollapsed] = useState(isTablet)

  // Sync collapsed when crossing the tablet/desktop boundary.
  useEffect(() => {
    if (isDesktop) {
      setCollapsed(false) // expand when we hit desktop
    } else if (isTablet) {
      setCollapsed(true) // collapse when we enter tablet
    }
  }, [isDesktop, isTablet])

  // Close mobile sheet when crossing into tablet/desktop territory.
  useEffect(() => {
    if (!isMobile) setMobileOpen(false)
  }, [isMobile])

  const toggleCollapsed = useCallback(() => {
    setCollapsed((prev) => !prev)
  }, [])

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* ── Desktop / Tablet Sidebar ────────────────────────────────── */}
      <Sidebar collapsed={collapsed} onToggleCollapse={toggleCollapsed} />

      {/* ── Mobile Sheet (hamburger — only on mobile) ──────────────── */}
      {isMobile && (
        <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
          <SheetContent side="left" className="w-72 p-0">
            {/* Simple logo for the mobile sheet */}
            <div className="flex h-14 items-center border-b px-4">
              <span className="text-lg font-semibold tracking-tight">
                Content Engine
              </span>
            </div>
            <SidebarContent onNavClick={() => setMobileOpen(false)} />
          </SheetContent>
        </Sheet>
      )}

      {/* ── Main Content Area ──────────────────────────────────────── */}
      <div className="flex flex-1 flex-col min-w-0">
        <TopBar onMenuClick={() => setMobileOpen(true)} />
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
