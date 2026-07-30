import { FoldDiagram } from "@/components/site/fold-diagram";
import { ArrowDownIcon, GitHubIcon } from "@/components/site/icons";
import { repoUrl } from "@/lib/site";

// The entrance is a CSS animation rather than a scripted one so the markup the
// server sends is already visible. The stagger is just an animation-delay per
// child; see the .rise rules in globals.css.
const stagger = (index: number) => ({ animationDelay: `${0.05 + index * 0.11}s` });

export function Hero() {
  return (
    <section className="relative overflow-hidden">
      <div className="mx-auto grid max-w-[1120px] items-center gap-12 px-6 pt-36 pb-10 md:px-8 lg:grid-cols-[1fr_320px] lg:gap-20 lg:pt-44 lg:pb-14">
        <div>
          <p style={stagger(0)} className="rise eyebrow flex items-center gap-3 text-subtle">
            <span className="inline-block h-2 w-2 rotate-45 bg-accent" aria-hidden="true" />
            Open source &middot; Local first &middot; macOS
          </p>
          <h1
            style={stagger(1)}
            className="rise mt-6 font-serif text-[2.9rem] leading-[1.04] font-medium tracking-[-0.015em] text-balance sm:text-6xl lg:text-[4.4rem]"
          >
            Your files, <em className="text-accent">folded</em> into knowledge.
          </h1>
          <p
            style={stagger(2)}
            className="rise mt-7 max-w-[34rem] text-lg leading-relaxed text-muted"
          >
            Origami is a local-first knowledge base with a research agent inside. It reads your
            PDFs, notes, and screenshots, builds a private index on your machine, and answers hard
            questions from what it actually read.
          </p>
          <div style={stagger(3)} className="rise mt-9 flex flex-wrap items-center gap-4">
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
          </div>
          <p style={stagger(4)} className="rise mt-7 font-mono text-xs tracking-wide text-subtle">
            MIT licensed. Desktop app in development, buildable from source today.
          </p>
        </div>
        {/* Rotation sits on the outer element because .rise animates transform
            and would otherwise overwrite it. */}
        <div className="hidden rotate-[5deg] lg:block">
          <div style={{ animationDelay: "0.35s" }} className="rise">
            <FoldDiagram />
          </div>
        </div>
      </div>
    </section>
  );
}
