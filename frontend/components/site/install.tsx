import { Reveal } from "@/components/site/reveal";
import { ArrowUpRightIcon } from "@/components/site/icons";
import { readmeSetupUrl, roadmapUrl } from "@/lib/site";

const prerequisites = [
  "Ollama, serving locally",
  "Bun 1.3 or newer",
  "Python 3.13 with uv",
  "An Anthropic API key",
];

function Comment({ children }: { children: string }) {
  return <span className="text-panel-muted">{children}</span>;
}

export function Install() {
  return (
    <section id="install" className="scroll-mt-20">
      <div className="mx-auto max-w-[1120px] px-6 py-24 md:px-8 lg:py-32">
        <Reveal className="max-w-[40rem]">
          <p className="eyebrow text-subtle">Install</p>
          <h2 className="mt-5 font-serif text-4xl font-medium tracking-[-0.01em] text-balance sm:text-5xl">
            Build it from source, tonight.
          </h2>
          <p className="mt-5 text-lg leading-relaxed text-muted">
            The desktop app is in active development. Until the signed build ships, Origami runs
            from a clone.
          </p>
        </Reveal>
        <div className="mt-14 grid gap-8 lg:grid-cols-5">
          <Reveal delay={0.05} className="lg:col-span-3">
            <div className="h-full rounded-xl bg-ink-panel p-6 font-mono text-[13px] leading-[1.9] text-panel-text shadow-card sm:p-8 sm:text-sm">
              <pre className="overflow-x-auto whitespace-pre">
                <code>
                  {"git clone https://github.com/GeneralCorn/Origami.git\n"}
                  {"cd Origami\n"}
                  {"\n"}
                  <Comment># pull the local models</Comment>
                  {"\nollama pull qwen2.5-vl:7b\n"}
                  {"ollama pull deepseek-r1:8b\n"}
                  {"\n"}
                  <Comment># backend, in its own terminal</Comment>
                  {"\ncd backend\n"}
                  {"uv sync\n"}
                  {"cp .env.example .env.local  "}
                  <Comment># add your ANTHROPIC_API_KEY</Comment>
                  {"\nuv run uvicorn main:app --reload\n"}
                  {"\n"}
                  <Comment># the interface is mid-move to the desktop shell,</Comment>
                  {"\n"}
                  <Comment># so follow README.md for its current command</Comment>
                </code>
              </pre>
            </div>
          </Reveal>
          <div className="flex flex-col gap-8 lg:col-span-2">
            <Reveal delay={0.12}>
              <div className="rounded-xl border border-line bg-surface p-6 sm:p-8">
                <h3 className="font-serif text-xl font-medium tracking-tight">You will need</h3>
                <ul className="mt-4 flex flex-col gap-3">
                  {prerequisites.map((prerequisite) => (
                    <li key={prerequisite} className="flex items-center gap-3 text-[0.95rem] text-muted">
                      <span className="h-1.5 w-1.5 shrink-0 rotate-45 bg-accent" aria-hidden="true" />
                      {prerequisite}
                    </li>
                  ))}
                </ul>
                <a
                  href={readmeSetupUrl}
                  className="mt-5 inline-flex items-center gap-1.5 text-sm font-medium text-accent transition-colors hover:text-accent-deep"
                >
                  Full setup in the README
                  <ArrowUpRightIcon className="h-3.5 w-3.5" />
                </a>
              </div>
            </Reveal>
            <Reveal delay={0.18}>
              <div className="rounded-xl border border-line bg-surface p-6 sm:p-8">
                <span className="inline-block rounded-full bg-accent-wash px-3 py-1 font-mono text-[11px] tracking-[0.14em] text-accent-deep uppercase">
                  DMG, in development
                </span>
                <h3 className="mt-4 font-serif text-xl font-medium tracking-tight">
                  A signed app is coming
                </h3>
                <p className="mt-3 text-[0.95rem] leading-relaxed text-muted">
                  Origami is being rebuilt as a signed, notarized macOS application with the
                  backend bundled inside, no terminal required. Building from source stays
                  supported either way.
                </p>
                <a
                  href={roadmapUrl}
                  className="mt-5 inline-flex items-center gap-1.5 text-sm font-medium text-accent transition-colors hover:text-accent-deep"
                >
                  Follow the roadmap
                  <ArrowUpRightIcon className="h-3.5 w-3.5" />
                </a>
              </div>
            </Reveal>
          </div>
        </div>
      </div>
    </section>
  );
}
