/**
 * InviteUserDialog — modal form for sending user invitations.
 *
 * Fields: email (validated format), role (select).
 * Requires email format validation before submission.
 * Shows loading state on the submit button while the invite is in flight.
 */

import * as React from "react";
import { Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { UserRole } from "@/types/user";

interface InviteUserDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onInvite: (email: string, role: UserRole) => Promise<boolean>;
  isInviting: boolean;
}

const ROLES: { value: UserRole; label: string }[] = [
  { value: "viewer", label: "Viewer" },
  { value: "editor", label: "Editor" },
  { value: "admin", label: "Admin" },
];

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function InviteUserDialog({
  open,
  onOpenChange,
  onInvite,
  isInviting,
}: InviteUserDialogProps) {
  const [email, setEmail] = React.useState("");
  const [role, setRole] = React.useState<UserRole>("viewer");
  const [emailError, setEmailError] = React.useState<string | null>(null);

  const resetForm = React.useCallback(() => {
    setEmail("");
    setRole("viewer");
    setEmailError(null);
  }, []);

  // Reset form when dialog opens/closes
  React.useEffect(() => {
    if (!open) {
      // Delay reset so the closing animation plays first
      const id = setTimeout(resetForm, 200);
      return () => clearTimeout(id);
    }
  }, [open, resetForm]);

  const validate = (): boolean => {
    if (!email.trim()) {
      setEmailError("Email is required");
      return false;
    }
    if (!EMAIL_REGEX.test(email.trim())) {
      setEmailError("Please enter a valid email address");
      return false;
    }
    setEmailError(null);
    return true;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    const success = await onInvite(email.trim(), role);
    if (success) {
      onOpenChange(false);
      resetForm();
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite User</DialogTitle>
          <DialogDescription>
            Send an invitation to a new user. They will receive a registration
            link via email.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Email */}
          <div className="space-y-2">
            <label htmlFor="invite-email" className="text-sm font-medium">
              Email
            </label>
            <Input
              id="invite-email"
              type="email"
              placeholder="user@example.com"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                if (emailError) setEmailError(null);
              }}
              disabled={isInviting}
              aria-invalid={!!emailError}
              aria-describedby={emailError ? "invite-email-error" : undefined}
            />
            {emailError && (
              <p
                id="invite-email-error"
                className="text-sm text-destructive"
                role="alert"
              >
                {emailError}
              </p>
            )}
          </div>

          {/* Role */}
          <div className="space-y-2">
            <label htmlFor="invite-role" className="text-sm font-medium">
              Role
            </label>
            <Select
              value={role}
              onValueChange={(v) => setRole(v as UserRole)}
              disabled={isInviting}
            >
              <SelectTrigger id="invite-role">
                <SelectValue placeholder="Select a role" />
              </SelectTrigger>
              <SelectContent>
                {ROLES.map((r) => (
                  <SelectItem key={r.value} value={r.value}>
                    {r.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <DialogFooter className="pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isInviting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isInviting}>
              {isInviting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Send Invitation
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
