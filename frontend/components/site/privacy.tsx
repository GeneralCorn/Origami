import { Reveal } from "@/components/site/reveal";

const guarantees = [
  {
    title: "No account",
    body: "Nothing to sign up for. No login, no waitlist, and no server behind this site to collect either one.",
  },
  {
    title: "No telemetry",
    body: "No analytics, no crash reporting, no phone-home. The code is open, so the claim is checkable rather than taken on faith.",
  },
  {
    title: "A local index",
    body: "Documents, notes, screenshots, and every embedding live in a Chroma store on your disk. Screenshots are described by a vision model that runs on your machine.",
  },
  {
    title: "Your key, your call",
    body: "Agent reasoning currently runs through the Anthropic API using a key you supply. You choose when to use it, and you can read exactly what gets sent.",
  },
];

export function Privacy() {
  return (
    <section className="bg-ink-panel text-panel-text">
      <div className="mx-auto max-w-[1120px] px-6 py-24 md:px-8 lg:py-32">
        <Reveal className="max-w-[42rem]">
          <p className="eyebrow flex items-center gap-3 text-panel-muted">
            <span className="inline-block h-2 w-2 rotate-45 bg-accent" aria-hidden="true" />
            Local first
          </p>
          <h2 className="mt-6 font-serif text-4xl font-medium tracking-[-0.01em] text-balance sm:text-5xl lg:text-[3.4rem] lg:leading-[1.08]">
            Your corpus stays on your machine.
          </h2>
          <p className="mt-6 text-lg leading-relaxed text-panel-muted">
            Your files, notes, screenshots, embeddings, and the index itself never leave your disk.
            Reasoning is the one part that reaches the network, and it does so through your own API
            key.
          </p>
        </Reveal>
        <div className="mt-16 grid gap-10 sm:grid-cols-2 sm:gap-8 lg:grid-cols-4">
          {guarantees.map((guarantee, index) => (
            <Reveal key={guarantee.title} delay={0.08 * index}>
              <div className="border-t border-panel-line pt-6">
                <h3 className="font-serif text-xl font-medium tracking-tight">{guarantee.title}</h3>
                <p className="mt-3 text-[0.95rem] leading-relaxed text-panel-muted">
                  {guarantee.body}
                </p>
              </div>
            </Reveal>
          ))}
        </div>
        <Reveal delay={0.1} className="mt-16">
          <p className="max-w-[44rem] border-l-2 border-accent pl-5 text-[0.95rem] leading-relaxed text-panel-muted">
            What actually goes out, stated plainly: two jobs call the Anthropic API with a key you
            provide. The agent answering a question, which sends the passages it retrieved and the
            note you have open at the time, and the one-line blurbs written during ingestion, which
            send the document being ingested once per chunk. Vision, embeddings, search, and storage
            all run locally. Origami is in active development, so read the code before trusting any
            of this with something sensitive.
          </p>
        </Reveal>
      </div>
    </section>
  );
}
