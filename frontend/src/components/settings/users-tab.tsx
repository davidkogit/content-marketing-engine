/**
 * UsersTab — user management table with invite, role-change, and
 * deactivation workflows.
 *
 * Features:
 * - Tabular user list (email, role badge, status, created date)
 * - Invite User button → InviteUserDialog
 * - Inline role-change dropdown per row
 * - Deactivate button with confirmation via AlertDialog
 * - Loading / empty / error states
 */

import * as React from "react";
import { Loader2, Plus, UserX } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { InviteUserDialog } from "@/components/settings/invite-user-dialog";
import type { UserListItem, UserRole } from "@/types";

// ── Role badge color map ──────────────────────────────────────────────────────

const ROLE_VARIANT: Record<string, "default" | "secondary" | "warning" | "success"> = {
  super_admin: "success",
  admin: "default",
  editor: "warning",
  viewer: "secondary",
};

const ROLE_LABEL: Record<string, string> = {
  super_admin: "Super Admin",
  admin: "Admin",
  editor: "Editor",
  viewer: "Viewer",
};

function formatDate(iso: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

// ── Props ─────────────────────────────────────────────────────────────────────

interface UsersTabProps {
  users: UserListItem[];
  total: number;
  isLoading: boolean;
  isInviting: boolean;
  error: string | null;
  onInvite: (email: string, role: UserRole) => Promise<boolean>;
  onChangeRole: (userId: number, role: UserRole) => Promise<boolean>;
  onDeactivate: (userId: number) => Promise<boolean>;
}

// ── Loading Skeleton ──────────────────────────────────────────────────────────

function UsersSkeleton() {
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between">
        <div className="space-y-2">
          <Skeleton className="h-6 w-24" />
          <Skeleton className="h-4 w-48" />
        </div>
        <Skeleton className="h-10 w-28" />
      </CardHeader>
      <CardContent>
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="mb-2 h-12 w-full" />
        ))}
      </CardContent>
    </Card>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export function UsersTab({
  users,
  total,
  isLoading,
  isInviting,
  error,
  onInvite,
  onChangeRole,
  onDeactivate,
}: UsersTabProps) {
  const [inviteOpen, setInviteOpen] = React.useState(false);
  const [deactivateTarget, setDeactivateTarget] =
    React.useState<UserListItem | null>(null);
  const [confirmOpen, setConfirmOpen] = React.useState(false);

  const handleDeactivateClick = (user: UserListItem) => {
    setDeactivateTarget(user);
    setConfirmOpen(true);
  };

  const handleConfirmDeactivate = async () => {
    if (!deactivateTarget) return;
    await onDeactivate(deactivateTarget.id);
    setConfirmOpen(false);
    setDeactivateTarget(null);
  };

  // ── Loading State ─────────────────────────────────────────────────────────

  if (isLoading) return <UsersSkeleton />;

  // ── Error State ───────────────────────────────────────────────────────────

  if (error && users.length === 0) {
    return (
      <Card className="border-destructive">
        <CardHeader>
          <CardTitle className="text-destructive">Failed to Load</CardTitle>
          <CardDescription>{error}</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <>
      <Card>
        <CardHeader className="flex-row items-start justify-between">
          <div>
            <CardTitle>Users</CardTitle>
            <CardDescription>
              {total} user{total !== 1 ? "s" : ""} registered. Manage roles
              and access.
            </CardDescription>
          </div>
          <Button size="sm" onClick={() => setInviteOpen(true)}>
            <Plus className="mr-1 h-4 w-4" />
            Invite User
          </Button>
        </CardHeader>
        <CardContent>
          {error && users.length > 0 && (
            <div className="mb-4 rounded-md bg-destructive/10 px-4 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          {/* Empty State */}
          {users.length === 0 && (
            <div className="py-12 text-center text-muted-foreground">
              <p className="text-sm">No users found.</p>
              <p className="mt-1 text-xs">
                Click &ldquo;Invite User&rdquo; to add the first user.
              </p>
            </div>
          )}

          {/* User Table */}
          {users.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Email</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="w-[180px]">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((user) => (
                  <TableRow key={user.id}>
                    <TableCell className="font-mono text-sm">
                      {user.email}
                    </TableCell>
                    <TableCell>
                      <Badge variant={ROLE_VARIANT[user.role] ?? "secondary"}>
                        {ROLE_LABEL[user.role] ?? user.role}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <span
                        className={`inline-flex items-center gap-1.5 text-xs font-medium ${
                          user.is_active
                            ? "text-emerald-600 dark:text-emerald-400"
                            : "text-muted-foreground"
                        }`}
                      >
                        <span
                          className={`h-1.5 w-1.5 rounded-full ${
                            user.is_active
                              ? "bg-emerald-600 dark:bg-emerald-400"
                              : "bg-muted-foreground"
                          }`}
                        />
                        {user.is_active ? "Active" : "Inactive"}
                      </span>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatDate(user.created_at)}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {/* Role Change Dropdown */}
                        <Select
                          value={user.role}
                          onValueChange={(v) =>
                            onChangeRole(user.id, v as UserRole)
                          }
                        >
                          <SelectTrigger className="h-8 w-[110px] text-xs">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="viewer">Viewer</SelectItem>
                            <SelectItem value="editor">Editor</SelectItem>
                            <SelectItem value="admin">Admin</SelectItem>
                          </SelectContent>
                        </Select>

                        {/* Deactivate Button */}
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-muted-foreground hover:text-destructive"
                          onClick={() => handleDeactivateClick(user)}
                          aria-label={`Deactivate ${user.email}`}
                        >
                          <UserX className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Invite Dialog */}
      <InviteUserDialog
        open={inviteOpen}
        onOpenChange={setInviteOpen}
        onInvite={onInvite}
        isInviting={isInviting}
      />

      {/* Deactivate Confirmation */}
      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Deactivate User</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to deactivate{" "}
              <span className="font-medium">{deactivateTarget?.email}</span>?
              They will no longer be able to log in.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              destructive
              onClick={handleConfirmDeactivate}
            >
              Deactivate
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
