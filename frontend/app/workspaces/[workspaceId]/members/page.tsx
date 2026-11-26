"use client";

import { use, useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { api, errorMessage, fmtDate, RANK, type Invitation, type Member, type Role } from "@/lib/api";
import { useMe, wsBase } from "@/lib/useWorkspace";
import { useWorkspace } from "@/lib/useWorkspace";

const ROLES: Role[] = ["viewer", "member", "manager", "owner"];

export default function MembersPage({ params }: { params: Promise<{ workspaceId: string }> }) {
  const { workspaceId } = use(params);
  const { workspace, error, setError } = useWorkspace(workspaceId);
  const me = useMe();
  const [members, setMembers] = useState<Member[]>([]);
  const [invites, setInvites] = useState<Invitation[]>([]);
  const [email, setEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<Role>("member");
  const [lastLink, setLastLink] = useState<string | null>(null);

  const base = wsBase(workspaceId);
  const role = workspace?.role;
  const isManager = !!role && RANK[role] >= RANK.manager;
  const isOwner = role === "owner";

  const load = useCallback(() => {
    api<Member[]>(`${base}/members`).then(setMembers).catch((e) => setError(errorMessage(e)));
    if (isManager) api<Invitation[]>(`${base}/invitations`).then(setInvites).catch(() => {});
  }, [base, isManager, setError]);
  useEffect(load, [load]);

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    try {
      const inv = await api<Invitation>(`${base}/invitations`, { method: "POST", json: { email, role: inviteRole } });
      setLastLink(`${window.location.origin}${inv.invite_url}`);
      setEmail("");
      load();
    } catch (err) { setError(errorMessage(err)); }
  }

  async function changeRole(m: Member, r: Role) {
    try { await api(`${base}/members/${encodeURIComponent(m.user_id)}`, { method: "PUT", json: { role: r } }); load(); }
    catch (err) { setError(errorMessage(err)); }
  }

  async function remove(m: Member) {
    if (!confirm(`Remove ${m.display_name} from ${workspace?.name}?`)) return;
    try { await api(`${base}/members/${encodeURIComponent(m.user_id)}`, { method: "DELETE" }); load(); }
    catch (err) { setError(errorMessage(err)); }
  }

  async function revoke(i: Invitation) {
    try { await api(`${base}/invitations/${encodeURIComponent(i.id)}`, { method: "DELETE" }); load(); }
    catch (err) { setError(errorMessage(err)); }
  }

  const canRemove = (m: Member) => m.user_id !== me?.user.id && (isOwner || (isManager && RANK[m.role] < RANK.manager));

  return (
    <Shell workspace={workspace}>
      <h1 className="mb-6">Team</h1>
      {error && <p className="error mb-4" role="alert">{error}</p>}

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="card overflow-x-auto p-0 lg:col-span-2">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-slate-500">
              <tr><th className="px-4 py-2">Name</th><th className="px-4 py-2">Role</th><th className="px-4 py-2">Joined</th><th /></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {members.map((m) => (
                <tr key={m.user_id}>
                  <td className="px-4 py-2">
                    <div className="font-medium">{m.display_name}</div>
                    <div className="text-xs text-slate-500">{m.job_title ?? ""}{m.job_title ? " · " : ""}{m.email}</div>
                  </td>
                  <td className="px-4 py-2">
                    {isOwner && m.user_id !== me?.user.id ? (
                      <select className="input w-auto capitalize" value={m.role} onChange={(e) => changeRole(m, e.target.value as Role)} aria-label={`Role for ${m.display_name}`}>
                        {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                      </select>
                    ) : <span className="capitalize">{m.role}</span>}
                  </td>
                  <td className="px-4 py-2 text-slate-500">{fmtDate(m.joined_at)}</td>
                  <td className="px-4 py-2 text-right">{canRemove(m) && <button className="btn-quiet text-red-700" onClick={() => remove(m)}>Remove</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        {isManager && (
          <section className="card space-y-4">
            <h2>Invite someone</h2>
            <form onSubmit={invite} className="space-y-2">
              <input className="input" type="email" required maxLength={254} placeholder="name@company.com" value={email} onChange={(e) => setEmail(e.target.value)} aria-label="Email" />
              <select className="input" value={inviteRole} onChange={(e) => setInviteRole(e.target.value as Role)} aria-label="Role">
                {ROLES.filter((r) => r !== "owner" && (isOwner || r !== "manager")).map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
              <button className="btn w-full justify-center">Create invitation</button>
            </form>
            {lastLink && (
              <div className="rounded-md bg-indigo-50 p-3 text-xs">
                <p className="mb-1 font-medium text-indigo-900">Share this link with them. It works once, for 7 days, and only for that email address. It won't be shown again.</p>
                <input className="input font-mono text-xs" readOnly value={lastLink} onFocus={(e) => e.currentTarget.select()} aria-label="Invitation link" />
              </div>
            )}
            <div>
              <h3 className="mb-2 text-sm font-medium">Pending invitations</h3>
              <ul className="space-y-2 text-sm">
                {invites.map((i) => (
                  <li key={i.id} className="flex items-center justify-between gap-2">
                    <span className="truncate">{i.email} <span className="text-xs capitalize text-slate-500">· {i.role}</span></span>
                    <button className="btn-quiet text-xs" onClick={() => revoke(i)}>Revoke</button>
                  </li>
                ))}
                {invites.length === 0 && <li className="text-slate-500">None.</li>}
              </ul>
            </div>
          </section>
        )}
      </div>
    </Shell>
  );
}
