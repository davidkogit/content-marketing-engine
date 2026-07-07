/**
 * RegisterPage — public route for self-registration.
 *
 * Behaviour:
 *  - If the user is already authenticated, redirects to the dashboard.
 *  - While auth state is loading, shows a centred spinner.
 *  - When unauthenticated, renders a mobile-responsive centred card
 *    with app branding and the <RegisterForm /> component.
 *
 * Self-registration is limited to viewer and editor roles. Admin+
 * accounts require an invitation (enforced on the backend).
 *
 * Layout: full-height vertical stack (branding header → card body) that
 * remains centred and readable at all breakpoints.  The card takes
 * `max-w-sm` on desktop and full width on mobile.
 */

import { Navigate } from "react-router-dom";
import { useAuth } from "@/hooks/use-auth";
import { RegisterForm } from "@/components/auth/register-form";

export default function RegisterPage() {
  const { isAuthenticated, isLoading } = useAuth();

  // ── Loading State ──────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-background">
        <div className="text-muted-foreground animate-pulse">
          Loading…
        </div>
      </div>
    );
  }

  // ── Auth Guard: Redirect to Dashboard if Already Logged In ─────────────────

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  // ── Register View ──────────────────────────────────────────────────────────

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-4 py-8">
      {/* App Branding */}
      <div className="mb-8 flex flex-col items-center gap-2">
        <h1 className="text-3xl font-bold tracking-tight">
          Content Engine
        </h1>
        <p className="text-sm text-muted-foreground">
          LLM-powered product content marketing
        </p>
      </div>

      {/* Centred Card — responsive width */}
      <div className="w-full max-w-sm">
        <RegisterForm />
      </div>
    </div>
  );
}
