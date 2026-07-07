/**
 * LLMSettingsTab — provider / model / API key configuration.
 *
 * Form validation rules:
 * - Provider is always required.
 * - Model name is required.
 * - API key is required when the provider changes and no key is stored.
 * - Test connection calls the backend health-check endpoint.
 */

import * as React from "react";
import { Loader2, CheckCircle2, XCircle } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiKeyInput } from "@/components/settings/api-key-input";
import type {
  LLMConfigResponse,
  LLMConfigTestResponse,
} from "@/types";

// ── Props ─────────────────────────────────────────────────────────────────────

interface LlmSettingsTabProps {
  /** The current LLM config from the server (null = loading) */
  config: LLMConfigResponse | null;
  /** Whether the initial config fetch is in progress */
  isLoading: boolean;
  /** Whether a save operation is in progress */
  isSaving: boolean;
  /** Whether a test-connection request is in flight */
  isTesting: boolean;
  /** Any fetch / save error message */
  error: string | null;
  /** The result of the most recent test-connection call */
  testResult: LLMConfigTestResponse | null;
  /** Called when the user clicks Save */
  onSave: (body: { provider: string; model: string; apiKey: string; apiBaseUrl?: string | null }) => Promise<boolean>;
  /** Called when the user clicks Test Connection */
  onTest: () => Promise<LLMConfigTestResponse | null>;
}

// ── Loading Skeleton ──────────────────────────────────────────────────────────

function LlmSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-6 w-36" />
        <Skeleton className="h-4 w-64" />
      </CardHeader>
      <CardContent className="space-y-4">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-44" />
      </CardContent>
    </Card>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export function LlmSettingsTab({
  config,
  isLoading,
  isSaving,
  isTesting,
  error,
  testResult,
  onSave,
  onTest,
}: LlmSettingsTabProps) {
  const [provider, setProvider] = React.useState<string>("openai");
  const [model, setModel] = React.useState<string>("");
  const [apiKey, setApiKey] = React.useState<string>("");
  const [apiBaseUrl, setApiBaseUrl] = React.useState<string>("");
  const [formErrors, setFormErrors] = React.useState<Record<string, string>>({});

  // Sync local state with server config when it loads
  React.useEffect(() => {
    if (config) {
      setProvider(config.provider);
      setModel(config.model);
      setApiKey(""); // never pre-fill the API key
      setApiBaseUrl(config.api_base_url ?? "");
    }
  }, [config]);

  // ── Loading State ─────────────────────────────────────────────────────────

  if (isLoading) return <LlmSkeleton />;

  // ── Error State ───────────────────────────────────────────────────────────

  if (error && !config) {
    return (
      <Card className="border-destructive">
        <CardHeader>
          <CardTitle className="text-destructive">Failed to Load</CardTitle>
          <CardDescription>{error}</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  // ── Form Validation ───────────────────────────────────────────────────────

  const validate = (): boolean => {
    const errors: Record<string, string> = {};

    if (!provider) {
      errors.provider = "Provider is required";
    }
    if (!model.trim()) {
      errors.model = "Model name is required";
    }
    // API key is required only when no key is already stored
    if (!config?.masked_api_key && !apiKey.trim()) {
      errors.apiKey = "API key is required to configure a provider";
    }

    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSave = async () => {
    if (!validate()) return;
    await onSave({ provider, model, apiKey, apiBaseUrl: apiBaseUrl || null });
  };

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <Card>
      <CardHeader>
        <CardTitle>LLM Configuration</CardTitle>
        <CardDescription>
          Configure the language model provider, model, and API credentials.
          Changing the provider requires a valid API key.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Provider */}
        <div className="space-y-2">
          <label htmlFor="llm-provider" className="text-sm font-medium">
            Provider
          </label>
          <Select
            value={provider}
            onValueChange={(v) => {
              setProvider(v);
              setFormErrors((prev) => ({ ...prev, provider: "" }));
            }}
            disabled={isSaving}
          >
            <SelectTrigger id="llm-provider">
              <SelectValue placeholder="Select a provider" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="openai">OpenAI</SelectItem>
              <SelectItem value="anthropic">Anthropic</SelectItem>
            </SelectContent>
          </Select>
          {formErrors.provider && (
            <p className="text-sm text-destructive" role="alert">
              {formErrors.provider}
            </p>
          )}
        </div>

        {/* Model */}
        <div className="space-y-2">
          <label htmlFor="llm-model" className="text-sm font-medium">
            Model
          </label>
          <Input
            id="llm-model"
            value={model}
            onChange={(e) => {
              setModel(e.target.value);
              setFormErrors((prev) => ({ ...prev, model: "" }));
            }}
            placeholder={provider === "openai" ? "gpt-4o" : "claude-3-5-sonnet-20241022"}
            disabled={isSaving}
            aria-invalid={!!formErrors.model}
            aria-describedby={formErrors.model ? "llm-model-error" : undefined}
          />
          {formErrors.model && (
            <p id="llm-model-error" className="text-sm text-destructive" role="alert">
              {formErrors.model}
            </p>
          )}
        </div>

        {/* API Base URL */}
        <div className="space-y-2">
          <label htmlFor="llm-base-url" className="text-sm font-medium">
            API Base URL <span className="text-muted-foreground font-normal">(optional)</span>
          </label>
          <Input
            id="llm-base-url"
            value={apiBaseUrl}
            onChange={(e) => setApiBaseUrl(e.target.value)}
            placeholder="https://api.openai.com/v1"
            disabled={isSaving}
          />
          <p className="text-xs text-muted-foreground">
            Custom endpoint for OpenRouter or self-hosted LLMs. Leave empty for defaults.
          </p>
        </div>

        {/* API Key */}
        <div className="space-y-2">
          <label htmlFor="llm-api-key" className="text-sm font-medium">
            API Key
          </label>
          <ApiKeyInput
            maskedValue={config?.masked_api_key}
            value={apiKey}
            onChange={(v) => {
              setApiKey(v);
              setFormErrors((prev) => ({ ...prev, apiKey: "" }));
            }}
            placeholder={`Enter your ${provider === "openai" ? "OpenAI" : "Anthropic"} API key`}
            disabled={isSaving}
            ariaDescribedby={
              formErrors.apiKey ? "llm-api-key-error" : undefined
            }
          />
          {formErrors.apiKey && (
            <p id="llm-api-key-error" className="text-sm text-destructive" role="alert">
              {formErrors.apiKey}
            </p>
          )}
          {config?.masked_api_key && (
            <p className="text-xs text-muted-foreground">
              A key is currently configured. Leave blank to keep it unchanged.
            </p>
          )}
        </div>

        {/* Error Banner */}
        {error && config && (
          <div className="rounded-md bg-destructive/10 px-4 py-2 text-sm text-destructive">
            {error}
          </div>
        )}

        {/* Test Result */}
        {testResult && (
          <div
            className={`flex items-start gap-2 rounded-md px-4 py-3 text-sm ${
              testResult.success
                ? "bg-emerald-50 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
                : "bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-200"
            }`}
          >
            {testResult.success ? (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
            ) : (
              <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
            )}
            <div>
              <p className="font-medium">
                {testResult.success ? "Connection Successful" : "Connection Failed"}
              </p>
              <p className="text-xs opacity-80">
                {testResult.message}
                {testResult.latency_ms > 0 &&
                  ` (${testResult.latency_ms}ms)`}
              </p>
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex flex-wrap gap-3 pt-2">
          <Button
            onClick={handleSave}
            disabled={isSaving || isTesting}
          >
            {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Save Configuration
          </Button>
          <Button
            variant="outline"
            onClick={onTest}
            disabled={isTesting || isSaving}
          >
            {isTesting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Test Connection
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
