"use client";

import { motion } from "framer-motion";
import { type ReactNode } from "react";

interface CardProps {
  title: string;
  description?: string;
  imageUrl: string;
  badge?: string;
  disabled?: boolean;
  onClick?: () => void;
  footer?: ReactNode;
}

/** Reusable image card with cover art + description (campaigns, saved games). */
export function Card({
  title,
  description,
  imageUrl,
  badge,
  disabled,
  onClick,
  footer,
}: CardProps) {
  return (
    <motion.button
      type="button"
      onClick={onClick}
      whileHover={{ y: -6 }}
      transition={{ type: "spring", stiffness: 300, damping: 20 }}
      className={`group relative cursor-pointer flex w-full flex-col overflow-hidden rounded-card border text-left transition-colors ${disabled
          ? "border-stone-2 opacity-80"
          : "border-gold/30 hover:border-gold"
        }`}
    >
      <div className="relative aspect-[3/4] w-full overflow-hidden bg-stone">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={imageUrl}
          alt={title}
          className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
          loading="lazy"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-obsidian via-obsidian/30 to-transparent" />
        {badge && (
          <span className="absolute right-2 top-2 rounded-full border border-gold/40 bg-obsidian/80 px-3 py-1 font-display text-[10px] uppercase tracking-widest text-gold-bright">
            {badge}
          </span>
        )}
      </div>
      <div className="parchment flex flex-1 flex-col gap-2 p-4">
        <h3 className="text-gilded font-display text-lg font-bold tracking-wide">
          {title}
        </h3>
        {description && (
          <p className="text-sm leading-relaxed text-parchment-dim">{description}</p>
        )}
        {footer && <div className="mt-auto pt-2">{footer}</div>}
      </div>
    </motion.button>
  );
}
