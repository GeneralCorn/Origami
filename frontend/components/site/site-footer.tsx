import Link from "next/link";
import { FoldMark } from "@/components/site/logo";
import { docsUrl, licenseUrl, repoUrl, roadmapUrl } from "@/lib/site";

const linkClass = "link-rule text-sm text-muted hover:text-ink";

export function SiteFooter() {
  return (
    <footer className="border-t border-line bg-paper-deep/60">
      <div className="mx-auto max-w-[1120px] px-6 py-14 md:px-8">
        <div className="flex flex-col justify-between gap-10 sm:flex-row">
          <div className="max-w-xs">
            <div className="flex items-center gap-2.5">
              <FoldMark className="h-6 w-6 text-ink" />
              <span className="font-serif text-xl leading-none tracking-tight">Origami</span>
            </div>
            <p className="mt-4 text-sm leading-relaxed text-muted">
              A local-first AI knowledge base, open source and MIT licensed. In active development.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-10 sm:gap-16">
            <div className="flex flex-col gap-3">
              <span className="eyebrow text-subtle">Project</span>
              <a href={repoUrl} className={linkClass}>
                GitHub
              </a>
              <a href={roadmapUrl} className={linkClass}>
                Roadmap
              </a>
              <a href={docsUrl} className={linkClass}>
                Docs
              </a>
              <a href={licenseUrl} className={linkClass}>
                License
              </a>
            </div>
            <div className="flex flex-col gap-3">
              <span className="eyebrow text-subtle">Site</span>
              <Link href="/#capabilities" className={linkClass}>
                Capabilities
              </Link>
              <Link href="/#install" className={linkClass}>
                Install
              </Link>
              <Link href="/faq" className={linkClass}>
                FAQ
              </Link>
            </div>
          </div>
        </div>
        <div className="mt-12 flex flex-col gap-2 border-t border-line pt-6 sm:flex-row sm:items-center sm:justify-between">
          <span className="font-mono text-xs text-subtle">MIT licensed, 2026</span>
          <span className="font-mono text-xs text-subtle">No account. No telemetry. No forms.</span>
        </div>
      </div>
    </footer>
  );
}
