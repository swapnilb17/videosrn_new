import { cn } from "@/lib/utils";
import type { ButtonHTMLAttributes } from "react";

type ClayButtonProps = ButtonHTMLAttributes<HTMLButtonElement>;

export function ClayButton({ className, ...props }: ClayButtonProps) {
  return (
    <button
      className={cn(
        "clay inline-flex items-center justify-center px-6 py-3 text-sm font-semibold text-white",
        className,
      )}
      {...props}
    />
  );
}
