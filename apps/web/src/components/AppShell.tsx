"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { UsageStatus } from "@/features/usage/UsageStatus";

const items = [
  { href: "/", label: "Create" },
  { href: "/history", label: "History" },
  { href: "/documents", label: "Documents" },
  { href: "/ask", label: "Ask Documents" },
];

export function AppShell({ children }: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();
  const navigation = <nav aria-label="Main navigation" className="flex gap-1 lg:flex-col">
    {items.map((item) => {
      const active = pathname === item.href;
      return <Link aria-current={active ? "page" : undefined} className={`pf-link shrink-0 rounded-lg px-3 py-2 text-sm font-semibold transition ${active ? "bg-[#6F7454] text-[#FBF9F3]" : "text-[#454A35] hover:bg-[#FBF9F3]"}`} href={item.href} key={item.href}>{item.label}</Link>;
    })}
  </nav>;

  return <div className="min-h-screen lg:grid lg:grid-cols-[15rem_minmax(0,1fr)]">
    <aside className="hidden min-h-screen flex-col border-r bg-[#ECE6D8] px-5 py-7 lg:flex">
      <div className="mb-10 px-3"><p className="text-lg font-semibold tracking-tight text-[#272A22]">PromptForge</p><p className="mt-1 text-xs text-[#747568]">Structured prompt workspace</p></div>
      {navigation}
      <div className="mt-auto"><UsageStatus /></div>
    </aside>
    <div className="min-w-0">
      <header className="border-b border-[#D8D1C1] bg-[#ECE6D8] lg:hidden">
        <div className="flex items-center justify-between px-5 py-4"><span className="font-semibold tracking-tight">PromptForge</span><span className="text-xs text-[#747568]">Workspace</span></div>
        <div className="overflow-x-auto px-3 pb-3">{navigation}</div>
      </header>
      <main className="mx-auto min-h-screen max-w-6xl px-5 py-8 sm:px-8 sm:py-10 lg:px-12">{children}</main>
    </div>
  </div>;
}
