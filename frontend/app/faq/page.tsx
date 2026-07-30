import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Reveal } from "@/components/site/reveal";
import { ArrowUpRightIcon } from "@/components/site/icons";
import { docsUrl, repoUrl, roadmapUrl } from "@/lib/site";

export const metadata: Metadata = {
  title: "FAQ",
  description:
    "Plain answers about Origami: what it ingests, what stays local, which models it uses, and where the desktop app is.",
};

const answerLinkClass =
  "font-medium text-accent underline decoration-line-strong underline-offset-4 transition-colors hover:text-accent-deep";

const faqItems: { question: string; answer: ReactNode }[] = [
  {
    question: "What is Origami?",
    answer: (
      <p>
        A local-first knowledge base with a research agent inside. You give it PDFs, Markdown
        notes, and screenshots. It builds a private index on your machine and answers questions by
        actually reading what it retrieved. It is a working tool rather than a finished product,
        and it is under active development. The code is{" "}
        <a href={repoUrl} className={answerLinkClass}>
          open source
        </a>{" "}
        under the MIT license.
      </p>
    ),
  },
  {
    question: "What can it ingest today?",
    answer: (
      <p>
        Three things. PDFs, which go through a contextual retrieval pipeline that annotates every
        chunk with its place in the whole document before embedding. Markdown notes, written and
        edited beside the chat. Screenshots, described by a local vision model so their contents
        become searchable. Connectors for sources like calendars are planned, and the reasoning
        behind each one is recorded in{" "}
        <a href={docsUrl} className={answerLinkClass}>
          the docs
        </a>
        .
      </p>
    ),
  },
  {
    question: "Does my data leave my machine?",
    answer: (
      <p>
        Your corpus is stored and indexed entirely on your machine: files, notes, screenshots,
        embeddings, and the Chroma vector store. Two jobs reach the network, both through the
        Anthropic API with a key you provide. The research agent, which sends the passages it
        retrieved along with your question, and the one-line notes written during ingestion. Vision
        runs locally through Ollama, so screenshots are never uploaded. There is no telemetry and
        no account, and since Origami is still in development you should read the code before
        trusting it with anything sensitive.
      </p>
    ),
  },
  {
    question: "Which models does it use?",
    answer: (
      <p>
        Claude models through the Anthropic API for agent reasoning and ingestion annotations. A
        local vision model, qwen2.5-vl by default, for describing screenshots. Local
        bge-small-en-v1.5 embeddings for the index. The vision and generation models can be pointed
        at anything Ollama serves.
      </p>
    ),
  },
  {
    question: "Where is the desktop app?",
    answer: (
      <p>
        In development. Origami is being rebuilt as a signed, notarized macOS application with the
        Python backend bundled inside. Until it ships, building from source is the way in, and the
        full phase plan is public in{" "}
        <a href={roadmapUrl} className={answerLinkClass}>
          the roadmap
        </a>
        .
      </p>
    ),
  },
  {
    question: "Will there be Windows or Linux builds?",
    answer: (
      <p>
        Not currently planned. Origami is macOS first, and several planned connectors depend on
        macOS system frameworks. A hosted cloud version is not planned either, which is the point.
      </p>
    ),
  },
  {
    question: "Why is there no waitlist or newsletter?",
    answer: (
      <p>
        This site has no backend, no forms, and nothing to submit, by decision rather than by
        accident. A tool whose pitch is that your data stays home should not open by asking for
        your email. Star or watch{" "}
        <a href={repoUrl} className={answerLinkClass}>
          the repository
        </a>{" "}
        for updates.
      </p>
    ),
  },
  {
    question: "How will connectors stay safe?",
    answer: (
      <p>
        Connecting private data to an agent that also reads content other people wrote is a known
        risk, sometimes called the lethal trifecta. Origami sequences provenance and taint tracking
        before any connector ships: content you did not write is marked untrusted, and an agent
        turn that touches untrusted content loses the ability to communicate outward. That ordering
        is deliberate, and it is recorded in the roadmap.
      </p>
    ),
  },
  {
    question: "How can I contribute?",
    answer: (
      <p>
        Read{" "}
        <a href={docsUrl} className={answerLinkClass}>
          the documents in docs/
        </a>{" "}
        first, they are the source of truth for direction. Research claims there are tagged by how
        well they are verified, and the phase ordering is intentional. Issues and pull requests are
        welcome on GitHub.
      </p>
    ),
  },
];

export default function FaqPage() {
  return (
    <main>
      <div className="mx-auto max-w-[760px] px-6 pt-36 pb-24 md:px-8 lg:pt-44 lg:pb-32">
        <Reveal>
          <p className="eyebrow flex items-center gap-3 text-subtle">
            <span className="inline-block h-2 w-2 rotate-45 bg-accent" aria-hidden="true" />
            FAQ
          </p>
          <h1 className="mt-6 font-serif text-4xl font-medium tracking-[-0.01em] text-balance sm:text-5xl">
            Questions, answered plainly.
          </h1>
          <p className="mt-5 text-lg leading-relaxed text-muted">
            The short version of everything the landing page implies. When in doubt, the repository
            is the source of truth.
          </p>
        </Reveal>
        <Reveal delay={0.1} className="mt-14">
          <div className="border-t border-line">
            {faqItems.map((item) => (
              <details key={item.question} className="group border-b border-line">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-6 py-6 text-left">
                  <span className="font-serif text-xl font-medium tracking-tight sm:text-[1.35rem]">
                    {item.question}
                  </span>
                  <svg
                    viewBox="0 0 16 16"
                    fill="none"
                    aria-hidden="true"
                    className="h-4 w-4 shrink-0 text-subtle transition-transform duration-[220ms] [transition-timing-function:var(--ease-crease)] group-open:rotate-45 motion-reduce:transition-none"
                  >
                    <path d="M8 2v12M2 8h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                </summary>
                <div className="pb-7 leading-relaxed text-muted">{item.answer}</div>
              </details>
            ))}
          </div>
        </Reveal>
        <Reveal delay={0.15} className="mt-12">
          <a
            href={repoUrl}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-accent transition-colors hover:text-accent-deep"
          >
            Something unanswered? Open an issue
            <ArrowUpRightIcon className="h-3.5 w-3.5" />
          </a>
        </Reveal>
      </div>
    </main>
  );
}
