"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api, errorMessage, RANK, STATUS_LABEL, timeAgo, type Dashboard, type Ticket, type TicketStatus } from "@/lib/api";
import { useWorkspace, wsBase } from "@/lib/useWorkspace";

const SORTS: [string, string][] = [["updated_at", "Last updated"], ["created_at", "Created"], ["priority", "Priority"], ["number", "Number"]];
const PRIORITY_STYLE: Record<string, string> = {
  urgent: "bg-red-100 text-red-800", high: "bg-orange-100 text-orange-800", normal: "bg-slate-100 text-slate-700", low: "bg-slate-50 text-slate-500",
};

export default function TicketsPage({ params }: { params: Promise<{ workspaceId: string }> }) {
  const { workspaceId } = use(params);
  const { workspace, error, setError, nameOf } = useWorkspace(workspaceId, true);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState("updated_at");
  const [order, setOrder] = useState("desc");
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ subject: "", requester_name: "", requester_email: "", priority: "normal", description: "" });
  const base = wsBase(workspaceId);

  const load = useCallback(() => {
    const qs = new URLSearchParams({ sort, order });
    if (q) qs.set("q", q);
    if (status) qs.set("status", status);
    api<Ticket[]>(`${base}/tickets?${qs}`).then(setTickets).catch((e) => setError(errorMessage(e)));
    api<Dashboard>(`${base}/dashboard`).then(setDash).catch(() => {});
  }, [base, q, status, sort, order, setError]);
  useEffect(load, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api(`${base}/tickets`, { method: "POST", json: form });
      setForm({ subject: "", requester_name: "", requester_email: "", priority: "normal", description: "" });
      setCreating(false);
      load();
    } catch (err) { setError(errorMessage(err)); }
  }

  const canCreate = workspace && RANK[workspace.role] >= RANK.member;
  return (
    <Shell workspace={workspace}>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1>Tickets</h1>
        {canCreate && <button className="btn" onClick={() => setCreating((v) => !v)}>New ticket</button>}
      </div>
      {error && <p className="error mb-4" role="alert">{error}</p>}
      {dash && (
        <div className="mb-6 grid gap-4 sm:grid-cols-4">
          <Stat label="Open" value={(dash.by_status.open ?? 0) + (dash.by_status.pending ?? 0)} />
          <Stat label="Assigned to me" value={dash.mine_open} />
          <Stat label="Unassigned" value={dash.unassigned_open} />
          <Stat label="Urgent" value={dash.urgent_open} />
        </div>
      )}
      {creating && (
        <form onSubmit={create} className="card mb-6 grid gap-3 sm:grid-cols-2">
          <input className="input sm:col-span-2" required maxLength={200} placeholder="Subject" value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} aria-label="Subject" />
          <input className="input" required maxLength={120} placeholder="Customer name" value={form.requester_name} onChange={(e) => setForm({ ...form, requester_name: e.target.value })} aria-label="Customer name" />
          <input className="input" required type="email" maxLength={254} placeholder="Customer email" value={form.requester_email} onChange={(e) => setForm({ ...form, requester_email: e.target.value })} aria-label="Customer email" />
          <textarea className="input sm:col-span-2" rows={3} maxLength={10000} placeholder="Details" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} aria-label="Details" />
          <select className="input" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} aria-label="Priority">
            {["low", "normal", "high", "urgent"].map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <button className="btn justify-center">Create ticket</button>
        </form>
      )}
      <div className="mb-4 flex flex-wrap gap-3">
        <input className="input w-64" placeholder="Search subject or email" maxLength={100} value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search tickets" />
        <select className="input w-auto" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
          <option value="">All statuses</option>
          {(Object.keys(STATUS_LABEL) as TicketStatus[]).map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
        </select>
        <select className="input w-auto" value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort by">
          {SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <select className="input w-auto" value={order} onChange={(e) => setOrder(e.target.value)} aria-label="Order">
          <option value="desc">Newest first</option><option value="asc">Oldest first</option>
        </select>
      </div>
      <div className="card overflow-x-auto p-0">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-slate-500">
            <tr><th className="px-4 py-2">Ticket</th><th className="px-4 py-2">Subject</th><th className="px-4 py-2">Customer</th>
              <th className="px-4 py-2">Priority</th><th className="px-4 py-2">Status</th><th className="px-4 py-2">Assignee</th><th className="px-4 py-2">Updated</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {tickets.map((t) => (
              <tr key={t.id} className="hover:bg-slate-50">
                <td className="px-4 py-2 font-mono"><Link className="text-sky-700 hover:underline" href={`/workspaces/${encodeURIComponent(workspaceId)}/tickets/${encodeURIComponent(t.id)}`}>{t.ref}</Link></td>
                <td className="px-4 py-2">{t.subject}</td>
                <td className="px-4 py-2 text-slate-600">{t.requester_name}</td>
                <td className="px-4 py-2"><span className={`rounded px-2 py-0.5 text-xs ${PRIORITY_STYLE[t.priority]}`}>{t.priority}</span></td>
                <td className="px-4 py-2">{STATUS_LABEL[t.status]}</td>
                <td className="px-4 py-2 text-slate-600">{nameOf(t.assignee_id)}</td>
                <td className="px-4 py-2 text-slate-500">{timeAgo(t.updated_at)}</td>
              </tr>
            ))}
            {tickets.length === 0 && <tr><td colSpan={7} className="px-4 py-6 text-center text-slate-500">No tickets.</td></tr>}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return <div className="card p-4"><div className="text-2xl font-semibold">{value}</div><div className="text-xs text-slate-500">{label}</div></div>;
}
