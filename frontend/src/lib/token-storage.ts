/**
 * Token storage helpers using localStorage.
 *
 * Wraps raw localStorage access behind typed get/set/clear helpers
 * so the rest of the app never touches localStorage directly.
 */

const ACCESS_TOKEN_KEY = "cme_access_token";
const REFRESH_TOKEN_KEY = "cme_refresh_token";

// ── Getters ──────────────────────────────────────────────────────────────────

/** Retrieve the stored access token (JWT), or null if not found. */
export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

/** Retrieve the stored refresh token, or null if not found. */
export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

// ── Setters ──────────────────────────────────────────────────────────────────

/** Persist the access + refresh token pair to localStorage. */
export function setTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
}

// ── Clear ────────────────────────────────────────────────────────────────────

/** Remove both tokens from localStorage (e.g. on logout or refresh failure). */
export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

// ── Predicates ───────────────────────────────────────────────────────────────

/** Returns true if an access token is present in storage. */
export function hasAccessToken(): boolean {
  return getAccessToken() !== null;
}
