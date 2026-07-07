/**
 * Axios API client with JWT interceptor and automatic token refresh.
 *
 * Features:
 * - Attaches the Authorization header from in-memory storage on every request.
 * - On 401 responses, attempts a silent refresh using the HttpOnly refresh cookie.
 * - Only one refresh is in-flight at a time (deduplication via promise latch).
 * - If the refresh fails, clears the in-memory token and redirects to /login.
 */

import axios, {
  type AxiosError,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from "axios";
import {
  getAccessToken,
  setAccessToken,
  clearTokens,
} from "./token-storage";

// ── Configuration ────────────────────────────────────────────────────────────

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

/** The singleton Axios instance used by all API calls. */
const apiClient: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
  withCredentials: true, // Send HttpOnly cookies on every request
});

// ── Refresh Token Deduplication ──────────────────────────────────────────────

/** Holds the in-flight refresh promise so concurrent 401s share one call. */
let refreshPromise: Promise<string | null> | null = null;

/**
 * Attempt to exchange the HttpOnly refresh cookie for a new access token.
 *
 * The refresh token is sent automatically via the HttpOnly cookie
 * (withCredentials: true).  The backend reads the cookie, validates it,
 * and returns a fresh access token in the response body.
 *
 * Returns the new access token on success, or null on failure.
 * Deduplicates concurrent refresh attempts — only one HTTP call is made.
 */
function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) {
    return refreshPromise; // reuse in-flight refresh
  }

  refreshPromise = (async (): Promise<string | null> => {
    try {
      // Use a raw axios call (not the interceptor-aware instance) to
      // avoid infinite retry loops on the /auth/refresh endpoint itself.
      // The refresh token is sent via the HttpOnly cookie automatically.
      const response = await axios.post<{ access_token: string }>(
        `${BASE_URL}/auth/refresh`,
        {},
        { withCredentials: true },
      );

      const { access_token } = response.data;
      setAccessToken(access_token);
      return access_token;
    } catch {
      clearTokens();
      return null;
    } finally {
      refreshPromise = null; // reset latch for next round
    }
  })();

  return refreshPromise;
}

// ── Request Interceptor — Attach Authorization Header ───────────────────────

apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = getAccessToken();
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error: AxiosError) => Promise.reject(error),
);

// ── Response Interceptor — Handle 401 with Refresh Flow ─────────────────────

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    // Only attempt refresh on 401 and if we haven't already retried.
    if (error.response?.status !== 401 || originalRequest._retry) {
      return Promise.reject(error);
    }

    // Don't attempt refresh if the failing request IS the refresh call itself.
    if (
      originalRequest.url?.includes("/auth/refresh") ||
      originalRequest.url?.includes("/auth/login")
    ) {
      return Promise.reject(error);
    }

    originalRequest._retry = true;

    const newAccessToken = await refreshAccessToken();

    if (!newAccessToken) {
      // Refresh failed — redirect to login.
      // Use window.location for a hard redirect that resets app state.
      window.location.href = "/login";
      return Promise.reject(error);
    }

    // Retry the original request with the fresh token.
    if (originalRequest.headers) {
      originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
    }
    return apiClient(originalRequest);
  },
);

export default apiClient;
