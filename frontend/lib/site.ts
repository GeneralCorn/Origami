export const repoUrl = "https://github.com/GeneralCorn/Origami";
export const docsUrl = `${repoUrl}/tree/main/docs`;
export const roadmapUrl = `${repoUrl}/blob/main/docs/ELECTRON_PORT_PLAN.md`;
export const licenseUrl = `${repoUrl}/blob/main/LICENSE`;
export const readmeSetupUrl = `${repoUrl}#setup`;

/**
 * Read the star count once, at build time.
 *
 * The site is a static export with no backend, and it deploys on every push to
 * main, so baking the number in keeps it current without asking the visitor's
 * browser to call GitHub. That matters here beyond tidiness: a page whose whole
 * claim is that nothing phones home should not open a third-party request just
 * to decorate its own header. Returns null when the call fails, and the header
 * then renders without a count rather than showing a zero.
 */
export async function fetchStarCount(): Promise<number | null> {
  try {
    const response = await fetch("https://api.github.com/repos/GeneralCorn/Origami", {
      headers: { Accept: "application/vnd.github+json" },
    });
    if (!response.ok) {
      return null;
    }
    const data = (await response.json()) as { stargazers_count?: number };
    return typeof data.stargazers_count === "number" ? data.stargazers_count : null;
  } catch {
    return null;
  }
}
