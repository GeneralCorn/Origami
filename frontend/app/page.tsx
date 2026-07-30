import { Hero } from "@/components/site/hero";
import { ScreenshotFrame } from "@/components/site/screenshot-frame";
import { Capabilities } from "@/components/site/capabilities";
import { Roadmap } from "@/components/site/roadmap";
import { Privacy } from "@/components/site/privacy";
import { Install } from "@/components/site/install";

export default function Home() {
  return (
    <main>
      <Hero />
      <ScreenshotFrame />
      <Capabilities />
      <Roadmap />
      <Privacy />
      <Install />
    </main>
  );
}
