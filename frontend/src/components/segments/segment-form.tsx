import { useState, useEffect } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { segments } from "@/lib/api-endpoints"
import { useToast } from "@/hooks/use-toast"
import type { Segment, SegmentCreate, SegmentUpdate } from "@/types"

const TONE_OPTIONS = [
  { value: "professional", label: "Professional" },
  { value: "casual", label: "Casual" },
  { value: "technical", label: "Technical" },
  { value: "persuasive", label: "Persuasive" },
] as const

interface SegmentFormProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  segment?: Segment | null
  onSuccess: (segment: Segment) => void
}

export function SegmentForm({
  open,
  onOpenChange,
  segment,
  onSuccess,
}: SegmentFormProps) {
  const { toast } = useToast()
  const isEditing = !!segment

  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [targetAudience, setTargetAudience] = useState("")
  const [tone, setTone] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [nameError, setNameError] = useState("")

  useEffect(() => {
    if (open && segment) {
      setName(segment.name)
      setDescription(segment.description ?? "")
      setTargetAudience(segment.target_audience ?? "")
      setTone(segment.tone ?? "")
    } else if (open) {
      setName("")
      setDescription("")
      setTargetAudience("")
      setTone("")
    }
    setNameError("")
  }, [open, segment])

  const validate = (): boolean => {
    const trimmed = name.trim()
    if (!trimmed) {
      setNameError("Name is required.")
      return false
    }
    if (trimmed.length > 120) {
      setNameError("Name must be 120 characters or fewer.")
      return false
    }
    setNameError("")
    return true
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!validate()) return

    setSubmitting(true)
    try {
      const payload: SegmentCreate | SegmentUpdate = {
        name: name.trim(),
        description: description.trim() || null,
        target_audience: targetAudience.trim() || null,
        tone: tone || null,
      }

      let result: Segment
      if (isEditing && segment) {
        result = await segments.update(segment.id, payload)
        toast({ title: "Segment updated", variant: "success" })
      } else {
        result = await segments.create(payload as SegmentCreate)
        toast({ title: "Segment created", variant: "success" })
      }
      onSuccess(result)
      onOpenChange(false)
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail ?? err?.message ?? "An error occurred."
      if (msg.toLowerCase().includes("already exists")) {
        setNameError("A segment with this name already exists.")
      } else {
        toast({ title: "Error", description: msg, variant: "destructive" })
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {isEditing ? "Edit Segment" : "New Market Segment"}
          </DialogTitle>
          <DialogDescription>
            {isEditing
              ? "Update the segment details below."
              : "Define a new target market segment with audience and tone."}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="seg-name">Name *</Label>
            <Input
              id="seg-name"
              value={name}
              onChange={(e) => {
                setName(e.target.value)
                if (nameError) setNameError("")
              }}
              placeholder="e.g. Enterprise Buyers"
              maxLength={120}
              disabled={submitting}
              aria-invalid={!!nameError}
            />
            {nameError && (
              <p className="text-sm text-destructive">{nameError}</p>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="seg-desc">Description</Label>
            <Textarea
              id="seg-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Who is this segment for?"
              rows={2}
              disabled={submitting}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="seg-audience">Target Audience</Label>
            <Input
              id="seg-audience"
              value={targetAudience}
              onChange={(e) => setTargetAudience(e.target.value)}
              placeholder="e.g. C-level executives at mid-size companies"
              disabled={submitting}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="seg-tone">Tone</Label>
            <Select
              value={tone}
              onValueChange={setTone}
              disabled={submitting}
            >
              <SelectTrigger id="seg-tone">
                <SelectValue placeholder="Select a tone…" />
              </SelectTrigger>
              <SelectContent>
                {TONE_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Saving…" : isEditing ? "Save Changes" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
