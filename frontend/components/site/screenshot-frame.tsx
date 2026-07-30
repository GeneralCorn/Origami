"use client";

import Image from "next/image";
import { useRef } from "react";
import { motion, useReducedMotion, useScroll, useTransform } from "motion/react";
import { Reveal } from "@/components/site/reveal";
import screenshotLight from "@/assets/screenshot-light.png";

export function ScreenshotFrame() {
  const reduced = useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start end", "end start"],
  });
  const parallaxY = useTransform(scrollYProgress, [0, 1], [30, -30]);

  return (
    <section ref={ref} className="relative">
      <div
        aria-hidden="true"
        className="absolute inset-x-0 bottom-0 h-1/2 border-y border-line bg-paper-deep/70"
      />
      <div className="relative mx-auto max-w-[1120px] px-6 md:px-8">
        {/* The parallax only ever sets a transform, so a tab that never runs it
            shows a static screenshot rather than an empty frame. */}
        <motion.div style={reduced ? undefined : { y: parallaxY }}>
          <Reveal>
            <figure>
              <div className="rounded-xl border border-line-strong bg-surface p-1.5 shadow-frame sm:p-2">
              <Image
                src={screenshotLight}
                alt="The Origami workspace: a Markdown editor, a rendered note, and the research agent side by side"
                priority
                className="h-auto w-full rounded-lg border border-line"
              />
              </div>
              <figcaption className="mt-4 flex items-baseline justify-between gap-4 pb-10 font-mono text-[11px] tracking-[0.14em] text-subtle uppercase sm:pb-14">
                <span>The workspace today</span>
                <span className="hidden sm:block">notes &middot; reader &middot; agent</span>
              </figcaption>
            </figure>
          </Reveal>
        </motion.div>
      </div>
    </section>
  );
}
