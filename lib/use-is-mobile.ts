"use client";

import { useEffect, useState } from "react";

/**
 * SSR-safe hook that reports whether the current viewport is at or below the
 * given pixel breakpoint. Defaults to 768px to match Tailwind's `md` breakpoint
 * so JS gating stays consistent with `< md` Tailwind classes.
 */
export function useIsMobile(breakpoint = 768): boolean {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia(`(max-width: ${breakpoint - 1}px)`);
    const update = () => setIsMobile(mql.matches);
    update();
    if (typeof mql.addEventListener === "function") {
      mql.addEventListener("change", update);
      return () => mql.removeEventListener("change", update);
    }
    mql.addListener(update);
    return () => mql.removeListener(update);
  }, [breakpoint]);

  return isMobile;
}

/**
 * SSR-safe hook reporting whether the primary pointer is coarse (touch).
 * Use this to disable hover-only affordances (e.g. autoplay-on-hover).
 */
export function useIsTouch(): boolean {
  const [isTouch, setIsTouch] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia("(pointer: coarse)");
    const update = () => setIsTouch(mql.matches);
    update();
    if (typeof mql.addEventListener === "function") {
      mql.addEventListener("change", update);
      return () => mql.removeEventListener("change", update);
    }
    mql.addListener(update);
    return () => mql.removeListener(update);
  }, []);

  return isTouch;
}
