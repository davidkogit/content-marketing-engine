/**
 * BreadcrumbNav — auto-generates breadcrumbs from the current URL path.
 *
 * Parses `window.location.pathname` (kept in sync via react-router) into
 * human-readable breadcrumb segments.  Each segment links to its cumulative
 * path, with the last segment rendered as the current page (non-clickable).
 *
 * Segment labels are resolved from a static dictionary; unknown segments
 * fall back to a title-cased version of the raw path segment.
 */
import { useLocation, Link } from "react-router-dom"
import { useMemo } from "react"
import {
  Breadcrumb,
  BreadcrumbList,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"

// ── Path Segment → Human-Readable Label ───────────────────────────────────

const LABEL_MAP: Record<string, string> = {
  products: "Products",
  categories: "Categories",
  segments: "Segments",
  documents: "Documents",
  settings: "Settings",
  dashboard: "Dashboard",
}

/**
 * Title-case a slug-like segment (e.g. "my-product" → "My Product").
 */
function segmentToLabel(segment: string): string {
  // Check the static map first
  if (LABEL_MAP[segment]) return LABEL_MAP[segment]

  // Split on hyphens, capitalise each word
  return segment
    .split("-")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ")
}

/**
 * Build breadcrumb items from a pathname string.
 *
 * Example: "/products/42" → [
 *   { label: "Products", path: "/products" },
 *   { label: "Detail",  path: null },         // current page
 * ]
 */
function buildCrumbs(
  pathname: string,
): { label: string; path: string | null }[] {
  const segments = pathname.split("/").filter(Boolean)
  if (segments.length === 0) {
    return [{ label: "Dashboard", path: null }]
  }

  return segments.map((seg, idx) => {
    const label = segmentToLabel(seg)
    const isLast = idx === segments.length - 1
    const path = isLast ? null : "/" + segments.slice(0, idx + 1).join("/")
    return { label, path }
  })
}

// ── Component ────────────────────────────────────────────────────────────

export function BreadcrumbNav() {
  const location = useLocation()

  const crumbs = useMemo(() => buildCrumbs(location.pathname), [location.pathname])

  if (crumbs.length === 0) return null

  return (
    <Breadcrumb>
      <BreadcrumbList>
        {crumbs.map((crumb, idx) => {
          const isLast = idx === crumbs.length - 1

          return (
            <BreadcrumbItem key={crumb.label + idx}>
              {isLast || crumb.path === null ? (
                <BreadcrumbPage>{crumb.label}</BreadcrumbPage>
              ) : (
                <BreadcrumbLink asChild>
                  <Link to={crumb.path!}>{crumb.label}</Link>
                </BreadcrumbLink>
              )}
              {!isLast && <BreadcrumbSeparator />}
            </BreadcrumbItem>
          )
        })}
      </BreadcrumbList>
    </Breadcrumb>
  )
}
