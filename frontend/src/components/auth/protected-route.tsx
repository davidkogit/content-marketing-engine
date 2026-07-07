/**
 * ProtectedRoute — wraps routes that require authentication.
 *
 * Renders children (usually an <Outlet />) only when the user is
 * authenticated.  While auth state is loading, shows a centred
 * spinner.  If the user is not authenticated, redirects to /login
 * and preserves the intended destination in location state so the
 * login page can redirect back after success.
 */

import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/hooks/use-auth";

interface ProtectedRouteProps {
  /** Optional: render these children instead of <Outlet />. */
  children?: React.ReactNode;
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="flex h-screen w-screen items-center justify-center">
        <div className="text-muted-foreground animate-pulse">
          Verifying session…
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    // Preserve the attempted URL so LoginPage can redirect back.
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children ?? <Outlet />;
}
