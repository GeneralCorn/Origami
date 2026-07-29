import { Reveal } from "@/components/site/reveal";

const capabilities = [
  {
    number: "01",
    title: "Ingestion that reads first",
    body: "Every PDF chunk is prefaced with a short note situating it in the whole document before it is embedded, following Anthropic’s contextual retrieval method. Fragments stop losing their context.",
    className: "md:border-r md:border-b border-b border-line",
  },
  {
    number: "02",
    title: "Screenshots become searchable",
    body: "A vision model running locally through Ollama describes every screenshot you capture, and the description joins the index. The chart you half remember is one question away.",
    className: "md:border-b border-b border-line",
  },
  {
    number: "03",
    title: "An agent that does the reading",
    body: "The research agent plans, retrieves, reviews its own findings, and loops until it has enough to answer. Its reasoning stays visible while it works.",
    className: "md:border-r border-b md:border-b-0 border-line",
  },
  {
    number: "04",
    title: "An index on your own disk",
    body: "Chunks are embedded by a model running on your machine and stored in a local Chroma index. Building and searching that index needs no network at all.",
    className: "",
  },
];

export function Capabilities() {
  return (
    <section id="capabilities" className="scroll-mt-20">
      <div className="mx-auto max-w-[1120px] px-6 py-24 md:px-8 lg:py-32">
        <Reveal className="max-w-[40rem]">
          <p className="eyebrow text-subtle">What it does</p>
          <h2 className="mt-5 font-serif text-4xl font-medium tracking-[-0.01em] text-balance sm:text-5xl">
            One index, four ways in.
          </h2>
          <p className="mt-5 text-lg leading-relaxed text-muted">
            Everything you feed Origami lands in one local index, and every answer the agent gives
            is grounded in what it retrieved from that index.
          </p>
        </Reveal>
        <Reveal delay={0.1} className="mt-16">
          <div className="grid border-y border-line md:grid-cols-2">
            {capabilities.map((capability) => (
              <article key={capability.number} className={`${capability.className} p-8 md:p-10`}>
                <span className="font-mono text-xs tracking-[0.18em] text-accent">
                  {capability.number}
                </span>
                <h3 className="mt-4 font-serif text-2xl font-medium tracking-tight">
                  {capability.title}
                </h3>
                <p className="mt-3 leading-relaxed text-muted">{capability.body}</p>
              </article>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}
