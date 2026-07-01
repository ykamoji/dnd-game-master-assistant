"use client";

import { AnimatePresence, motion } from "framer-motion";
import { type ReactNode, useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { Button } from "./Button";

interface ModalProps {
  open: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
  size?: "xs" | "md" | "lg";
}

const SIZE: Record<NonNullable<ModalProps["size"]>, string> = {
  xs: "max-w-4xl",
  md: "max-w-7md",
  lg: "max-w-7xl",
};

/** Themed popup dialog (used for "coming soon" campaigns + DNA profile). */
export function Modal({ open, title, children, onClose, size = "md" }: ModalProps) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) return null;

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[9999] flex items-center justify-center p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <div
            className="absolute inset-0 bg-obsidian/80 backdrop-blur-sm"
            onClick={onClose}
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            className={`parchment relative z-10 flex max-h-[90vh] w-full ${SIZE[size]} flex-col rounded-card border border-gold/30 p-6 shadow-2xl shadow-black/60`}
            initial={{ scale: 0.9, y: 20 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.9, y: 20 }}
            transition={{ type: "spring", stiffness: 260, damping: 22 }}
          >
            <h3 className="text-gilded mb-3 shrink-0 font-display text-xl font-bold tracking-wide">
              {title}
            </h3>
            <div className="scroll-thin -mr-2 mb-6 min-h-0 flex-1 overflow-y-auto pr-2 text-parchment-dim">
              {children}
            </div>
            <div className="flex shrink-0 justify-end">
              <Button variant="secondary" onClick={onClose}>
                Close
              </Button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}
