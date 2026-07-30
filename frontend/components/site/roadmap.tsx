import { Reveal } from "@/components/site/reveal";

const planned = [
  {
    group: "On your Mac",
    note: "Local APIs, so nothing leaves the machine. Each one needs the signed build first, because macOS ties a permission grant to a stable signing identity.",
    items: [
      { name: "Calendar and Reminders", status: "Planned", detail: "EventKit" },
      { name: "Photos", status: "Planned", detail: "PhotoKit" },
      { name: "iMessage", status: "Opt-in", detail: "Full Disk Access, off by default" },
    ],
  },
  {
    group: "Services you already use",
    note: "Opt-in, one at a time, using credentials you create. Origami ships no shared app that everyone authenticates through.",
    items: [
      { name: "Slack", status: "Opt-in", detail: "your own app manifest" },
      { name: "Google Calendar", status: "Opt-in", detail: "your own OAuth client" },
      { name: "Todoist", status: "Opt-in", detail: "personal API token" },
    ],
  },
  {
    group: "Tools and models",
    items: [
      { name: "MCP, both directions", status: "Planned", detail: "read from servers, and expose your corpus read-only" },
      { name: "Local text generation", status: "Undecided", detail: "the model routing seam exists" },
    ],
  },
];

export function Roadmap() {
  return (
    <section id="roadmap" className="scroll-mt-20 border-t border-line">
      <div className="mx-auto max-w-[1120px] px-6 py-24 md:px-8 lg:py-32">
        <Reveal className="max-w-[42rem]">
          <p className="eyebrow text-subtle">What comes next</p>
          <h2 className="mt-5 font-serif text-4xl font-medium tracking-[-0.01em] text-balance sm:text-5xl">
            Files are the floor, not the ceiling.
          </h2>
          <p className="mt-5 text-lg leading-relaxed text-muted">
            Documents, notes, and screenshots are the base. The rest of what you know lives in
            calendars, photo libraries, and message threads, and the point of one local index is
            that it can hold all of it. Nothing below has shipped, and everything below is opt-in,
            one source at a time.
          </p>
        </Reveal>

        <div className="mt-16 space-y-12">
          {planned.map((section, index) => (
            <Reveal key={section.group} delay={0.05 * index}>
              <div className="grid gap-6 border-t border-line pt-8 md:grid-cols-[16rem_1fr] md:gap-12">
                <div>
                  <h3 className="font-serif text-2xl font-medium tracking-tight">{section.group}</h3>
                  {section.note ? (
                    <p className="mt-3 text-sm leading-relaxed text-subtle">{section.note}</p>
                  ) : null}
                </div>
                <ul className="space-y-4">
                  {section.items.map((item) => (
                    <li
                      key={item.name}
                      className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b border-line pb-4 last:border-b-0"
                    >
                      <span className="font-mono text-[11px] tracking-[0.16em] text-accent uppercase">
                        {item.status}
                      </span>
                      <span className="text-lg">{item.name}</span>
                      <span className="text-sm text-subtle">{item.detail}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </Reveal>
          ))}
        </div>

        <Reveal delay={0.1} className="mt-16">
          <div className="max-w-[42rem] border-l-2 border-line-strong pl-6">
            <p className="eyebrow text-subtle">And what will not ship</p>
            <p className="mt-4 leading-relaxed text-muted">
              Google Photos cannot be read through its API any more, because the library scopes were
              removed, so the only honest route is importing a Takeout archive you asked for.
              Automating a personal Discord account is a bannable offence, and WhatsApp has no
              sanctioned path to personal messages at all. Those three are not on a roadmap
              somewhere, they are ruled out, and a tool that claims otherwise is either wrong or
              about to get your account closed.
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
