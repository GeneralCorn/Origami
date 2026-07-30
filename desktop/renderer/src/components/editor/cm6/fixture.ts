export const SPIKE_MEDIA = [
  "/spike-media/wide-banner.png",
  "/spike-media/screenshot-a.png",
  "/spike-media/tall-portrait.png",
  "/spike-media/panorama.png",
  "/spike-media/square.png",
  "/spike-media/very-tall.png",
  "/spike-media/screenshot-b.png",
  "/spike-media/thumb.png",
] as const;

const PROSE = [
  "The question this spike exists to answer is whether a text editor can host block media without the document stopping being text.",
  "Everything below the title is ordinary markdown. Nothing in the extension writes to the document; the widgets are a view-layer overlay only.",
  "A line holding nothing but an image link is replaced by a block widget. Put the caret on that line and the raw source comes back.",
  "Paragraphs above and below a widget must stay editable without disturbing it, and undo has to cross the boundary cleanly.",
  "Variable image heights are the interesting case, because the editor estimates the height of anything it has not drawn yet.",
];

/**
 * A markdown note with `count` images spaced between paragraphs.
 *
 * Aspect ratios are deliberately mixed so the rendered heights range from
 * roughly 160px to roughly 1300px, which is what makes the height-map
 * behaviour observable rather than theoretical.
 */
export function buildFixture(count: number, paragraphsPerImage = 3): string {
  const lines: string[] = ["# CodeMirror 6 mixed-media spike", ""];
  for (let i = 0; i < count; i += 1) {
    for (let p = 0; p < paragraphsPerImage; p += 1) {
      const n = i * paragraphsPerImage + p;
      lines.push(`${n + 1}. ${PROSE[n % PROSE.length]}`, "");
    }
    const src = SPIKE_MEDIA[i % SPIKE_MEDIA.length];
    const name = src.split("/").pop()?.replace(".png", "") ?? "image";
    lines.push(`![${name} ${i + 1}](${src})`, "");
  }
  lines.push("End of fixture.", "");
  return lines.join("\n");
}

/** A long plain-prose document used to measure whole-document rebuild cost. */
export function buildLargeFixture(lineCount: number, imageEvery: number): string {
  const lines: string[] = ["# Large document rebuild cost", ""];
  for (let i = 0; i < lineCount; i += 1) {
    if (imageEvery > 0 && i % imageEvery === 0) {
      const src = SPIKE_MEDIA[(i / imageEvery) % SPIKE_MEDIA.length];
      lines.push(`![row ${i}](${src})`, "");
    } else {
      lines.push(`Line ${i}: ${PROSE[i % PROSE.length]}`, "");
    }
  }
  return lines.join("\n");
}
