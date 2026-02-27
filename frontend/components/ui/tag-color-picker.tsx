"use client";

import { useEffect, useRef } from "react";
import { Check } from "lucide-react";
import { PASTEL_PALETTE } from "@/lib/utils";

interface TagColorPickerProps {
  currentIndex: number;
  onSelect: (index: number) => void;
  onClose: () => void;
}

export function TagColorPicker({
  currentIndex,
  onSelect,
  onClose,
}: TagColorPickerProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener("mousedown", handler, true);
    return () => document.removeEventListener("mousedown", handler, true);
  }, [onClose]);

  return (
    <div
      ref={ref}
      className="absolute left-1/2 -translate-x-1/2 top-full mt-1 z-[100] rounded-lg border border-border bg-popover p-2.5 shadow-lg w-max"
    >
      <div className="grid grid-cols-4 gap-2.5">
        {PASTEL_PALETTE.map((entry, i) => (
          <button
            key={entry.name}
            type="button"
            title={entry.name}
            onClick={(e) => {
              e.stopPropagation();
              onSelect(i);
              onClose();
            }}
            className={`relative w-6 h-6 rounded-full transition-transform hover:scale-110 ${entry.swatch} ${
              i === currentIndex
                ? "ring-2 ring-offset-2 ring-foreground/40"
                : ""
            }`}
          >
            {i === currentIndex && (
              <Check className="absolute inset-0 m-auto h-3 w-3 text-white drop-shadow" />
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
