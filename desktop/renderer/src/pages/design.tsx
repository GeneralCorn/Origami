import { useState } from "react";

import { LibraryView } from "@/components/library/library-view";
import "@/styles/skins.css";

// Each treatment skins the real library view rather than a mockup, so what is
// being compared is actual data at actual density. The note is the honest cost,
// not a sales line: see skins.css for why frosted confines blur to the two
// surfaces that never scroll.
const SKINS = [
  {
    id: "plain",
    name: "Plain",
    note: "What ships today. No effects, nothing to composite beyond text and borders.",
  },
  {
    id: "paper",
    name: "Paper",
    note: "The launch site's language brought inside. Serif headings, warm stock, hairline rules. Same render cost as plain.",
  },
  {
    id: "frosted",
    name: "Frosted",
    note: "Blur on the rail and header only, never behind the list. backdrop-filter re-samples what is behind it every frame, which is affordable on a fixed surface and not on a scrolling one.",
  },
  {
    id: "soft",
    name: "Soft (fails)",
    note: "Restrained neumorphism, kept here as the rejected option rather than deleted. The shadow pair is the tile's only boundary cue, and the canonical recipe measures 1.40:1 against the 3:1 that WCAG 1.4.11 requires for exactly that case. It cannot be tuned into compliance, because raising the contrast is the same operation as making it stop looking soft. See INTERFACE_DIRECTIONS.md section 2.2.",
  },
] as const;

export default function DesignPage() {
  const [skin, setSkin] = useState<string>("plain");
  const active = SKINS.find((entry) => entry.id === skin) ?? SKINS[0];

  return (
    <div className="flex h-screen w-screen flex-col bg-background">
      <div className="flex shrink-0 items-center gap-2 border-b border-black/10 px-4 py-2 dark:border-white/10">
        <span className="mr-1 text-xs tracking-wide uppercase opacity-45">Treatment</span>
        {SKINS.map((entry) => (
          <button
            key={entry.id}
            type="button"
            onClick={() => setSkin(entry.id)}
            aria-pressed={entry.id === skin}
            className={`rounded px-2.5 py-1 text-sm transition-colors ${
              entry.id === skin
                ? "bg-black/[0.08] font-medium dark:bg-white/15"
                : "hover:bg-black/[0.04] dark:hover:bg-white/10"
            }`}
          >
            {entry.name}
          </button>
        ))}
      </div>

      <p className="shrink-0 border-b border-black/[0.06] px-4 py-2 text-xs leading-relaxed opacity-55 dark:border-white/[0.06]">
        {active.note}
      </p>

      {/* The skin attribute is the only thing that changes. Everything below is
          the same component the real route renders. */}
      <div data-skin={skin} className="min-h-0 flex-1">
        <LibraryView />
      </div>
    </div>
  );
}
