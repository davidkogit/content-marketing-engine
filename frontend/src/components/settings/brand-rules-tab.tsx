/**
 * BrandRulesTab — markdown-based brand rule editor with accordion sections.
 *
 * Three accordion sections: Tone, Compliance, Style.
 * Each section shows the current markdown content in an editable textarea.
 * Save button per section sends the content to the backend.
 *
 * States: loading skeleton, empty state, error alert, saving spinner.
 */

import * as React from "react";
import { Loader2 } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import type { RuleName } from "@/types";

// ── Rule metadata ─────────────────────────────────────────────────────────────

interface RuleMeta {
  name: RuleName;
  label: string;
  description: string;
  placeholder: string;
}

const RULES: RuleMeta[] = [
  {
    name: "tone",
    label: "Tone of Voice",
    description:
      "Define the brand's tone — word choice, formality level, personality traits, and voice guidelines.",
    placeholder:
      "## Tone of Voice\n\nOur brand voice is professional yet approachable. We use...\n\n- Clear, simple language\n- No jargon unless necessary\n- Friendly but not casual",
  },
  {
    name: "compliance",
    label: "Compliance Rules",
    description:
      "Regulatory and legal constraints. Every generated copy is checked against these rules for violations.",
    placeholder:
      "## Compliance Rules\n\n- Do not make unsubstantiated health claims\n- Always include disclaimer for financial products\n- Must cite source for statistical claims",
  },
  {
    name: "style",
    label: "Style Guide",
    description:
      "Formatting conventions, heading styles, character limits, emoji policy, and structural rules for generated content.",
    placeholder:
      "## Style Guide\n\n- Max 300 characters per paragraph\n- Use sentence case for headings\n- No emojis in B2B content\n- Bullet points preferred over numbered lists",
  },
];

// ── Per-Rule State ────────────────────────────────────────────────────────────

interface RuleState {
  content: string | null;
  isLoading: boolean;
  isSaving: boolean;
}

interface BrandRulesTabProps {
  rules: Record<RuleName, RuleState>;
  error: string | null;
  onSave: (ruleName: RuleName, content: string) => Promise<boolean>;
  onContentChange: (ruleName: RuleName, content: string) => void;
}

// ── Loading Skeleton ──────────────────────────────────────────────────────────

function RulesSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-4 w-64" />
      </CardHeader>
      <CardContent className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </CardContent>
    </Card>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export function BrandRulesTab({
  rules,
  error,
  onSave,
  onContentChange,
}: BrandRulesTabProps) {
  const [accordionValue, setAccordionValue] = React.useState<string>("tone");
  const [dirtyRules, setDirtyRules] = React.useState<Set<RuleName>>(new Set());

  const allLoading = RULES.every((r) => rules[r.name].isLoading);
  const anyLoading = RULES.some((r) => rules[r.name].isLoading);

  const handleContentChange = (ruleName: RuleName, content: string) => {
    onContentChange(ruleName, content);
    setDirtyRules((prev) => new Set(prev).add(ruleName));
  };

  const handleSave = async (ruleName: RuleName) => {
    const content = rules[ruleName].content ?? "";
    const success = await onSave(ruleName, content);
    if (success) {
      setDirtyRules((prev) => {
        const next = new Set(prev);
        next.delete(ruleName);
        return next;
      });
    }
  };

  // ── Loading State ─────────────────────────────────────────────────────────

  if (allLoading) return <RulesSkeleton />;

  // ── Error State (with loaded rules) ───────────────────────────────────────

  if (error && RULES.every((r) => !rules[r.name].content)) {
    return (
      <Card className="border-destructive">
        <CardHeader>
          <CardTitle className="text-destructive">Failed to Load</CardTitle>
          <CardDescription>{error}</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <Card>
      <CardHeader>
        <CardTitle>Brand Rules</CardTitle>
        <CardDescription>
          Configure the authoritative rules that govern every AI-generated
          piece of content. Each rule is checked during generation.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error && (
          <div className="mb-4 rounded-md bg-destructive/10 px-4 py-2 text-sm text-destructive">
            {error}
          </div>
        )}

        <Accordion
          type="single"
          value={accordionValue}
          onValueChange={setAccordionValue}
          collapsible
        >
          {RULES.map((rule) => {
            const state = rules[rule.name];
            const isDirty = dirtyRules.has(rule.name);

            return (
              <AccordionItem key={rule.name} value={rule.name}>
                <AccordionTrigger>
                  <div className="flex items-center gap-3 text-left">
                    <span>{rule.label}</span>
                    {isDirty && (
                      <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:bg-amber-900 dark:text-amber-200">
                        Unsaved
                      </span>
                    )}
                  </div>
                </AccordionTrigger>
                <AccordionContent>
                  <div className="space-y-3">
                    <p className="text-sm text-muted-foreground">
                      {rule.description}
                    </p>

                    {/* Loading per-section */}
                    {state.isLoading ? (
                      <Skeleton className="h-40 w-full" />
                    ) : (
                      <>
                        <Textarea
                          value={state.content ?? ""}
                          onChange={(e) =>
                            handleContentChange(rule.name, e.target.value)
                          }
                          placeholder={rule.placeholder}
                          className="min-h-[200px] font-mono text-sm"
                          disabled={state.isSaving}
                          aria-label={`${rule.label} content`}
                        />

                        <div className="flex items-center gap-2">
                          <Button
                            size="sm"
                            onClick={() => handleSave(rule.name)}
                            disabled={state.isSaving || anyLoading}
                          >
                            {state.isSaving && (
                              <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                            )}
                            Save {rule.label}
                          </Button>

                          {/* Preview is a future feature; stub the button */}
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={state.isSaving}
                            title="Preview is available when the generation pipeline is active"
                          >
                            Preview
                          </Button>
                        </div>
                      </>
                    )}
                  </div>
                </AccordionContent>
              </AccordionItem>
            );
          })}
        </Accordion>
      </CardContent>
    </Card>
  );
}
