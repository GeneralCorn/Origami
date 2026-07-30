import type { Metadata } from "next";
import { Fragment_Mono, Instrument_Sans, Newsreader } from "next/font/google";
import { SiteHeader } from "@/components/site/site-header";
import { SiteFooter } from "@/components/site/site-footer";
import "./globals.css";

const newsreader = Newsreader({
  variable: "--font-newsreader",
  subsets: ["latin"],
  style: ["normal", "italic"],
  axes: ["opsz"],
  display: "swap",
});

const instrumentSans = Instrument_Sans({
  variable: "--font-instrument-sans",
  subsets: ["latin"],
  display: "swap",
});

const fragmentMono = Fragment_Mono({
  variable: "--font-fragment-mono",
  subsets: ["latin"],
  weight: "400",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL("https://generalcorn.github.io"),
  title: {
    default: "Origami, a local-first AI knowledge base",
    template: "%s · Origami",
  },
  description:
    "Open source knowledge base that ingests PDFs, notes, and screenshots, indexes them on your machine, and answers hard questions with a research agent.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${newsreader.variable} ${instrumentSans.variable} ${fragmentMono.variable}`}
    >
      <body className="grain">
        <SiteHeader />
        {children}
        <SiteFooter />
      </body>
    </html>
  );
}
