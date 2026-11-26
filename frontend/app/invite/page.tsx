"use client";

// Invitation links look like /invite#<token>. The token stays in the URL fragment, so
// it's never sent to the server in the page request or leaked through Referer.

import { useEffect, useState } from "react";
import { api, ApiError, errorMessage, type Session, type Workspace } from "@/lib/api";

type Preview = { workspace_name: string; email: string; role: string; account_exists: boolean };

export default function InvitePage() {
  const [token, setToken] = useState<string | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [signedInAs, setSignedInAs] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const t = window.location.hash.slice(1);
    if (!t) { setError("This invitation link is incomplete."); return; }
    setToken(t);
    api<Preview>("/api/v1/invitations/preview", { method: "POST", json: { token: t } }).then(setPreview).catch((e) => setError(errorMessage(e)));
    fetch("/api/v1/auth/me", { credentials: "same-origin" }).then((r) => (r.ok ? r.json() : null))
      .then((s: Session | null) => setSignedInAs(s?.user.email ?? null)).catch(() => {});
  }, []);

  async function accept() {
    setBusy(true);
    try {
      const ws = await api<Workspace>("/api/v1/invitations/accept", { method: "POST", json: { token } });
      window.location.assign(`/workspaces/${encodeURIComponent(ws.id)}`);
    } catch (e) { setError(errorMessage(e)); setBusy(false); }
  }

  async function register(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api<Session>("/api/v1/invitations/register", { method: "POST", json: { token, display_name: name, password } });
      window.location.assign("/workspaces");
    } catch (err) {
      setError(err instanceof ApiError && err.code === "weak_password"
        ? "Choose a stronger password: at least 12 characters, not a common one, and not containing your email name."
        : errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="card w-full max-w-md space-y-4">
        <h1>Join a workspace</h1>
        {error && <p className="error" role="alert">{error}</p>}
        {preview && (
          <>
            <p className="text-sm text-slate-700">
              You've been invited to <strong>{preview.workspace_name}</strong> as a <strong>{preview.role}</strong>.
              This invitation is for <strong>{preview.email}</strong>.
            </p>
            {preview.account_exists ? (
              signedInAs === preview.email ? (
                <button className="btn w-full justify-center" disabled={busy} onClick={accept}>Accept invitation</button>
              ) : (
                <p className="text-sm text-slate-600">
                  {signedInAs ? `You're signed in as ${signedInAs}. ` : ""}
                  Sign in as {preview.email}, then open this link again to accept. <a className="text-indigo-700 underline" href="/login">Go to sign in</a>
                </p>
              )
            ) : (
              <form onSubmit={register} className="space-y-3">
                <div><label className="label" htmlFor="name">Your name</label>
                  <input id="name" className="input" required maxLength={100} autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} /></div>
                <div><label className="label" htmlFor="pw">Choose a password</label>
                  <input id="pw" className="input" type="password" required minLength={12} maxLength={128} autoComplete="new-password"
                         value={password} onChange={(e) => setPassword(e.target.value)} />
                  <p className="mt-1 text-xs text-slate-500">At least 12 characters.</p></div>
                <button className="btn w-full justify-center" disabled={busy}>Create account and join</button>
              </form>
            )}
          </>
        )}
      </div>
    </main>
  );
}
