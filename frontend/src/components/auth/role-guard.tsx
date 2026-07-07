/**
 * RoleGuard — renders children only when the current user's role
 * meets or exceeds the required minimum role.
 *
 * Role hierarchy (highest → lowest):
 *   super_admin → admin → editor → viewer
 *
 * When the user lacks the required role the guard renders nothing
 * by default.  Pass a `fallback` prop to show a custom "forbidden"
 * view (or redirect component) instead.
 */

import type { ReactNode } from "react";
import type { UserRole } from "@/types/user";
import { useAuth } from "@/hooks/use-auth";

interface RoleGuardProps {
  /** Minimum role required to see the children. */
  minRole: UserRole;
  /** Content shown when the user passes the role check. */
  children: ReactNode;
  /** Optional fallback content when the role check fails. */
  fallback?: ReactNode;
}

export function RoleGuard({
  minRole,
  children,
  fallback = null,
}: RoleGuardProps) {
  const { hasRole, isLoading } = useAuth();

  // While the auth state is still resolving, render nothing to
  // avoid a brief flash of the fallback / forbidden state.
  if (isLoading) {
    return null;
  }

  if (!hasRole(minRole)) {
    return <>{fallback}</>;
  }

  return <>{children}</>;
}
