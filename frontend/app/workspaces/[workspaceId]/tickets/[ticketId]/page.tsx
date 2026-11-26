"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api, errorMessage, fmtDate, RANK, STATUS_LABEL, timeAgo, type Note, type Ticket, type TicketStatus } from "@/lib/api";
import { useWorkspace, wsBase } from "@/lib/useWorkspace";

export default function TicketPage({ params }: { params: Promise<{ workspaceId: string; ticketId: string }> }) {
  const { workspaceId, ticketId } = use(params);
  const { workspace, members, error, setError } = useWorkspace(workspaceId, true);
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [notes, setNotes] = useState<Note[]>([]);
  const [note, setNote] = useState("");
  const url = `${wsBase(workspaceId)}/tickets/${encodeURIComponent(ticketId)}`;

  const load = useCallback(() => {
    api<Ticket>(url).then(setTicket).catch((e) => setError(errorMessage(e)));
    api<Note[]>(`${url}/notes`).then(setNotes).catch(() => {});
  }, [url, setError]);
  useEffect(load, [load]);

  async function patch(changes: Partial<Ticket>) {
    try { setTicket(await api<Ticket>(url, { method: "PATCH", json: changes })); }
    catch (e) { setError(errorMessage(e)); }
  }

  async function addNote(e: React.FormEvent) {
    e.preventDefault();
    try { await api(`${url}/notes`, { method: "POST", json: { body: note } }); setNote(""); load(); }
    catch (err) { setError(errorMessage(err)); }
  }

  const role = workspace?.role;
  const canEdit = !!role && RANK[role] >= RANK.member;
  const statuses = (Object.keys(STATUS_LABEL) as TicketStatus[]).filter((s) => s !== "closed" || (role && RANK[role] >= RANK.manager));

  return (
    <Shell workspace={workspace}>
      <Link href={`/workspaces/${encodeURIComponent(workspaceId)}`} className="text-sm text-sky-700 hover:underline">← All tickets</Link>
      {error && <p className="error my-4" role="alert">{error}</p>}
      {ticket && (
        <div className="mt-4 grid gap-6 lg:grid-cols-3">
          <section className="card space-y-4 lg:col-span-2">
            <div>
              <div className="font-mono text-sm text-slate-500">{ticket.ref} · via {ticket.channel}</div>
              <h1>{ticket.subject}</h1>
              <p className="text-sm text-slate-500">From {ticket.requester_name} &lt;{ticket.requester_email}&gt; · {fmtDate(ticket.created_at)}</p>
            </div>
            {ticket.description && <p className="whitespace-pre-wrap text-sm text-slate-800">{ticket.description}</p>}
            <div>
              <h2 className="mb-2">Internal notes</h2>
              <ul className="space-y-3">
                {notes.map((n) => (
                  <li key={n.id} className="rounded-md bg-amber-50 p-3 text-sm">
                    <div className="mb-1 text-xs text-slate-500">{n.author_name ?? "Former agent"} · {timeAgo(n.created_at)}</div>
                    <p className="whitespace-pre-wrap">{n.body}</p>
                  </li>
                ))}
                {notes.length === 0 && <li className="text-sm text-slate-500">No notes yet.</li>}
              </ul>
              {canEdit && (
                <form onSubmit={addNote} className="mt-3 space-y-2">
                  <textarea className="input" rows={3} required maxLength={10000} placeholder="Add an internal note" value={note} onChange={(e) => setNote(e.target.value)} aria-label="Note" />
                  <button className="btn">Add note</button>
                </form>
              )}
            </div>
          </section>
          <section className="card space-y-3 text-sm">
            <label className="block"><span className="label">Status</span>
              <select className="input" disabled={!canEdit} value={ticket.status} onChange={(e) => patch({ status: e.target.value as TicketStatus })}>
                {statuses.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
              </select></label>
            <label className="block"><span className="label">Priority</span>
              <select className="input" disabled={!canEdit} value={ticket.priority} onChange={(e) => patch({ priority: e.target.value as Ticket["priority"] })}>
                {["low", "normal", "high", "urgent"].map((p) => <option key={p} value={p}>{p}</option>)}
              </select></label>
            <label className="block"><span className="label">Assignee</span>
              <select className="input" disabled={!canEdit} value={ticket.assignee_id ?? ""} onChange={(e) => patch({ assignee_id: e.target.value || null })}>
                <option value="">Unassigned</option>
                {members.filter((m) => m.role !== "viewer").map((m) => <option key={m.user_id} value={m.user_id}>{m.display_name}</option>)}
              </select></label>
          </section>
        </div>
      )}
    </Shell>
  );
}
