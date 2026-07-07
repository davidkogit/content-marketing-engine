/**
 * RegisterForm — email + password + confirm + role selector for
 * self-registration.
 *
 * Self-registration is limited to the **viewer** and **editor** roles.
 * Admin and Super Admin accounts are created via invitation only
 * (enforced on the backend).  The role selector reflects this constraint
 * by only offering those two options.
 *
 * Handles:
 *  - Client-side validation (email format, password ≥ 8 chars, password
 *    match, all fields required)
 *  - Real-time feedback after field blur
 *  - Global API error display (email taken, server error, network error)
 *  - Loading state (spinner + disabled fields)
 *  - Redirect on success (via auth-context)
 */

import { useState, useCallback, type FormEvent, type ChangeEvent } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, Loader2 } from "lucide-react";
import { isAxiosError } from "axios";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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

// ── Pure Validation Helpers ───────────────────────────────────────────────────

/** Validates email format. Returns undefined if valid, error string if not. */
function validateEmail(value: string): string | undefined {
  const trimmed = value.trim();
  if (!trimmed) return "Email is required.";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed))
    return "Please enter a valid email address.";
  return undefined;
}

/** Validates password. Returns undefined if valid, error string if not. */
function validatePassword(value: string): string | undefined {
  if (!value) return "Password is required.";
  if (value.length < 8) return "Password must be at least 8 characters.";
  return undefined;
}

/** Ensures confirm matches password. */
function validateConfirm(value: string, password: string): string | undefined {
  if (!value) return "Please confirm your password.";
  if (value !== password) return "Passwords do not match.";
  return undefined;
}

// ── Field Error Map ───────────────────────────────────────────────────────────

interface FieldErrors {
  email?: string;
  password?: string;
  confirm?: string;
  role?: string;
}

// ── Role Options (self-register only) ────────────────────────────────────────

const ROLE_OPTIONS = [
  { value: "viewer", label: "Viewer — read-only access" },
  { value: "editor", label: "Editor — create and edit content" },
] as const;

// ── Component ─────────────────────────────────────────────────────────────────

export function RegisterForm() {
  const { register } = useAuth();

  // Form state
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [role, setRole] = useState("viewer"); // default to lowest privilege
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [apiError, setApiError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Tracks which fields have been touched (for showing errors only after
  // the user interacts with a field, not immediately on page load).
  const [touched, setTouched] = useState<Record<string, boolean>>({});

  // ── Field-Level Validation on Blur ─────────────────────────────────────────

  const handleBlur = useCallback(
    (field: "email" | "password" | "confirm") => {
      setTouched((prev) => ({ ...prev, [field]: true }));
      setFieldErrors((prev) => {
        let error: string | undefined;
        switch (field) {
          case "email":
            error = validateEmail(email);
            break;
          case "password":
            error = validatePassword(password);
            // Re-validate confirm when password changes
            if (confirm && error && !prev.confirm) {
              // If password is now valid, also check confirm
            }
            break;
          case "confirm":
            error = validateConfirm(confirm, password);
            break;
        }
        return { ...prev, [field]: error };
      });
    },
    [email, password, confirm],
  );

  // ── Change Handlers (real-time re-validation after first touch) ────────────

  const handleEmailChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const value = e.target.value;
      setEmail(value);
      setApiError(null);
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

      // Re-validate password if touched
      if (touched.password) {
        setFieldErrors((prev) => ({
          ...prev,
          password: validatePassword(value),
        }));
      }

      // Re-validate confirm if already touched (it depends on password)
      if (touched.confirm) {
        setFieldErrors((prev) => ({
          ...prev,
          confirm: validateConfirm(confirm, value),
        }));
      }
    },
    [touched.password, touched.confirm, confirm],
  );

  const handleConfirmChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const value = e.target.value;
      setConfirm(value);
      setApiError(null);
      if (touched.confirm) {
        setFieldErrors((prev) => ({
          ...prev,
          confirm: validateConfirm(value, password),
        }));
      }
    },
    [touched.confirm, password],
  );

  const handleRoleChange = useCallback((value: string) => {
    setRole(value);
    setApiError(null);
  }, []);

  // ── Run All Validations ────────────────────────────────────────────────────

  /** Validate every field. Returns true when the form is valid. */
  function runAllValidations(): boolean {
    const errors: FieldErrors = {
      email: validateEmail(email),
      password: validatePassword(password),
      confirm: validateConfirm(confirm, password),
    };
    setTouched({ email: true, password: true, confirm: true });
    setFieldErrors(errors);
    return !errors.email && !errors.password && !errors.confirm;
  }

  // ── Submit Handler ─────────────────────────────────────────────────────────

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();

    setApiError(null);

    if (!runAllValidations()) return;

    setIsSubmitting(true);

    try {
      // Pass the selected role to the auth context so the backend
      // assigns the appropriate privilege level.
      await register(email, password, role);
      // On success, auth-context handles token storage + navigation.
    } catch (error: unknown) {
      if (isAxiosError(error)) {
        const status = error.response?.status;

        if (status === 409) {
          // Conflict — email already taken
          setApiError(
            "An account with this email already exists. Try signing in instead.",
          );
        } else if (status === 400) {
          // Validation error from backend — display field errors
          const backendErrors = error.response?.data as {
            detail?: string;
          };
          if (backendErrors?.detail) {
            setApiError(backendErrors.detail);
          } else {
            setApiError("Please check your inputs and try again.");
          }
        } else if (status && status >= 500) {
          setApiError("Server error. Please try again later.");
        } else if (error.code === "ERR_NETWORK" || !error.response) {
          setApiError(
            "Network error. Please check your connection and try again.",
          );
        } else {
          const detail = (error.response?.data as { detail?: string })?.detail;
          setApiError(detail ?? "Registration failed. Please try again.");
        }
      } else {
        setApiError("An unexpected error occurred. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  // ── Has any field-level error (for disabling submit) ───────────────────────

  const hasErrors = Boolean(
    fieldErrors.email || fieldErrors.password || fieldErrors.confirm,
  );

  // Ensure all required fields have been touched before enabling submit
  const allFieldsTouched =
    touched.email && touched.password && touched.confirm;

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <Card className="w-full">
      <CardHeader className="space-y-1">
        <CardTitle className="text-2xl">Create an account</CardTitle>
        <CardDescription>
          Register to start managing your product content
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
            <Label htmlFor="register-email">Email</Label>
            <Input
              id="register-email"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={handleEmailChange}
              onBlur={() => handleBlur("email")}
              disabled={isSubmitting}
              aria-invalid={touched.email && Boolean(fieldErrors.email)}
              aria-describedby={
                fieldErrors.email ? "register-email-error" : undefined
              }
              autoComplete="email"
            />
            {touched.email && fieldErrors.email && (
              <p
                id="register-email-error"
                className="text-sm text-destructive"
                role="alert"
              >
                {fieldErrors.email}
              </p>
            )}
          </div>

          {/* ── Password Field ────────────────────────────────────────── */}
          <div className="space-y-2">
            <Label htmlFor="register-password">Password</Label>
            <Input
              id="register-password"
              type="password"
              placeholder="Min. 8 characters"
              value={password}
              onChange={handlePasswordChange}
              onBlur={() => handleBlur("password")}
              disabled={isSubmitting}
              aria-invalid={touched.password && Boolean(fieldErrors.password)}
              aria-describedby={
                fieldErrors.password ? "register-password-error" : undefined
              }
              autoComplete="new-password"
            />
            {touched.password && fieldErrors.password && (
              <p
                id="register-password-error"
                className="text-sm text-destructive"
                role="alert"
              >
                {fieldErrors.password}
              </p>
            )}
          </div>

          {/* ── Confirm Password Field ─────────────────────────────────── */}
          <div className="space-y-2">
            <Label htmlFor="register-confirm">Confirm password</Label>
            <Input
              id="register-confirm"
              type="password"
              placeholder="Re-enter your password"
              value={confirm}
              onChange={handleConfirmChange}
              onBlur={() => handleBlur("confirm")}
              disabled={isSubmitting}
              aria-invalid={touched.confirm && Boolean(fieldErrors.confirm)}
              aria-describedby={
                fieldErrors.confirm ? "register-confirm-error" : undefined
              }
              autoComplete="new-password"
            />
            {touched.confirm && fieldErrors.confirm && (
              <p
                id="register-confirm-error"
                className="text-sm text-destructive"
                role="alert"
              >
                {fieldErrors.confirm}
              </p>
            )}
          </div>

          {/* ── Role Selector ──────────────────────────────────────────── */}
          <div className="space-y-2">
            <Label htmlFor="register-role">Role</Label>
            <Select
              value={role}
              onValueChange={handleRoleChange}
              disabled={isSubmitting}
            >
              <SelectTrigger id="register-role" className="w-full">
                <SelectValue placeholder="Select a role" />
              </SelectTrigger>
              <SelectContent>
                {ROLE_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Admin and Super Admin roles require an invitation.
            </p>
          </div>
        </CardContent>

        <CardFooter className="flex-col space-y-4">
          <Button
            type="submit"
            className="w-full"
            disabled={isSubmitting || (allFieldsTouched && hasErrors)}
          >
            {isSubmitting && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            {isSubmitting ? "Creating account…" : "Create account"}
          </Button>

          <p className="text-center text-sm text-muted-foreground">
            Already have an account?{" "}
            <Link
              to="/login"
              className="font-medium text-primary underline underline-offset-4 hover:text-primary/90"
            >
              Sign in
            </Link>
          </p>
        </CardFooter>
      </form>
    </Card>
  );
}
