"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { api, type Session, type Workspace } from "@/lib/api";

const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME ?? "HelpDesk Pro";
const SessionCtx = createContext<Session | null>(null);
export const useSession = () => useContext(SessionCtx);

export default function Shell({ children, workspace }: { children: React.ReactNode; workspace?: Workspace | null }) {
  const [session, setSession] = useState<Session | null>(null);
  const pathname = usePathname();

  useEffect(() => {
    api<Session>("/api/v1/auth/me").then(setSession).catch(() => {});
  }, []);

  async function logout() {
    try {
      await api("/api/v1/auth/logout", { method: "POST" });
    } finally {
      window.location.assign("/login");
    }
  }

  const base = workspace ? `/workspaces/${encodeURIComponent(workspace.id)}` : null;
  const tabs = base
    ? [
        { href: base, label: "Tickets" },
        { href: `${base}/members`, label: "Team" },
      ]
    : [];

  return (
    <SessionCtx.Provider value={session}>
      <div className="min-h-screen">
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
            <nav className="flex items-center gap-1">
              <Link href="/workspaces" className="mr-4 flex items-center gap-2 font-semibold">
                <span className="inline-block h-6 w-6 rounded bg-sky-600 text-center text-sm leading-6 text-white">H</span>
                {APP_NAME}
              </Link>
              {workspace && <span className="text-sm text-slate-500">/ {workspace.name}</span>}
            </nav>
            <div className="flex items-center gap-2 text-sm text-slate-600">
              {session?.user.is_platform_admin && <Link href="/admin" className="btn-quiet">Security alerts</Link>}
              {session && <span className="hidden sm:inline">{session.user.display_name}</span>}
              <button className="btn-quiet" onClick={logout}>Sign out</button>
            </div>
          </div>
          {tabs.length > 0 && (
            <div className="mx-auto flex max-w-6xl gap-1 px-6">
              {tabs.map((t) => {
                const active = t.href === base ? !pathname.endsWith("/members") : pathname.startsWith(t.href);
                return (
                  <Link key={t.href} href={t.href}
                        className={`border-b-2 px-3 py-2 text-sm ${active ? "border-sky-600 font-medium text-slate-900" : "border-transparent text-slate-500 hover:text-slate-800"}`}>
                    {t.label}
                  </Link>
                );
              })}
            </div>
          )}
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
      </div>
    </SessionCtx.Provider>
  );
}
