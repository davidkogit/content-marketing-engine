/**
 * SettingsPage — Super Admin configuration hub.
 *
 * Access is restricted to super_admin via the RoleGuard wrapper.
 *
 * Contains three tabbed sub-sections:
 *   1. LLM — provider/model/API key with test connection
 *   2. Users — invite, role change, deactivation table
 *   3. Brand Rules — accordion-based markdown editor
 *
 * All operations surface toast notifications via the useSettings hook.
 */

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCallback } from "react";
import { RoleGuard } from "@/components/auth/role-guard";
import { LlmSettingsTab } from "@/components/settings/llm-settings-tab";
import { UsersTab } from "@/components/settings/users-tab";
import { BrandRulesTab } from "@/components/settings/brand-rules-tab";
import { useSettings } from "@/hooks/use-settings";
import type { RuleName, UserRole } from "@/types";

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const {
    state,
    saveLlmConfig,
    testLlmConnection,
    inviteUser,
    changeUserRole,
    deactivateUser,
    saveRule,
    setRuleContent,
  } = useSettings();

  /** Bridge: LlmSettingsTab uses camelCase; the API layer uses snake_case. */
  const handleSaveLlm = async (body: {
    provider: string;
    model: string;
    apiKey: string;
  }) => {
    return saveLlmConfig({
      provider: body.provider,
      model: body.model,
      api_key: body.apiKey,
    });
  };

  /** Bridge: UsersTab expects (email, role) → Promise<boolean> */
  const handleInviteUser = useCallback(
    async (email: string, role: UserRole): Promise<boolean> => {
      return inviteUser({ email, role });
    },
    [inviteUser],
  );

  /** Bridge: UsersTab expects (userId, role) → Promise<boolean> */
  const handleChangeUserRole = useCallback(
    async (userId: number, role: UserRole): Promise<boolean> => {
      return changeUserRole(userId, { role });
    },
    [changeUserRole],
  );

  return (
    <RoleGuard
      minRole="super_admin"
      fallback={
        <div className="flex h-64 items-center justify-center">
          <div className="text-center">
            <h2 className="text-xl font-semibold">Access Denied</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Only Super Admins can access settings.
            </p>
          </div>
        </div>
      }
    >
      <div className="container mx-auto p-6 space-y-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
          <p className="text-muted-foreground">
            Manage LLM configuration, user access, and brand content rules.
          </p>
        </div>

        <Tabs defaultValue="llm" className="space-y-6">
          <TabsList>
            <TabsTrigger value="llm">LLM</TabsTrigger>
            <TabsTrigger value="users">Users</TabsTrigger>
            <TabsTrigger value="brand-rules">Brand Rules</TabsTrigger>
          </TabsList>

          {/* ── LLM Tab ─────────────────────────────────────────────────── */}
          <TabsContent value="llm">
            <LlmSettingsTab
              config={state.llm.config}
              isLoading={state.llm.isLoading}
              isSaving={state.llm.isSaving}
              isTesting={state.llm.isTesting}
              error={state.llm.error}
              testResult={state.llm.testResult}
              onSave={handleSaveLlm}
              onTest={testLlmConnection}
            />
          </TabsContent>

          {/* ── Users Tab ────────────────────────────────────────────────── */}
          <TabsContent value="users">
            <UsersTab
              users={state.users.items}
              total={state.users.total}
              isLoading={state.users.isLoading}
              isInviting={state.users.isInviting}
              error={state.users.error}
              onInvite={handleInviteUser}
              onChangeRole={handleChangeUserRole}
              onDeactivate={deactivateUser}
            />
          </TabsContent>

          {/* ── Brand Rules Tab ──────────────────────────────────────────── */}
          <TabsContent value="brand-rules">
            <BrandRulesTab
              rules={state.rules}
              error={state.rules.error}
              onSave={saveRule}
              onContentChange={(ruleName: RuleName, content: string) =>
                setRuleContent(ruleName, content)
              }
            />
          </TabsContent>
        </Tabs>
      </div>
    </RoleGuard>
  );
}
