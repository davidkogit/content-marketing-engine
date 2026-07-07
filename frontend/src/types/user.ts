/**
 * User types — authentication, roles, and user profile shapes.
 *
 * Mirrors the backend: backend/app/models/user.py + backend/app/auth/schemas.py
 */

// ── UserRole Enum ────────────────────────────────────────────────────────────

export const UserRole = {
  SUPER_ADMIN: "super_admin",
  ADMIN: "admin",
  EDITOR: "editor",
  VIEWER: "viewer",
} as const;

export type UserRole = (typeof UserRole)[keyof typeof UserRole];

// ── User Interface ───────────────────────────────────────────────────────────

export interface User {
  id: number;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string; // ISO 8601 datetime
}

// ── UserListItem (lightweight, for user management list) ─────────────────────

export type UserListItem = User;

// ── UserResponse (alias matching backend auth/schemas.py UserResponse) ───────

export type UserResponse = User;
