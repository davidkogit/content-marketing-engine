import * as React from "react"
import { cn } from "@/lib/utils"

// ── Avatar Root ─────────────────────────────────────────────────────────

interface AvatarProps extends React.HTMLAttributes<HTMLDivElement> {
  /** When true, renders as a childless wrapper for composition. */
  asChild?: boolean
}

const Avatar = React.forwardRef<HTMLDivElement, AvatarProps>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "relative flex h-10 w-10 shrink-0 overflow-hidden rounded-full",
        className,
      )}
      {...props}
    />
  ),
)
Avatar.displayName = "Avatar"

// ── Avatar Image ────────────────────────────────────────────────────────

interface AvatarImageProps extends React.ImgHTMLAttributes<HTMLImageElement> {
  /** Called when the image fails to load so the fallback can be shown. */
  onLoadingStatusChange?: (status: "loading" | "loaded" | "error") => void
}

const AvatarImage = React.forwardRef<HTMLImageElement, AvatarImageProps>(
  ({ className, onLoadingStatusChange, alt = "", ...props }, ref) => {
    const [status, setStatus] = React.useState<
      "loading" | "loaded" | "error"
    >("loading")

    const handleLoad: React.ReactEventHandler<HTMLImageElement> = (e) => {
      setStatus("loaded")
      onLoadingStatusChange?.("loaded")
      props.onLoad?.(e)
    }

    const handleError: React.ReactEventHandler<HTMLImageElement> = (e) => {
      setStatus("error")
      onLoadingStatusChange?.("error")
      props.onError?.(e)
    }

    return (
      <img
        ref={ref}
        alt={alt}
        className={cn(
          "aspect-square h-full w-full object-cover",
          status !== "loaded" && "hidden",
          className,
        )}
        onLoad={handleLoad}
        onError={handleError}
        {...props}
      />
    )
  },
)
AvatarImage.displayName = "AvatarImage"

// ── Avatar Fallback ─────────────────────────────────────────────────────

interface AvatarFallbackProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Initials or icon to show when no image is available. */
  children?: React.ReactNode
  /** Delay in ms before showing the fallback (purely cosmetic). */
  delayMs?: number
}

const AvatarFallback = React.forwardRef<HTMLDivElement, AvatarFallbackProps>(
  ({ className, children, delayMs = 0, ...props }, ref) => {
    const [visible, setVisible] = React.useState(delayMs === 0)

    React.useEffect(() => {
      if (delayMs <= 0) return
      const t = setTimeout(() => setVisible(true), delayMs)
      return () => clearTimeout(t)
    }, [delayMs])

    if (!visible) return null

    return (
      <div
        ref={ref}
        className={cn(
          "flex h-full w-full items-center justify-center rounded-full bg-muted text-muted-foreground text-sm font-medium",
          className,
        )}
        {...props}
      >
        {children}
      </div>
    )
  },
)
AvatarFallback.displayName = "AvatarFallback"

export { Avatar, AvatarImage, AvatarFallback }
