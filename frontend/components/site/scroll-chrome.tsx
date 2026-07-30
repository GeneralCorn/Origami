"use client";

import { useEffect } from "react";

// The header's rule and blur describe an edge that does not exist until content
// has passed under it. The default is today's design, and the client only ever
// REMOVES chrome, so no JS, a hidden tab, or an observer that never resolves all
// leave the header exactly as it ships.
export function ScrollChrome() {
  useEffect(() => {
    const sentinel = document.querySelector("[data-top-sentinel]");
    if (!sentinel) {
      return;
    }
    const root = document.documentElement;
    let ready = false;
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          root.setAttribute("data-at-top", "");
        } else {
          root.removeAttribute("data-at-top");
        }
      }
      // One frame later, so the first resolution of the observer is not itself
      // animated in on load.
      if (!ready) {
        ready = true;
        requestAnimationFrame(() => root.classList.add("chrome-ready"));
      }
    });
    observer.observe(sentinel);
    return () => {
      observer.disconnect();
      root.removeAttribute("data-at-top");
      root.classList.remove("chrome-ready");
    };
  }, []);

  return null;
}
