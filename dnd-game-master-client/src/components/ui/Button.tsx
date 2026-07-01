"use client";

import { forwardRef, type ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost";
type Size = "xs" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-blood text-parchment border border-gold/40 hover:bg-blood-bright hover:border-gold shadow-lg shadow-blood/30",
  secondary:
    "bg-stone text-parchment border border-stone-2 hover:border-gold/60 hover:text-gold-bright",
  ghost:
    "bg-parchment-dim text-obsidian font-semibold border border-transparent hover:text-parchment hover:bg-blood hover:border-gold/40",
};

const SIZES: Record<Size, string> = {
  xs: "px-2 py-2 text-xs",
  md: "px-5 py-2.5 text-sm",
  lg: "px-8 py-3.5 text-base",
};

/** Themed button used across the app for visual consistency. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", className = "", ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      className={`inline-flex items-center cursor-pointer justify-center gap-2 rounded-md font-display tracking-wide uppercase transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-40 ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...props}
    />
  );
});
