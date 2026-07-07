"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  APP_CONFIG,
  getApplicationInitial,
} from "@/lib/app_config";

type SidebarProps = {
  onNewAnalysis: () => void;
};

const navItems = [
  { label: "Dashboard", href: "/", action: null },
  { label: "New Analysis", href: null, action: "new" as const },
  { label: "Active Analyses", href: "/", action: null },
  { label: "History", href: "/", action: null },
  { label: "Settings", href: "/", action: null },
];

export default function Sidebar({ onNewAnalysis }: SidebarProps) {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-full flex-col border-r border-hap-border bg-hap-panel lg:w-56 xl:w-60">
      <div className="border-b border-hap-border px-5 py-5">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded bg-hap-orange text-sm font-bold text-black">
            {getApplicationInitial()}
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-wider text-hap-orange">
              {APP_CONFIG.applicationName}
            </h1>
            <p className="text-[10px] uppercase tracking-widest text-hap-muted">
              {APP_CONFIG.fullName}
            </p>
          </div>
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-0.5 p-3">
        {navItems.map((item) => {
          const isActive =
            item.label === "Dashboard"
              ? pathname === "/"
              : pathname.startsWith("/analysis");

          const className = `rounded px-3 py-2.5 text-left text-sm transition-colors ${
            isActive && item.label === "Dashboard"
              ? "border-l-2 border-hap-orange bg-hap-panel-elevated font-medium text-hap-orange"
              : "border-l-2 border-transparent text-hap-muted hover:bg-hap-panel-elevated hover:text-foreground"
          }`;

          if (item.action === "new") {
            return (
              <button key={item.label} onClick={onNewAnalysis} className={className}>
                {item.label}
              </button>
            );
          }

          return (
            <Link key={item.label} href={item.href!} className={className}>
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-hap-border px-5 py-3">
        <div className="flex items-center gap-2 text-xs text-hap-muted">
          <span className="h-1.5 w-1.5 rounded-full bg-hap-success" />
          Systems operational
        </div>
      </div>
    </aside>
  );
}
