import { Reveal } from "@/components/site/reveal";

const stations = [
  {
    group: "On your Mac",
    note: "Local APIs, so nothing leaves the machine. Each needs the signed build first, because macOS ties a permission grant to a stable signing identity.",
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
    note: "The seams for both already exist in the code, which is what separates these from wishes.",
    items: [
      {
        name: "MCP, both directions",
        status: "Planned",
        detail: "read from servers, expose your corpus read-only",
      },
      { name: "Local text generation", status: "Undecided", detail: "the model routing seam exists" },
    ],
  },
  {
    group: "Other platforms",
    note: "The shell is Electron, so Windows and Linux are reachable in principle. Nothing has been built or tested for either, and packaging today produces an arm64 macOS app only.",
    items: [
      { name: "Windows", status: "Not started", detail: "window chrome written, never run" },
      { name: "Linux", status: "Not started", detail: "no packaging target yet" },
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

        {/* The spine is a crease, drawn with the same dashed line as the fold
            diagram in the hero, running the length of the timeline. */}
        <div className="relative mt-20 pl-9 sm:pl-16">
          <Reveal
            variant="crease"
            decorative
            className="absolute top-4 bottom-4 left-[5px] w-px border-l border-dashed border-line-strong sm:left-[7px]"
          />

          {/* No stagger on the stations. A stagger only reads when the staggered
              items are co-visible, and these are hundreds of pixels apart, each
              armed by its own observer, so the delay was never perceived. */}
          {stations.map((station, index) => (
            <Reveal key={station.group}>
              <div className={index === 0 ? "relative" : "relative mt-16"}>
                <span
                  aria-hidden="true"
                  className="absolute top-[9px] -left-9 h-[11px] w-[11px] rotate-45 bg-accent sm:-left-16 sm:ml-0.5"
                />
                <h3 className="font-serif text-2xl font-medium tracking-tight">{station.group}</h3>
                <p className="mt-3 max-w-[36rem] text-sm leading-relaxed text-subtle">
                  {station.note}
                </p>

                <ul className="mt-7">
                  {station.items.map((item) => (
                    <li
                      key={item.name}
                      className="relative grid grid-cols-[1fr] gap-x-6 gap-y-1 border-b border-line py-4 last:border-b-0 sm:grid-cols-[6.5rem_minmax(0,14rem)_1fr] sm:items-baseline"
                    >
                      {/* Tick joining the entry back to the crease. */}
                      <span
                        aria-hidden="true"
                        className="absolute top-[1.7rem] -left-16 hidden w-9 border-t border-dashed border-line-strong sm:block"
                      />
                      <span className="font-mono text-[11px] tracking-[0.16em] text-accent uppercase">
                        {item.status}
                      </span>
                      <span className="text-lg leading-snug">{item.name}</span>
                      <span className="text-sm text-subtle">{item.detail}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </Reveal>
          ))}

          {/* Terminus. Hollow, because this is where the line stops rather than
              another thing being planned. */}
          <Reveal>
            <div className="relative mt-16">
              <span
                aria-hidden="true"
                className="absolute top-[9px] -left-9 h-[11px] w-[11px] rotate-45 border border-line-strong bg-paper sm:-left-16 sm:ml-0.5"
              />
              <h3 className="font-serif text-2xl font-medium tracking-tight text-muted">
                And where the line stops
              </h3>
              <p className="mt-3 max-w-[38rem] leading-relaxed text-muted">
                Google Photos cannot be read through its API any more, because the library scopes
                were removed, so the only honest route is importing a Takeout archive you asked for.
                Automating a personal Discord account is a bannable offence, and WhatsApp has no
                sanctioned path to personal messages at all. Those three are not waiting on a
                roadmap, they are ruled out, and a tool that claims otherwise is either wrong or
                about to get your account closed.
              </p>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
