import { Hero } from "@/components/site/hero";
import { ScreenshotFrame } from "@/components/site/screenshot-frame";
import { Capabilities } from "@/components/site/capabilities";
import { Privacy } from "@/components/site/privacy";
import { Install } from "@/components/site/install";

export default function Home() {
  return (
    <main>
      <Hero />
      <ScreenshotFrame />
      <Capabilities />
      <Privacy />
      <Install />
    </main>
  );
}
