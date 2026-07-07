/**
 * useAuth — typed convenience hook that reads from AuthContext.
 *
 * Must be called inside an <AuthProvider> (which should wrap the
 * entire app root).  Throws a descriptive error if used outside.
 */

import { useContext } from "react";
import { AuthContext, type AuthContextValue } from "@/contexts/auth-context";

/**
 * Returns the full auth context value: user, isAuthenticated,
 * isLoading, login(), register(), logout(), hasRole().
 */
export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);

  if (context === undefined) {
    throw new Error(
      "useAuth() must be called inside an <AuthProvider>. " +
        "Wrap your component tree with <AuthProvider> at the root level.",
    );
  }

  return context;
}
