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
import { useCallback, useState } from "react";
import { RoleGuard } from "@/components/auth/role-guard";
import { LlmSettingsTab } from "@/components/settings/llm-settings-tab";
import { UsersTab } from "@/components/settings/users-tab";
import { BrandRulesTab } from "@/components/settings/brand-rules-tab";
import { useSettings } from "@/hooks/use-settings";
import { auth } from "@/lib/api-endpoints";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Loader2 } from "lucide-react";
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
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">
          Manage LLM configuration, user access, and brand content rules.
        </p>
      </div>

      {/* ── Password Change — available to all users ──────────────────────── */}
      <PasswordSection />

      {/* ── Super Admin Tabs ──────────────────────────────────────────────── */}
      <RoleGuard
        minRole="super_admin"
        fallback={
          <p className="text-sm text-muted-foreground">
            Super Admin access required for system configuration.
          </p>
        }
      >
        <Tabs defaultValue="llm" className="space-y-6">
          <TabsList>
            <TabsTrigger value="llm">LLM</TabsTrigger>
            <TabsTrigger value="users">Users</TabsTrigger>
            <TabsTrigger value="brand-rules">Brand Rules</TabsTrigger>
          </TabsList>

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
      </RoleGuard>
    </div>
  );
}

// ── Password Change Section ──────────────────────────────────────────────────

function PasswordSection() {
  const [current, setCurrent] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(false);

    if (newPw.length < 8) {
      setError("New password must be at least 8 characters.");
      return;
    }
    if (newPw !== confirm) {
      setError("Passwords do not match.");
      return;
    }

    setLoading(true);
    try {
      await auth.changePassword(current, newPw);
      setSuccess(true);
      setCurrent("");
      setNewPw("");
      setConfirm("");
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Failed to change password.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>My Account</CardTitle>
        <CardDescription>Change your password.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4 max-w-sm">
          {error && (
            <p className="text-sm text-destructive rounded-md bg-destructive/10 p-2">{error}</p>
          )}
          {success && (
            <p className="text-sm text-green-600 rounded-md bg-green-50 p-2">
              Password changed successfully.
            </p>
          )}
          <div className="space-y-2">
            <Label htmlFor="current-pw">Current Password</Label>
            <Input
              id="current-pw"
              type="password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              required
              disabled={loading}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="new-pw">New Password</Label>
            <Input
              id="new-pw"
              type="password"
              value={newPw}
              onChange={(e) => setNewPw(e.target.value)}
              required
              disabled={loading}
              minLength={8}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="confirm-pw">Confirm New Password</Label>
            <Input
              id="confirm-pw"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              disabled={loading}
            />
          </div>
          <Button type="submit" disabled={loading}>
            {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Change Password
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
