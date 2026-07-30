import Link from "next/link";
import { FoldMark } from "@/components/site/logo";
import { GitHubIcon } from "@/components/site/icons";
import { repoUrl } from "@/lib/site";

export function SiteHeader() {
  return (
    <header className="fixed inset-x-0 top-0 z-40 border-b border-line bg-paper/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-[1120px] items-center justify-between px-6 md:px-8">
        <Link href="/" className="flex items-center gap-2.5">
          <FoldMark className="h-6 w-6 text-ink" />
          <span className="font-serif text-[1.4rem] leading-none tracking-tight">Origami</span>
        </Link>
        <nav className="flex items-center gap-5 sm:gap-7">
          <Link
            href="/#capabilities"
            className="hidden text-sm text-muted transition-colors hover:text-ink md:block"
          >
            Capabilities
          </Link>
          <Link
            href="/#roadmap"
            className="hidden text-sm text-muted transition-colors hover:text-ink md:block"
          >
            Roadmap
          </Link>
          <Link
            href="/#install"
            className="hidden text-sm text-muted transition-colors hover:text-ink md:block"
          >
            Install
          </Link>
          <Link href="/faq" className="text-sm text-muted transition-colors hover:text-ink">
            FAQ
          </Link>
          <a
            href={repoUrl}
            className="flex items-center gap-2 rounded-md border border-line-strong bg-surface px-3 py-1.5 text-sm font-medium transition-colors hover:border-ink"
          >
            <GitHubIcon className="h-4 w-4" />
            GitHub
          </a>
        </nav>
      </div>
    </header>
  );
}
