import type { Metadata } from "next";
import Link from "next/link";

import { UsageStatus } from "@/features/usage/UsageStatus";

import "./globals.css";

export const metadata: Metadata = {
  title: "PromptForge",
  description: "Structured prompt creation, starting with a solid foundation.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <main className="mx-auto min-h-screen max-w-5xl px-6 py-8 sm:px-10">
          <nav aria-label="Main navigation" className="mb-8 flex justify-end gap-4 text-sm text-cyan-200">
            <Link className="hover:text-white" href="/">Create</Link>
            <Link className="hover:text-white" href="/history">History</Link>
            <Link className="hover:text-white" href="/documents">Documents</Link>
          </nav>
          <UsageStatus />
          {children}
        </main>
      </body>
    </html>
  );
}
