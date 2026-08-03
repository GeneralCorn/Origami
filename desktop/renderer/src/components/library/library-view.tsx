import { useEffect, useMemo, useState } from "react";

import { fetchLibrary, type Library, type LibraryItem } from "@/lib/api/library";

// Facets are AND-ed across groups and OR-ed within one, which is what makes
// "screenshots I did not write" expressible. Ordered rather than derived from
// the response so the rail does not reshuffle as counts change.
const FACET_ORDER = [
  { key: "source_type" as const, label: "Source" },
  { key: "trust" as const, label: "Trust" },
  { key: "origin" as const, label: "Origin" },
];

type FacetKey = (typeof FACET_ORDER)[number]["key"];
type Selection = Record<FacetKey, Set<string>>;

const EMPTY_SELECTION: Selection = {
  source_type: new Set(),
  trust: new Set(),
  origin: new Set(),
};

function itemValue(item: LibraryItem, key: FacetKey): string {
  return key === "source_type" ? item.source_type : key === "trust" ? item.trust : item.origin;
}

function formatWhen(item: LibraryItem): string {
  const stamp = item.created_at || item.ingested_at;
  if (!stamp) {
    return "undated";
  }
  const parsed = new Date(stamp);
  return Number.isNaN(parsed.valueOf()) ? "undated" : parsed.toLocaleDateString();
}

function ModalityMix({ item }: { item: LibraryItem }) {
  const parts = Object.entries(item.modalities).filter(([, count]) => count);
  if (!parts.length) {
    return null;
  }
  return (
    <span className="flex items-center gap-2">
      {parts.map(([modality, count]) => (
        <span key={modality} className="tabular-nums">
          {count} {modality}
        </span>
      ))}
    </span>
  );
}

export function LibraryView() {
  const [library, setLibrary] = useState<Library | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selection, setSelection] = useState<Selection>(EMPTY_SELECTION);

  useEffect(() => {
    let live = true;
    fetchLibrary()
      .then((data) => live && setLibrary(data))
      .catch((cause) => live && setError(cause instanceof Error ? cause.message : String(cause)));
    return () => {
      live = false;
    };
  }, []);

  const items = useMemo(() => {
    if (!library) {
      return [];
    }
    return library.items.filter((item) =>
      FACET_ORDER.every(({ key }) => {
        const chosen = selection[key];
        return chosen.size === 0 || chosen.has(itemValue(item, key));
      }),
    );
  }, [library, selection]);

  const toggle = (key: FacetKey, value: string) => {
    setSelection((previous) => {
      const next = new Set(previous[key]);
      if (next.has(value)) {
        next.delete(value);
      } else {
        next.add(value);
      }
      return { ...previous, [key]: next };
    });
  };

  const active = FACET_ORDER.some(({ key }) => selection[key].size > 0);

  if (error) {
    return (
      <div className="p-8 text-sm text-red-600 dark:text-red-400">
        Could not load the library: {error}
      </div>
    );
  }

  if (!library) {
    return <div className="p-8 text-sm opacity-60">Reading the library…</div>;
  }

  return (
    <div className="flex h-full min-h-0">
      <aside className="w-56 shrink-0 overflow-y-auto border-r border-black/10 p-5 dark:border-white/10">
        <div className="flex items-baseline justify-between">
          <h2 className="text-xs font-medium tracking-wide uppercase opacity-60">Filter</h2>
          {active ? (
            <button
              type="button"
              onClick={() => setSelection(EMPTY_SELECTION)}
              className="text-xs opacity-60 hover:opacity-100"
            >
              Clear
            </button>
          ) : null}
        </div>

        {FACET_ORDER.map(({ key, label }) => {
          const counts = library.facets[key] ?? {};
          const values = Object.keys(counts).sort();
          if (!values.length) {
            return null;
          }
          return (
            <section key={key} className="mt-6">
              <h3 className="text-[11px] tracking-wide uppercase opacity-45">{label}</h3>
              <ul className="mt-2 space-y-0.5">
                {values.map((value) => {
                  const on = selection[key].has(value);
                  return (
                    <li key={value}>
                      <button
                        type="button"
                        onClick={() => toggle(key, value)}
                        aria-pressed={on}
                        className={`flex w-full items-baseline justify-between rounded px-2 py-1 text-left text-sm transition-colors ${
                          on
                            ? "bg-black/[0.07] font-medium dark:bg-white/10"
                            : "hover:bg-black/[0.04] dark:hover:bg-white/5"
                        }`}
                      >
                        <span>{value}</span>
                        <span className="tabular-nums text-xs opacity-50">{counts[value]}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>
          );
        })}

        <p className="mt-8 text-[11px] leading-relaxed opacity-40">
          Modality counts segments rather than items, so it will not add up to the totals above.
          One screenshot holds a caption and several runs of OCR.
        </p>
      </aside>

      <div className="min-w-0 flex-1 overflow-y-auto">
        <header className="flex items-baseline justify-between px-8 pt-7 pb-4">
          <h1 className="text-lg font-medium">Library</h1>
          <span className="text-sm tabular-nums opacity-50">
            {items.length === library.total
              ? `${library.total} items`
              : `${items.length} of ${library.total}`}
          </span>
        </header>

        {items.length === 0 ? (
          <p className="px-8 py-16 text-center text-sm opacity-50">
            {library.total === 0 ? "Nothing ingested yet." : "No items match these filters."}
          </p>
        ) : (
          <ul className="px-4 pb-10">
            {items.map((item) => (
              <li key={item.file_id}>
                <article className="flex items-baseline gap-4 rounded-lg px-4 py-3 hover:bg-black/[0.03] dark:hover:bg-white/[0.04]">
                  <span className="w-20 shrink-0 text-[11px] tracking-wide uppercase opacity-45">
                    {item.source_type}
                  </span>
                  <span className="min-w-0 flex-1 truncate">{item.title}</span>
                  <span className="hidden shrink-0 items-center gap-3 text-xs opacity-45 sm:flex">
                    <ModalityMix item={item} />
                    <span className="tabular-nums">{formatWhen(item)}</span>
                    {/* Stated rather than implied. Untrusted is the default for
                        anything Origami did not receive from the user directly,
                        so it is the common case and not an alarm. */}
                    <span className={item.trust === "untrusted" ? "opacity-70" : "opacity-100"}>
                      {item.trust}
                    </span>
                  </span>
                </article>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
