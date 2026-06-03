import "./globals.css";
import type { Metadata } from "next";
import { Bricolage_Grotesque, Hanken_Grotesk, IBM_Plex_Mono } from "next/font/google";
import Nav from "@/components/Nav";

const display = Bricolage_Grotesque({ subsets: ["latin"], variable: "--f-display", display: "swap" });
const body = Hanken_Grotesk({ subsets: ["latin"], variable: "--f-body", display: "swap" });
const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--f-mono", display: "swap" });

export const metadata: Metadata = {
  title: "gitly — git quality for the AI era",
  description: "Commit cleanly, ship reviewable PRs, and trace who really wrote the code.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable} ${mono.variable}`}>
      <body>
        <div className="shell">
          <Nav />
          <main className="wrap">{children}</main>
          <footer className="foot">
            <div className="wrap">
              <span>gitly · git quality for the AI-authorship era</span>
              <span>author → structure → review · trace</span>
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}
