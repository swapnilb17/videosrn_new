"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

type Side = "left" | "right" | "bottom";

export type SheetProps = {
  open: boolean;
  onClose: () => void;
  side?: Side;
  title?: React.ReactNode;
  description?: React.ReactNode;
  showHandle?: boolean;
  showClose?: boolean;
  className?: string;
  children: React.ReactNode;
  ariaLabel?: string;
};

/**
 * Lightweight sheet/drawer used for the mobile sidebar drawer, the Create
 * service chooser, and other mobile menus. Renders into a portal, locks body
 * scroll while open, closes on Escape, scrim tap, and (for bottom sheets) a
 * touch swipe-down past a threshold.
 */
export function Sheet({
  open,
  onClose,
  side = "bottom",
  title,
  description,
  showHandle = true,
  showClose = true,
  className,
  children,
  ariaLabel,
}: SheetProps) {
  const [mounted, setMounted] = React.useState(false);
  const [visible, setVisible] = React.useState(false);
  const [dragY, setDragY] = React.useState(0);
  const startYRef = React.useRef<number | null>(null);
  const sheetRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  React.useEffect(() => {
    if (!open) {
      setVisible(false);
      return;
    }
    const raf = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(raf);
  }, [open]);

  React.useEffect(() => {
    if (!open) return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prevOverflow;
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  if (!mounted || !open) return null;

  const sideClasses: Record<Side, string> = {
    left: cn(
      "left-0 top-0 h-full w-[88vw] max-w-sm rounded-r-2xl border-r",
      visible ? "translate-x-0" : "-translate-x-full",
    ),
    right: cn(
      "right-0 top-0 h-full w-[88vw] max-w-sm rounded-l-2xl border-l",
      visible ? "translate-x-0" : "translate-x-full",
    ),
    bottom: cn(
      "left-0 right-0 bottom-0 max-h-[92dvh] w-full rounded-t-2xl border-t",
      visible ? "translate-y-0" : "translate-y-full",
    ),
  };

  const handleTouchStart = (e: React.TouchEvent) => {
    if (side !== "bottom") return;
    startYRef.current = e.touches[0]?.clientY ?? null;
  };
  const handleTouchMove = (e: React.TouchEvent) => {
    if (side !== "bottom" || startYRef.current == null) return;
    const dy = (e.touches[0]?.clientY ?? 0) - startYRef.current;
    if (dy > 0) setDragY(dy);
  };
  const handleTouchEnd = () => {
    if (side !== "bottom") return;
    if (dragY > 120) {
      onClose();
    }
    setDragY(0);
    startYRef.current = null;
  };

  const dragTransform =
    side === "bottom" && dragY > 0 ? `translate3d(0, ${dragY}px, 0)` : undefined;

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label={ariaLabel ?? (typeof title === "string" ? title : undefined)}
      className="fixed inset-0 z-[100]"
    >
      <button
        type="button"
        aria-label="Close"
        tabIndex={-1}
        onClick={onClose}
        className={cn(
          "absolute inset-0 bg-black/55 backdrop-blur-sm transition-opacity duration-200",
          visible ? "opacity-100" : "opacity-0",
        )}
      />
      <div
        ref={sheetRef}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        style={dragTransform ? { transform: dragTransform } : undefined}
        className={cn(
          "fixed flex flex-col overflow-hidden border-white/15 bg-[#0b0f1f] text-white shadow-2xl transition-transform duration-250 ease-out",
          sideClasses[side],
          className,
        )}
      >
        {side === "bottom" && showHandle ? (
          <div className="flex justify-center pt-2 pb-1">
            <span className="block h-1 w-10 rounded-full bg-white/25" />
          </div>
        ) : null}

        {(title || showClose) && (
          <div className="flex items-start justify-between gap-3 px-5 pt-3 pb-2">
            <div className="min-w-0 flex-1">
              {title ? (
                <h2 className="text-lg font-semibold leading-tight">{title}</h2>
              ) : null}
              {description ? (
                <p className="mt-0.5 text-sm text-slate-400">{description}</p>
              ) : null}
            </div>
            {showClose ? (
              <button
                type="button"
                onClick={onClose}
                aria-label="Close"
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/15 bg-white/5 text-slate-300 transition hover:bg-white/10 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            ) : null}
          </div>
        )}

        <div
          className={cn(
            "flex-1 overflow-y-auto px-5",
            side === "bottom" ? "pb-[max(1rem,env(safe-area-inset-bottom))]" : "pb-5",
          )}
        >
          {children}
        </div>
      </div>
    </div>,
    document.body,
  );
}
