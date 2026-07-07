/**
 * Auth context provider — manages authentication state for the entire app.
 *
 * Provides: user, isAuthenticated, isLoading, login(), register(),
 * logout(), hasRole().  Wraps the app root so any component can access
 * auth state via the useAuth() hook.
 *
 * Token storage and API calls are delegated to the existing lib modules:
 *   - lib/token-storage  (getAccessToken, setTokens, clearTokens)
 *   - lib/api-endpoints   (auth.login, auth.register, auth.me)
 *
 * The Axios interceptor in lib/api-client handles silent token refresh
 * on 401 responses — this context only needs to handle the happy path.
 */

import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";
import { auth } from "@/lib/api-endpoints";
import { setTokens, clearTokens, hasAccessToken } from "@/lib/token-storage";
import type { User, UserRole } from "@/types/user";

// ── Role Weights (lower number = higher privilege) ───────────────────────────

const ROLE_WEIGHT: Record<UserRole, number> = {
  super_admin: 0,
  admin: 1,
  editor: 2,
  viewer: 3,
};

// ── State Shape ──────────────────────────────────────────────────────────────

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

// ── Reducer Actions ──────────────────────────────────────────────────────────

type AuthAction =
  | { type: "AUTH_LOADING" }
  | { type: "AUTH_SUCCESS"; user: User }
  | { type: "AUTH_FAILURE" }
  | { type: "LOGOUT" };

// ── Initial State ────────────────────────────────────────────────────────────

const initialState: AuthState = {
  user: null,
  isAuthenticated: false,
  isLoading: true, // true until initial token check completes
};

// ── Reducer ──────────────────────────────────────────────────────────────────

function authReducer(state: AuthState, action: AuthAction): AuthState {
  switch (action.type) {
    case "AUTH_LOADING":
      return { ...state, isLoading: true };
    case "AUTH_SUCCESS":
      return {
        user: action.user,
        isAuthenticated: true,
        isLoading: false,
      };
    case "AUTH_FAILURE":
      return {
        user: null,
        isAuthenticated: false,
        isLoading: false,
      };
    case "LOGOUT":
      return {
        user: null,
        isAuthenticated: false,
        isLoading: false,
      };
    default:
      return state;
  }
}

// ── Context Value Shape ──────────────────────────────────────────────────────

export interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, role?: string) => Promise<void>;
  logout: () => void;
  hasRole: (minRole: UserRole) => boolean;
}

// ── Context ──────────────────────────────────────────────────────────────────

export const AuthContext = createContext<AuthContextValue | undefined>(
  undefined,
);

// ── Provider ─────────────────────────────────────────────────────────────────

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [state, dispatch] = useReducer(authReducer, initialState);
  const navigate = useNavigate();

  // ── Initial Token Check (on mount) ───────────────────────────────────────

  useEffect(() => {
    // Only attempt to fetch the user profile if a stored token exists.
    // The api-client interceptor handles 401 → refresh → redirect automatically.
    if (!hasAccessToken()) {
      dispatch({ type: "AUTH_FAILURE" });
      return;
    }

    let cancelled = false;

    async function validateToken() {
      try {
        const user = await auth.me();
        if (!cancelled) {
          dispatch({ type: "AUTH_SUCCESS", user });
        }
      } catch {
        // The API interceptor already handles refresh attempts and will
        // hard-redirect on failure.  If we get here, the interceptor
        // either recovered or the error is non-401 — treat as unauthenticated.
        if (!cancelled) {
          dispatch({ type: "AUTH_FAILURE" });
        }
      }
    }

    validateToken();

    return () => {
      cancelled = true;
    };
  }, []);

  // ── login() ──────────────────────────────────────────────────────────────

  const login = useCallback(
    async (email: string, password: string): Promise<void> => {
      dispatch({ type: "AUTH_LOADING" });

      try {
        // 1. Obtain token pair
        const tokenResponse = await auth.login(email, password);
        setTokens(tokenResponse.access_token, tokenResponse.refresh_token);

        // 2. Fetch the user profile with the new token
        const user = await auth.me();

        dispatch({ type: "AUTH_SUCCESS", user });
        navigate("/", { replace: true });
      } catch (error) {
        dispatch({ type: "AUTH_FAILURE" });
        throw error; // let the caller display the error
      }
    },
    [navigate],
  );

  // ── register() ───────────────────────────────────────────────────────────

  const register = useCallback(
    async (email: string, password: string, role?: string): Promise<void> => {
      dispatch({ type: "AUTH_LOADING" });

      try {
        // /auth/register returns TokenResponse — auto-login on success.
        // The optional `role` is threaded through to the API call so the
        // backend can assign the appropriate role (viewer/editor for
        // self-registration; admin+ requires invitation on the backend).
        const tokenResponse = await auth.register(email, password, role);
        setTokens(tokenResponse.access_token, tokenResponse.refresh_token);

        // Fetch the user profile
        const user = await auth.me();

        dispatch({ type: "AUTH_SUCCESS", user });
        navigate("/", { replace: true });
      } catch (error) {
        dispatch({ type: "AUTH_FAILURE" });
        throw error;
      }
    },
    [navigate],
  );

  // ── logout() ─────────────────────────────────────────────────────────────

  const logout = useCallback(() => {
    clearTokens();
    dispatch({ type: "LOGOUT" });
    navigate("/login", { replace: true });
  }, [navigate]);

  // ── hasRole() ────────────────────────────────────────────────────────────

  const hasRole = useCallback(
    (minRole: UserRole): boolean => {
      if (!state.user || !state.user.is_active) {
        return false;
      }
      return ROLE_WEIGHT[state.user.role] <= ROLE_WEIGHT[minRole];
    },
    [state.user],
  );

  // ── Memoised Context Value ───────────────────────────────────────────────

  const value = useMemo<AuthContextValue>(
    () => ({
      user: state.user,
      isAuthenticated: state.isAuthenticated,
      isLoading: state.isLoading,
      login,
      register,
      logout,
      hasRole,
    }),
    [state.user, state.isAuthenticated, state.isLoading, login, register, logout, hasRole],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
