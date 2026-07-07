/**
 * GenerationControls — content generation type selector and trigger button.
 *
 * Lets the user pick a generation type (product_description, feature_bullets,
 * social_post, email_campaign) and fire generation for the current product.
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tooltip } from "@/components/ui/tooltip";
import { Sparkles, Loader2 } from "lucide-react";
import type { GenerationType } from "@/types";
import { GenerationType as GenType } from "@/types";

// ── Props ────────────────────────────────────────────────────────────────────

interface GenerationControlsProps {
  /** Whether generation is currently in progress. */
  isGenerating: boolean;
  /** Called with the selected generation type when the user clicks Generate. */
  onGenerate: (type: GenerationType) => void;
  disabled?: boolean;
}

// ── Options ──────────────────────────────────────────────────────────────────

const generationTypes: { value: GenerationType; label: string }[] = [
  { value: GenType.PRODUCT_DESCRIPTION, label: "Product Description" },
  { value: GenType.FEATURE_BULLETS, label: "Feature Bullets" },
  { value: GenType.SOCIAL_POST, label: "Social Post" },
  { value: GenType.EMAIL_BLAST, label: "Email Campaign" },
];

// ── Component ────────────────────────────────────────────────────────────────

export default function GenerationControls({
  isGenerating,
  onGenerate,
  disabled = false,
}: GenerationControlsProps) {
  const [selectedType, setSelectedType] = useState<GenerationType>(
    GenType.PRODUCT_DESCRIPTION,
  );

  const handleGenerate = () => {
    if (!isGenerating && !disabled) {
      onGenerate(selectedType);
    }
  };

  return (
    <div className="flex items-center gap-3">
      <Select
        value={selectedType}
        onValueChange={(value) => setSelectedType(value as GenerationType)}
        disabled={disabled || isGenerating}
      >
        <SelectTrigger className="w-[200px]">
          <SelectValue placeholder="Select generation type" />
        </SelectTrigger>
        <SelectContent>
          {generationTypes.map((gt) => (
            <SelectItem key={gt.value} value={gt.value}>
              {gt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Tooltip content={isGenerating ? "Generating..." : "Generate content"}>
        <Button
          onClick={handleGenerate}
          disabled={disabled || isGenerating}
          className="gap-2"
        >
          {isGenerating ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Generating…
            </>
          ) : (
            <>
              <Sparkles className="h-4 w-4" />
              Generate
            </>
          )}
        </Button>
      </Tooltip>
    </div>
  );
}
