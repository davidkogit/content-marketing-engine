/**
 * LoginForm — email + password login with real-time validation.
 *
 * Handles client-side validation (email format, password presence),
 * API submission via the auth context login(), error display
 * (field-level + global API errors), and loading state.
 *
 * On successful login the auth context automatically redirects to
 * the dashboard — this component only needs to display the form UI.
 */

import { useState, useCallback, type FormEvent, type ChangeEvent } from "react";
import { AlertCircle, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useAuth } from "@/hooks/use-auth";
import { isAxiosError } from "axios";

// ── Pure Validation Helpers ───────────────────────────────────────────────────

/** Validates email format. Returns undefined if valid, error string if not. */
function validateEmail(value: string): string | undefined {
  const trimmed = value.trim();
  if (!trimmed) return "Email is required.";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed))
    return "Please enter a valid email address.";
  return undefined;
}

/** Validates password field. Returns undefined if valid, error string if not. */
function validatePassword(value: string): string | undefined {
  if (!value) return "Password is required.";
  return undefined;
}

// ── Field Error Map ───────────────────────────────────────────────────────────

interface FieldErrors {
  email?: string;
  password?: string;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function LoginForm() {
  const { login } = useAuth();

  // Form state
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [apiError, setApiError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Tracks which fields have been touched (for showing errors only after
  // the user interacts with a field, not immediately on page load).
  const [touched, setTouched] = useState<Record<string, boolean>>({});

  // ── Field-Level Validation on Blur ─────────────────────────────────────────

  /** Mark a field as touched and validate it. */
  const handleBlur = useCallback(
    (field: "email" | "password") => {
      setTouched((prev) => ({ ...prev, [field]: true }));
      setFieldErrors((prev) => {
        const error =
          field === "email"
            ? validateEmail(email)
            : validatePassword(password);
        return { ...prev, [field]: error };
      });
    },
    [email, password],
  );

  // ── Change Handlers (real-time re-validation after first touch) ────────────

  const handleEmailChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const value = e.target.value;
      setEmail(value);
      setApiError(null); // clear API errors on edit
      if (touched.email) {
        setFieldErrors((prev) => ({ ...prev, email: validateEmail(value) }));
      }
    },
    [touched.email],
  );

  const handlePasswordChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const value = e.target.value;
      setPassword(value);
      setApiError(null);
      if (touched.password) {
        setFieldErrors((prev) => ({
          ...prev,
          password: validatePassword(value),
        }));
      }
    },
    [touched.password],
  );

  // ── Run All Validations ────────────────────────────────────────────────────

  /** Validate every field. Returns true when the form is valid. */
  function runAllValidations(): boolean {
    const errors: FieldErrors = {
      email: validateEmail(email),
      password: validatePassword(password),
    };
    // Mark all fields as touched so they display errors
    setTouched({ email: true, password: true });
    setFieldErrors(errors);
    return !errors.email && !errors.password;
  }

  // ── Submit Handler ─────────────────────────────────────────────────────────

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();

    // Clear previous API errors
    setApiError(null);

    // Run client-side validation
    if (!runAllValidations()) return;

    setIsSubmitting(true);

    try {
      await login(email, password);
      // On success, auth-context handles navigation.  No further action.
    } catch (error: unknown) {
      // Map known API / network errors to user-friendly messages
      if (isAxiosError(error)) {
        const status = error.response?.status;
        if (status === 401 || status === 403) {
          setApiError("Invalid email or password. Please try again.");
        } else if (status && status >= 500) {
          setApiError("Server error. Please try again later.");
        } else if (error.code === "ERR_NETWORK" || !error.response) {
          setApiError(
            "Network error. Please check your connection and try again.",
          );
        } else {
          // Fallback: use the server's detail message if available
          const detail = (error.response?.data as { detail?: string })?.detail;
          setApiError(detail ?? "Login failed. Please try again.");
        }
      } else {
        setApiError("An unexpected error occurred. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  // ── Has any field-level error (for disabling submit) ───────────────────────

  const hasErrors = Boolean(fieldErrors.email || fieldErrors.password);

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <Card className="w-full">
      <CardHeader className="space-y-1">
        <CardTitle className="text-2xl">Welcome back</CardTitle>
        <CardDescription>
          Sign in to your account to continue
        </CardDescription>
      </CardHeader>

      <form onSubmit={handleSubmit} noValidate>
        <CardContent className="space-y-4">
          {/* ── Global API Error ──────────────────────────────────────── */}
          {apiError && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{apiError}</AlertDescription>
            </Alert>
          )}

          {/* ── Email Field ──────────────────────────────────────────── */}
          <div className="space-y-2">
            <Label htmlFor="login-email">Email</Label>
            <Input
              id="login-email"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={handleEmailChange}
              onBlur={() => handleBlur("email")}
              disabled={isSubmitting}
              aria-invalid={touched.email && Boolean(fieldErrors.email)}
              aria-describedby={
                fieldErrors.email ? "login-email-error" : undefined
              }
              autoComplete="email"
            />
            {touched.email && fieldErrors.email && (
              <p
                id="login-email-error"
                className="text-sm text-destructive"
                role="alert"
              >
                {fieldErrors.email}
              </p>
            )}
          </div>

          {/* ── Password Field ────────────────────────────────────────── */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="login-password">Password</Label>
            </div>
            <Input
              id="login-password"
              type="password"
              placeholder="Enter your password"
              value={password}
              onChange={handlePasswordChange}
              onBlur={() => handleBlur("password")}
              disabled={isSubmitting}
              aria-invalid={touched.password && Boolean(fieldErrors.password)}
              aria-describedby={
                fieldErrors.password ? "login-password-error" : undefined
              }
              autoComplete="current-password"
            />
            {touched.password && fieldErrors.password && (
              <p
                id="login-password-error"
                className="text-sm text-destructive"
                role="alert"
              >
                {fieldErrors.password}
              </p>
            )}
          </div>
        </CardContent>

        <CardFooter className="flex-col space-y-4">
          <Button
            type="submit"
            className="w-full"
            disabled={isSubmitting || (touched.email && touched.password && hasErrors)}
          >
            {isSubmitting && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            {isSubmitting ? "Signing in…" : "Sign in"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}
