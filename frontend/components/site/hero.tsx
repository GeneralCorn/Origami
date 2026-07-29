"use client";

import { motion, useReducedMotion } from "motion/react";
import { FoldDiagram } from "@/components/site/fold-diagram";
import { ArrowDownIcon, GitHubIcon } from "@/components/site/icons";
import { repoUrl } from "@/lib/site";

const ease = [0.22, 0.55, 0.24, 1] as const;

export function Hero() {
  const reduced = useReducedMotion();

  const container = {
    hidden: {},
    visible: {
      transition: { staggerChildren: reduced ? 0 : 0.11, delayChildren: 0.05 },
    },
  };

  const item = {
    hidden: reduced ? { opacity: 1, y: 0 } : { opacity: 0, y: 26 },
    visible: { opacity: 1, y: 0, transition: { duration: reduced ? 0 : 0.8, ease } },
  };

  return (
    <section className="relative overflow-hidden">
      <div className="mx-auto grid max-w-[1120px] items-center gap-12 px-6 pt-36 pb-10 md:px-8 lg:grid-cols-[1fr_320px] lg:gap-20 lg:pt-44 lg:pb-14">
        <motion.div variants={container} initial="hidden" animate="visible">
          <motion.p variants={item} className="eyebrow flex items-center gap-3 text-subtle">
            <span className="inline-block h-2 w-2 rotate-45 bg-accent" aria-hidden="true" />
            Open source &middot; Local first &middot; macOS
          </motion.p>
          <motion.h1
            variants={item}
            className="mt-6 font-serif text-[2.9rem] leading-[1.04] font-medium tracking-[-0.015em] text-balance sm:text-6xl lg:text-[4.4rem]"
          >
            Your files, <em className="text-accent">folded</em> into knowledge.
          </motion.h1>
          <motion.p
            variants={item}
            className="mt-7 max-w-[34rem] text-lg leading-relaxed text-muted"
          >
            Origami is a local-first knowledge base with a research agent inside. It reads your
            PDFs, notes, and screenshots, builds a private index on your machine, and answers hard
            questions from what it actually read.
          </motion.p>
          <motion.div variants={item} className="mt-9 flex flex-wrap items-center gap-4">
            <a
              href={repoUrl}
              className="group flex items-center gap-2.5 rounded-md bg-ink px-5 py-3 text-sm font-medium text-paper transition-colors hover:bg-accent-deep"
            >
              <GitHubIcon className="h-4 w-4" />
              View on GitHub
            </a>
            <a
              href="#install"
              className="group flex items-center gap-2 rounded-md border border-line-strong bg-surface px-5 py-3 text-sm font-medium transition-colors hover:border-ink"
            >
              Build from source
              <ArrowDownIcon className="h-3.5 w-3.5 text-subtle transition-transform group-hover:translate-y-0.5" />
            </a>
          </motion.div>
          <motion.p variants={item} className="mt-7 font-mono text-xs tracking-wide text-subtle">
            MIT licensed. Desktop app in development, buildable from source today.
          </motion.p>
        </motion.div>
        <motion.div
          initial={reduced ? false : { opacity: 0, y: 20, rotate: 8 }}
          animate={{ opacity: 1, y: 0, rotate: 5 }}
          transition={reduced ? { duration: 0 } : { duration: 1, delay: 0.35, ease }}
          className="hidden lg:block"
        >
          <FoldDiagram />
        </motion.div>
      </div>
    </section>
  );
}
