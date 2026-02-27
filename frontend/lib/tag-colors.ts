"use client";

import { useState, useCallback, useEffect } from "react";
import { PASTEL_PALETTE, tagColor } from "./utils";

const STORAGE_KEY = "origami-tag-colors";
const SYNC_EVENT = "origami-tag-colors-changed";

function loadColors(): Record<string, number> {
  if (typeof window === "undefined") return {};
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
  } catch {
    return {};
  }
}

export function useTagColors() {
  const [colors, setColors] = useState<Record<string, number>>(loadColors);

  // Sync across components when another instance updates localStorage
  useEffect(() => {
    const handler = () => setColors(loadColors());
    window.addEventListener(SYNC_EVENT, handler);
    return () => window.removeEventListener(SYNC_EVENT, handler);
  }, []);

  const setTagColorIndex = useCallback((tag: string, index: number) => {
    setColors((prev) => {
      const next = { ...prev, [tag]: index };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      window.dispatchEvent(new Event(SYNC_EVENT));
      return next;
    });
  }, []);

  const getTagColorIndex = useCallback(
    (tag: string): number | undefined => colors[tag],
    [colors],
  );

  const getTagColor = useCallback(
    (tag: string) => tagColor(tag, colors[tag]),
    [colors],
  );

  return {
    getTagColorIndex,
    setTagColorIndex,
    getTagColor,
    paletteLength: PASTEL_PALETTE.length,
  };
}
