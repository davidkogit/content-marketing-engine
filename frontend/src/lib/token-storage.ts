/**
 * Token storage helpers — in-memory access token only.
 *
 * The refresh token is managed via an HttpOnly cookie set by the backend.
 * Only the access token (short-lived JWT) is held in memory here.
 */

let inMemoryAccessToken: string | null = null;

// ── Getters ──────────────────────────────────────────────────────────────────

/** Retrieve the stored access token (JWT), or null if not found. */
export function getAccessToken(): string | null {
  return inMemoryAccessToken;
}

// ── Setters ──────────────────────────────────────────────────────────────────

/** Store the access token in memory. */
export function setAccessToken(accessToken: string): void {
  inMemoryAccessToken = accessToken;
}

// ── Clear ────────────────────────────────────────────────────────────────────

/** Remove the in-memory access token (e.g. on logout or refresh failure). */
export function clearTokens(): void {
  inMemoryAccessToken = null;
}

// ── Predicates ───────────────────────────────────────────────────────────────

/** Returns true if an access token is present in memory. */
export function hasAccessToken(): boolean {
  return inMemoryAccessToken !== null;
}
