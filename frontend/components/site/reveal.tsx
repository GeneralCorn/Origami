"use client";

import { useEffect, useRef, type ReactNode } from "react";

export function Reveal({
  children,
  className,
  delay = 0,
  variant = "fade",
  decorative = false,
}: {
  children?: ReactNode;
  className?: string;
  delay?: number;
  variant?: "fade" | "crease";
  decorative?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const armed = variant === "crease" ? "crease-armed" : "reveal-armed";
  const shown = variant === "crease" ? "crease-in" : "reveal-in";

  useEffect(() => {
    const el = ref.current;
    if (!el) {
      return;
    }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }

    let observer: IntersectionObserver | null = null;

    const arm = () => {
      // Anything already on screen is left alone. Arming it would hide content
      // the visitor is looking at and then fade it back in, and the reveal is
      // only worth having for what scrolls into view later.
      if (el.getBoundingClientRect().top < window.innerHeight) {
        return;
      }
      el.style.transitionDelay = delay ? `${delay}s` : "";
      el.classList.add(armed);
      observer = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            if (entry.isIntersecting) {
              el.classList.add(shown);
              observer?.disconnect();
            }
          }
        },
        { rootMargin: "0px 0px -80px 0px" },
      );
      observer.observe(el);
    };

    // A hidden tab suspends rendering, so the observer cannot compute an
    // intersection and anything armed here would stay hidden until the visitor
    // scrolled it. Links routinely open in a background tab, so wait for the
    // tab to be looked at before hiding anything.
    if (document.visibilityState === "hidden") {
      const onVisible = () => {
        if (document.visibilityState === "visible") {
          document.removeEventListener("visibilitychange", onVisible);
          arm();
        }
      };
      document.addEventListener("visibilitychange", onVisible);
      return () => {
        document.removeEventListener("visibilitychange", onVisible);
        observer?.disconnect();
      };
    }

    arm();
    return () => observer?.disconnect();
  }, [delay, armed, shown]);

  return (
    <div ref={ref} className={className} aria-hidden={decorative || undefined}>
      {children}
    </div>
  );
}
