/**
 * Sidebar — main navigation sidebar with role-gated links, user info,
 * and an integrated collapse/expand toggle button.
 *
 * Exports:
 *   SidebarContent  — nav links + user section (no outer wrapper; usable
 *                      in both the fixed desktop sidebar and mobile Sheet).
 *   Sidebar          — full sidebar: outer <aside>, header with logo and
 *                      toggle, then SidebarContent inside.
 *
 * Responsive behaviour (driven by parent AppShell via props):
 *   Expanded (collapsed=false) : full sidebar with labels       (w-64)
 *   Collapsed (collapsed=true) : icon-only sidebar              (w-16)
 *   Mobile  (<md)             : hidden; replaced by Sheet       (hidden md:flex)
 */

import { NavLink, useNavigate } from "react-router-dom"
import { useAuth } from "@/hooks/use-auth"
import { cn } from "@/lib/utils"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Separator } from "@/components/ui/separator"
import { Button } from "@/components/ui/button"
import {
  LayoutDashboard,
  Package,
  FolderTree,
  Tags,
  FileText,
  Settings,
  LogOut,
  PanelLeftClose,
  PanelLeft,
  type LucideIcon,
} from "lucide-react"
import type { UserRole } from "@/types/user"
import { UserRole as UserRoleEnum } from "@/types/user"

// ── Navigation Item Definition ───────────────────────────────────────────

interface NavItem {
  label: string
  to: string
  icon: LucideIcon
  /** If set, only users with this role or higher can see the link. */
  minRole?: UserRole
  /** Match exactly or prefix.  "prefix" for nested paths. */
  match?: "exact" | "prefix"
}

const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", to: "/", icon: LayoutDashboard, match: "exact" },
  { label: "Products", to: "/products", icon: Package, match: "prefix" },
  { label: "Categories", to: "/categories", icon: FolderTree, match: "prefix" },
  { label: "Segments", to: "/segments", icon: Tags, match: "prefix" },
  { label: "Documents", to: "/documents", icon: FileText, match: "prefix" },
  {
    label: "Settings",
    to: "/settings",
    icon: Settings,
    match: "prefix",
  },
]

// ── Nav Link Component ───────────────────────────────────────────────────

interface NavLinkItemProps {
  item: NavItem
  collapsed: boolean
}

function NavLinkItem({ item, collapsed }: NavLinkItemProps) {
  const { hasRole } = useAuth()

  if (item.minRole && !hasRole(item.minRole)) {
    return null
  }

  return (
    <NavLink
      to={item.to}
      end={item.match === "exact"}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
          "hover:bg-accent hover:text-accent-foreground",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          isActive
            ? "bg-accent text-accent-foreground"
            : "text-muted-foreground",
          collapsed && "justify-center px-2",
        )
      }
      title={collapsed ? item.label : undefined}
    >
      <item.icon className="h-5 w-5 shrink-0" />
      {!collapsed && <span>{item.label}</span>}
    </NavLink>
  )
}

// ── User Avatar Fallback Initials ────────────────────────────────────────

function getUserInitials(email: string): string {
  const [name] = email.split("@")
  if (!name) return "?"
  return name.slice(0, 2).toUpperCase()
}

// ── Sidebar Content (nav + user section — no header/logo) ────────────────

interface SidebarContentProps {
  /** When true, labels are hidden (icon-only mode). */
  collapsed?: boolean
  /** Called when a nav link is clicked — used by mobile Sheet to close. */
  onNavClick?: () => void
}

export function SidebarContent({ collapsed = false, onNavClick }: SidebarContentProps) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate("/login", { replace: true })
  }

  return (
    <div className="flex h-full flex-col">
      {/* ── Navigation ──────────────────────────────────────────────── */}
      <nav className="flex-1 space-y-1 overflow-y-auto p-2" aria-label="Main navigation">
        {NAV_ITEMS.map((item) => (
          <div key={item.to} onClick={onNavClick}>
            <NavLinkItem item={item} collapsed={collapsed} />
          </div>
        ))}
      </nav>

      {/* ── User Section (bottom) ───────────────────────────────────── */}
      <Separator />
      <div className={cn("p-3", collapsed && "flex flex-col items-center")}>
        {user && (
          <div
            className={cn(
              "flex items-center gap-3",
              collapsed && "flex-col gap-1",
            )}
          >
            <Avatar className="h-8 w-8">
              <AvatarFallback className="text-xs">
                {getUserInitials(user.email)}
              </AvatarFallback>
            </Avatar>

            {!collapsed && (
              <div className="flex-1 min-w-0">
                <p className="truncate text-sm font-medium">{user.email}</p>
                <p className="truncate text-xs text-muted-foreground capitalize">
                  {user.role.replace("_", " ")}
                </p>
              </div>
            )}

            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 shrink-0 text-muted-foreground hover:text-foreground"
              onClick={handleLogout}
              title="Logout"
              aria-label="Logout"
            >
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Sidebar Wrapper (outer <aside>, header + toggle, SidebarContent) ─────

interface SidebarProps {
  /** When true, renders as icon-only collapsed sidebar. */
  collapsed?: boolean
  /** Called when the user clicks the collapse/expand toggle. */
  onToggleCollapse?: () => void
}

export function Sidebar({ collapsed = false, onToggleCollapse }: SidebarProps) {
  return (
    <aside
      className={cn(
        "hidden md:flex h-full shrink-0 flex-col border-r bg-background transition-all duration-200 ease-in-out",
        collapsed ? "w-16" : "w-64",
      )}
    >
      {/* ── Header: logo + collapse toggle ──────────────────────────── */}
      <div
        className={cn(
          "flex h-14 items-center border-b px-3 shrink-0",
          collapsed ? "justify-center gap-0" : "justify-between",
        )}
      >
        {collapsed ? (
          <span className="text-lg font-bold" title="Content Engine">
            CE
          </span>
        ) : (
          <span className="text-lg font-semibold tracking-tight">
            Content Engine
          </span>
        )}
        <Button
          variant="ghost"
          size="icon"
          className={cn(
            "h-8 w-8 shrink-0",
            collapsed && "absolute right-1",
          )}
          onClick={onToggleCollapse}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? (
            <PanelLeft className="h-4 w-4" />
          ) : (
            <PanelLeftClose className="h-4 w-4" />
          )}
        </Button>
      </div>

      {/* ── Nav + User content ──────────────────────────────────────── */}
      <div className="flex-1 overflow-hidden">
        <SidebarContent collapsed={collapsed} />
      </div>
    </aside>
  )
}
