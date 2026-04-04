import * as React from "react";
import { cn } from "@/lib/utils";

export function Card({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-white/15 bg-white/5 p-5 shadow-[0_10px_35px_rgba(2,6,23,0.35)]",
        className,
      )}
      {...props}
    />
  );
}
