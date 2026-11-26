"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api, errorMessage, type Workspace } from "@/lib/api";

export default function WorkspacesPage() {
  const [items, setItems] = useState<Workspace[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Workspace[]>("/api/v1/workspaces").then(setItems).catch((e) => setError(errorMessage(e)));
  }, []);

  return (
    <Shell>
      <h1 className="mb-6">Your workspaces</h1>
      {error && <p className="error">{error}</p>}
      {items?.length === 0 && <p className="text-slate-600">You're not a member of any workspace yet. Ask a workspace manager for an invitation.</p>}
      <ul className="grid gap-4 sm:grid-cols-2">
        {items?.map((w) => (
          <li key={w.id}>
            <Link href={`/workspaces/${encodeURIComponent(w.id)}`} className="card block h-full hover:border-indigo-300">
              <div className="flex items-start justify-between gap-2">
                <div className="font-medium">{w.name}</div>
                <span className="rounded bg-slate-100 px-2 py-0.5 text-xs capitalize text-slate-600">{w.role}</span>
              </div>
              {w.description && <p className="mt-2 text-sm text-slate-600">{w.description}</p>}
            </Link>
          </li>
        ))}
      </ul>
    </Shell>
  );
}
