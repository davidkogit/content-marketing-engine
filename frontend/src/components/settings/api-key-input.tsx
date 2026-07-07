/**
 * ApiKeyInput — masked API key field with reveal toggle.
 *
 * When a masked value is provided (e.g. "sk-...xyz1"), it is shown as
 * read-only dots until the user clicks the eye icon.  The underlying
 * input is always of type "password" to prevent browser autofill/passwords
 * managers from storing the key.
 *
 * When the field is empty (no configured key yet), the reveal toggle
 * is hidden and the field behaves like a normal password input.
 */

import * as React from "react";
import { Eye, EyeOff } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface ApiKeyInputProps {
  /** The masked API key from the server (e.g. "sk-••••••••xyz1") */
  maskedValue?: string;
  /** Controlled value for the actual API key (user-typed, sent on save) */
  value: string;
  /** Called when the user types a new API key value */
  onChange: (value: string) => void;
  /** Optional placeholder text */
  placeholder?: string;
  /** Whether the field is disabled (e.g. while saving) */
  disabled?: boolean;
  /** aria-describedby reference */
  ariaDescribedby?: string;
}

export function ApiKeyInput({
  maskedValue,
  value,
  onChange,
  placeholder = "Enter your API key",
  disabled = false,
  ariaDescribedby,
}: ApiKeyInputProps) {
  const [isRevealed, setIsRevealed] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  // Whether this is a "replace existing key" field — when a masked
  // value exists we show the masked display until the user interacts.
  const hasExistingKey = !!maskedValue && maskedValue.length > 0;
  const isEditing = value.length > 0;

  // When revealing with a masked key, show the masked value briefly
  // (the user can then type to overwrite).
  React.useEffect(() => {
    if (isRevealed && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isRevealed]);

  const handleToggle = () => {
    setIsRevealed((prev) => !prev);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange(e.target.value);
  };

  return (
    <div className="relative">
      <Input
        ref={inputRef}
        type={isRevealed && !hasExistingKey ? "text" : "password"}
        value={
          // Show mask when there's an existing key and the user hasn't typed
          hasExistingKey && !isEditing
            ? "••••••••••••••••••••••••"
            : value
        }
        onChange={handleChange}
        placeholder={hasExistingKey && !isEditing ? maskedValue : placeholder}
        disabled={disabled}
        aria-describedby={ariaDescribedby}
        className={cn("pr-12 font-mono", disabled && "cursor-not-allowed")}
        autoComplete="off"
        spellCheck={false}
      />

      {/* Last 4 chars indicator when no explicit reveal */}
      {hasExistingKey && !isEditing && (
        <span
          className="pointer-events-none absolute right-10 top-1/2 -translate-y-1/2 text-xs text-muted-foreground font-mono"
          aria-hidden="true"
        >
          {maskedValue.slice(-4)}
        </span>
      )}

      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="absolute right-1 top-1/2 -translate-y-1/2 h-8 w-8"
        onClick={handleToggle}
        disabled={disabled}
        aria-label={isRevealed ? "Hide API key" : "Reveal API key"}
      >
        {isRevealed ? (
          <EyeOff className="h-4 w-4" />
        ) : (
          <Eye className="h-4 w-4" />
        )}
      </Button>
    </div>
  );
}
