import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const PASTEL_PALETTE = [
  {
    name: "Rose",
    swatch: "bg-rose-300 dark:bg-rose-600 palenight:bg-rose-600",
    bg: "bg-rose-100 dark:bg-rose-950 palenight:bg-rose-950",
    text: "text-rose-700 dark:text-rose-300 palenight:text-rose-300",
    border: "border-rose-200 dark:border-rose-800 palenight:border-rose-800",
  },
  {
    name: "Amber",
    swatch: "bg-amber-300 dark:bg-amber-600 palenight:bg-amber-600",
    bg: "bg-amber-100 dark:bg-amber-950 palenight:bg-amber-950",
    text: "text-amber-700 dark:text-amber-300 palenight:text-amber-300",
    border: "border-amber-200 dark:border-amber-800 palenight:border-amber-800",
  },
  {
    name: "Lime",
    swatch: "bg-lime-300 dark:bg-lime-600 palenight:bg-lime-600",
    bg: "bg-lime-100 dark:bg-lime-950 palenight:bg-lime-950",
    text: "text-lime-700 dark:text-lime-300 palenight:text-lime-300",
    border: "border-lime-200 dark:border-lime-800 palenight:border-lime-800",
  },
  {
    name: "Teal",
    swatch: "bg-teal-300 dark:bg-teal-600 palenight:bg-teal-600",
    bg: "bg-teal-100 dark:bg-teal-950 palenight:bg-teal-950",
    text: "text-teal-700 dark:text-teal-300 palenight:text-teal-300",
    border: "border-teal-200 dark:border-teal-800 palenight:border-teal-800",
  },
  {
    name: "Sky",
    swatch: "bg-sky-300 dark:bg-sky-600 palenight:bg-sky-600",
    bg: "bg-sky-100 dark:bg-sky-950 palenight:bg-sky-950",
    text: "text-sky-700 dark:text-sky-300 palenight:text-sky-300",
    border: "border-sky-200 dark:border-sky-800 palenight:border-sky-800",
  },
  {
    name: "Violet",
    swatch: "bg-violet-300 dark:bg-violet-600 palenight:bg-violet-600",
    bg: "bg-violet-100 dark:bg-violet-950 palenight:bg-violet-950",
    text: "text-violet-700 dark:text-violet-300 palenight:text-violet-300",
    border:
      "border-violet-200 dark:border-violet-800 palenight:border-violet-800",
  },
  {
    name: "Fuchsia",
    swatch: "bg-fuchsia-300 dark:bg-fuchsia-600 palenight:bg-fuchsia-600",
    bg: "bg-fuchsia-100 dark:bg-fuchsia-950 palenight:bg-fuchsia-950",
    text: "text-fuchsia-700 dark:text-fuchsia-300 palenight:text-fuchsia-300",
    border:
      "border-fuchsia-200 dark:border-fuchsia-800 palenight:border-fuchsia-800",
  },
  {
    name: "Orange",
    swatch: "bg-orange-300 dark:bg-orange-600 palenight:bg-orange-600",
    bg: "bg-orange-100 dark:bg-orange-950 palenight:bg-orange-950",
    text: "text-orange-700 dark:text-orange-300 palenight:text-orange-300",
    border:
      "border-orange-200 dark:border-orange-800 palenight:border-orange-800",
  },
  {
    name: "Emerald",
    swatch: "bg-emerald-300 dark:bg-emerald-600 palenight:bg-emerald-600",
    bg: "bg-emerald-100 dark:bg-emerald-950 palenight:bg-emerald-950",
    text: "text-emerald-700 dark:text-emerald-300 palenight:text-emerald-300",
    border:
      "border-emerald-200 dark:border-emerald-800 palenight:border-emerald-800",
  },
  {
    name: "Indigo",
    swatch: "bg-indigo-300 dark:bg-indigo-600 palenight:bg-indigo-600",
    bg: "bg-indigo-100 dark:bg-indigo-950 palenight:bg-indigo-950",
    text: "text-indigo-700 dark:text-indigo-300 palenight:text-indigo-300",
    border:
      "border-indigo-200 dark:border-indigo-800 palenight:border-indigo-800",
  },
];

export function tagColor(tag: string, index?: number) {
  let i = index;
  if (i === undefined) {
    let hash = 0;
    for (const ch of tag) hash = (hash * 31 + ch.charCodeAt(0)) | 0;
    i = Math.abs(hash) % PASTEL_PALETTE.length;
  }
  return PASTEL_PALETTE[i % PASTEL_PALETTE.length];
}
