/**
 * useSettings — data-fetching hook for the Super Admin settings panel.
 *
 * Provides state slices for each settings tab (LLM, Users, Brand Rules)
 * with loading / saving / error state management.  All API calls are
 * delegated to the typed endpoint module (lib/api-endpoints).
 *
 * Every mutating operation shows a toast on success or failure via the
 * shared toast() function so callers don't need to wire up toasts
 * themselves.
 */

import { useCallback, useEffect, useReducer } from "react";
import { settingsLlm, settingsUsers, settingsRules } from "@/lib/api-endpoints";
import { toast } from "@/hooks/use-toast";
import type {
  LLMConfigResponse,
  LLMConfigUpdateRequest,
  LLMConfigTestResponse,
  UserListItem,
  InviteUserRequest,
  ChangeRoleRequest,
  RuleName,
  UserRole,
} from "@/types";

// ── State Shape ──────────────────────────────────────────────────────────────

export type TabKey = "llm" | "users" | "brand-rules";

export interface SettingsState {
  /** Which tab is currently selected (handled externally by Tabs) */
  activeTab: TabKey;

  // ── LLM ────────────────────────────────────────────────────────────────
  llm: {
    config: LLMConfigResponse | null;
    isLoading: boolean;
    isSaving: boolean;
    isTesting: boolean;
    error: string | null;
    testResult: LLMConfigTestResponse | null;
  };

  // ── Users ──────────────────────────────────────────────────────────────
  users: {
    items: UserListItem[];
    total: number;
    isLoading: boolean;
    isInviting: boolean;
    error: string | null;
  };

  // ── Brand Rules ────────────────────────────────────────────────────────
  rules: {
    tone: { content: string | null; isLoading: boolean; isSaving: boolean };
    compliance: { content: string | null; isLoading: boolean; isSaving: boolean };
    style: { content: string | null; isLoading: boolean; isSaving: boolean };
    error: string | null;
  };
}

// ── Reducer Actions ──────────────────────────────────────────────────────────

type SettingsAction =
  // -- LLM --
  | { type: "LLM_LOADING" }
  | { type: "LLM_LOADED"; config: LLMConfigResponse | null }
  | { type: "LLM_ERROR"; error: string }
  | { type: "LLM_SAVING" }
  | { type: "LLM_SAVED"; config: LLMConfigResponse }
  | { type: "LLM_TESTING" }
  | { type: "LLM_TESTED"; result: LLMConfigTestResponse }
  // -- Users --
  | { type: "USERS_LOADING" }
  | { type: "USERS_LOADED"; items: UserListItem[]; total: number }
  | { type: "USERS_ERROR"; error: string }
  | { type: "USERS_INVITING" }
  | { type: "USERS_INVITED" }
  | { type: "USERS_UPDATED"; user: UserListItem }
  | { type: "USERS_REMOVED"; userId: number }
  // -- Brand Rules --
  | { type: "RULES_LOADING"; ruleName: RuleName }
  | { type: "RULES_LOADED"; ruleName: RuleName; content: string }
  | { type: "RULES_ERROR"; error: string }
  | { type: "RULES_SAVING"; ruleName: RuleName }
  | { type: "RULES_SAVED"; ruleName: RuleName }
  | { type: "RULES_CONTENT_SET"; ruleName: RuleName; content: string };

// ── Initial State ────────────────────────────────────────────────────────────

const initialState: SettingsState = {
  activeTab: "llm",
  llm: {
    config: null,
    isLoading: true,
    isSaving: false,
    isTesting: false,
    error: null,
    testResult: null,
  },
  users: {
    items: [],
    total: 0,
    isLoading: true,
    isInviting: false,
    error: null,
  },
  rules: {
    tone: { content: null, isLoading: true, isSaving: false },
    compliance: { content: null, isLoading: true, isSaving: false },
    style: { content: null, isLoading: true, isSaving: false },
    error: null,
  },
};

// ── Reducer ──────────────────────────────────────────────────────────────────

function settingsReducer(
  state: SettingsState,
  action: SettingsAction,
): SettingsState {
  switch (action.type) {
    // -- LLM --
    case "LLM_LOADING":
      return {
        ...state,
        llm: { ...state.llm, isLoading: true, error: null },
      };
    case "LLM_LOADED":
      return {
        ...state,
        llm: { ...state.llm, config: action.config, isLoading: false, error: null },
      };
    case "LLM_ERROR":
      return {
        ...state,
        llm: { ...state.llm, isLoading: false, error: action.error },
      };
    case "LLM_SAVING":
      return {
        ...state,
        llm: { ...state.llm, isSaving: true, error: null },
      };
    case "LLM_SAVED":
      return {
        ...state,
        llm: {
          ...state.llm,
          config: action.config,
          isSaving: false,
          error: null,
        },
      };
    case "LLM_TESTING":
      return {
        ...state,
        llm: { ...state.llm, isTesting: true, testResult: null },
      };
    case "LLM_TESTED":
      return {
        ...state,
        llm: {
          ...state.llm,
          isTesting: false,
          testResult: action.result,
        },
      };
    // -- Users --
    case "USERS_LOADING":
      return {
        ...state,
        users: { ...state.users, isLoading: true, error: null },
      };
    case "USERS_LOADED":
      return {
        ...state,
        users: {
          ...state.users,
          items: action.items,
          total: action.total,
          isLoading: false,
          error: null,
        },
      };
    case "USERS_ERROR":
      return {
        ...state,
        users: { ...state.users, isLoading: false, error: action.error },
      };
    case "USERS_INVITING":
      return {
        ...state,
        users: { ...state.users, isInviting: true },
      };
    case "USERS_INVITED":
      return {
        ...state,
        users: { ...state.users, isInviting: false },
      };
    case "USERS_UPDATED":
      return {
        ...state,
        users: {
          ...state.users,
          items: state.users.items.map((u) =>
            u.id === action.user.id ? action.user : u,
          ),
        },
      };
    case "USERS_REMOVED":
      return {
        ...state,
        users: {
          ...state.users,
          items: state.users.items.filter((u) => u.id !== action.userId),
        },
      };
    // -- Brand Rules --
    case "RULES_LOADING":
      return {
        ...state,
        rules: {
          ...state.rules,
          [action.ruleName]: {
            content: null,
            isLoading: true,
            isSaving: false,
          },
        },
      };
    case "RULES_LOADED":
      return {
        ...state,
        rules: {
          ...state.rules,
          [action.ruleName]: {
            content: action.content,
            isLoading: false,
            isSaving: false,
          },
          error: null,
        },
      };
    case "RULES_ERROR":
      return {
        ...state,
        rules: { ...state.rules, error: action.error },
      };
    case "RULES_SAVING":
      return {
        ...state,
        rules: {
          ...state.rules,
          [action.ruleName]: {
            ...state.rules[action.ruleName],
            isSaving: true,
          },
        },
      };
    case "RULES_SAVED":
      return {
        ...state,
        rules: {
          ...state.rules,
          [action.ruleName]: {
            ...state.rules[action.ruleName],
            isSaving: false,
          },
        },
      };
    case "RULES_CONTENT_SET":
      return {
        ...state,
        rules: {
          ...state.rules,
          [action.ruleName]: {
            ...state.rules[action.ruleName],
            content: action.content,
          },
        },
      };
    default:
      return state;
  }
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "An unexpected error occurred";
}

// ── Hook ─────────────────────────────────────────────────────────────────────

export function useSettings() {
  const [state, dispatch] = useReducer(settingsReducer, initialState);

  // ── Initial Load (on mount) ────────────────────────────────────────────────

  useEffect(() => {
    // Load LLM config
    async function loadLlm() {
      dispatch({ type: "LLM_LOADING" });
      try {
        const config = await settingsLlm.get();
        dispatch({ type: "LLM_LOADED", config });
      } catch (err: any) {
        // 404 means no config exists yet — show empty form, not an error
        if (err?.response?.status === 404) {
          dispatch({ type: "LLM_LOADED", config: null });
        } else {
          dispatch({ type: "LLM_ERROR", error: getErrorMessage(err) });
        }
      }
    }

    // Load users
    async function loadUsers() {
      dispatch({ type: "USERS_LOADING" });
      try {
        const res = await settingsUsers.list();
        dispatch({
          type: "USERS_LOADED",
          items: res.items.map((item) => ({ ...item, role: item.role as UserRole })),
          total: res.total,
        });
      } catch (err) {
        dispatch({ type: "USERS_ERROR", error: getErrorMessage(err) });
      }
    }

    // Load brand rules (all three)
    async function loadRule(ruleName: RuleName) {
      dispatch({ type: "RULES_LOADING", ruleName });
      try {
        const res = await settingsRules.get(ruleName);
        dispatch({ type: "RULES_LOADED", ruleName, content: res.content });
      } catch {
        // Non-fatal; rules may not exist yet
        dispatch({ type: "RULES_LOADED", ruleName, content: "" });
      }
    }

    loadLlm();
    loadUsers();
    loadRule("tone");
    loadRule("compliance");
    loadRule("style");
  }, []);

  // ── LLM Actions ──────────────────────────────────────────────────────────

  const saveLlmConfig = useCallback(
    async (body: LLMConfigUpdateRequest) => {
      dispatch({ type: "LLM_SAVING" });
      try {
        const config = await settingsLlm.update(body);
        dispatch({ type: "LLM_SAVED", config });
        toast({ title: "LLM settings saved", description: "Configuration updated successfully." });
        return true;
      } catch (err) {
        dispatch({ type: "LLM_ERROR", error: getErrorMessage(err) });
        toast({
          title: "Failed to save",
          description: getErrorMessage(err),
          variant: "destructive",
        });
        return false;
      }
    },
    [],
  );

  const testLlmConnection = useCallback(async () => {
    dispatch({ type: "LLM_TESTING" });
    try {
      const result = await settingsLlm.test();
      dispatch({ type: "LLM_TESTED", result });
      if (result.success) {
        toast({
          title: "Connection successful",
          description: `Connected to ${result.model_used ?? "API"} in ${result.latency_ms}ms`,
        });
      } else {
        toast({
          title: "Connection failed",
          description: result.message,
          variant: "destructive",
        });
      }
      return result;
    } catch (err) {
      const message = getErrorMessage(err);
      dispatch({ type: "LLM_TESTED", result: { success: false, latency_ms: 0, message, model_used: null } });
      toast({ title: "Test failed", description: message, variant: "destructive" });
      return null;
    }
  }, []);

  // ── User Actions ──────────────────────────────────────────────────────────

  const inviteUser = useCallback(async (body: InviteUserRequest) => {
    dispatch({ type: "USERS_INVITING" });
    try {
      await settingsUsers.invite(body);
      dispatch({ type: "USERS_INVITED" });
      toast({ title: "Invitation sent", description: `Invited ${body.email} as ${body.role}` });
      // Reload user list
      const res = await settingsUsers.list();
      dispatch({ type: "USERS_LOADED", items: res.items, total: res.total });
      return true;
    } catch (err) {
      dispatch({ type: "USERS_INVITED" });
      toast({
        title: "Invitation failed",
        description: getErrorMessage(err),
        variant: "destructive",
      });
      return false;
    }
  }, []);

  const changeUserRole = useCallback(
    async (userId: number, body: ChangeRoleRequest) => {
      try {
        const res = await settingsUsers.changeRole(userId, body);
        dispatch({
          type: "USERS_UPDATED",
          user: {
            id: res.user_id,
            email: res.email,
            role: res.role as UserRole,
            is_active: res.is_active,
            created_at: "",
          },
        });
        toast({ title: "Role updated", description: `${res.email} is now ${res.role}` });
        return true;
      } catch (err) {
        toast({
          title: "Role change failed",
          description: getErrorMessage(err),
          variant: "destructive",
        });
        return false;
      }
    },
    [],
  );

  const deactivateUser = useCallback(async (userId: number) => {
    try {
      const res = await settingsUsers.deactivate(userId);
      dispatch({ type: "USERS_REMOVED", userId });
      toast({ title: "User deactivated", description: `${res.email} has been deactivated.` });
      return true;
    } catch (err) {
      toast({
        title: "Deactivation failed",
        description: getErrorMessage(err),
        variant: "destructive",
      });
      return false;
    }
  }, []);

  // ── Brand Rule Actions ───────────────────────────────────────────────────

  const saveRule = useCallback(async (ruleName: RuleName, content: string) => {
    dispatch({ type: "RULES_SAVING", ruleName });
    try {
      await settingsRules.update(ruleName, content);
      dispatch({ type: "RULES_SAVED", ruleName });
      toast({
        title: `${capitalize(ruleName)} rule saved`,
        description: "Brand rule updated successfully.",
      });
      return true;
    } catch (err) {
      dispatch({ type: "RULES_SAVED", ruleName });
      toast({
        title: "Save failed",
        description: getErrorMessage(err),
        variant: "destructive",
      });
      return false;
    }
  }, []);

  const setRuleContent = useCallback(
    (ruleName: RuleName, content: string) => {
      dispatch({ type: "RULES_CONTENT_SET", ruleName, content });
    },
    [],
  );

  return {
    state,
    saveLlmConfig,
    testLlmConnection,
    inviteUser,
    changeUserRole,
    deactivateUser,
    saveRule,
    setRuleContent,
  };
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
