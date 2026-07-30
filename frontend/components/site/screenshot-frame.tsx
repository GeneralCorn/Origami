import Image from "next/image";
import { Reveal } from "@/components/site/reveal";
import screenshotLight from "@/assets/screenshot-light.png";

export function ScreenshotFrame() {
  return (
    <section className="relative">
      <div
        aria-hidden="true"
        className="absolute inset-x-0 bottom-0 h-1/2 border-y border-line bg-paper-deep/70"
      />
      <div className="relative mx-auto max-w-[1120px] px-6 md:px-8">
        <Reveal className="tip">
          <figure>
            <div
              data-plate
              className="rounded-xl border border-line-strong bg-surface p-1.5 sm:p-2"
            >
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
      </div>
    </section>
  );
}
