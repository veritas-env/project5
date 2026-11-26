"use client";

import { useEffect, useState } from "react";
import { api, errorMessage, type Member, type Session, type Workspace } from "./api";

export function wsBase(id: string): string {
  return `/api/v1/workspaces/${encodeURIComponent(id)}`;
}

/** Loads the workspace (and optionally its members) for a page. */
export function useWorkspace(id: string, withMembers = false) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Workspace>(wsBase(id)).then(setWorkspace).catch((e) => setError(errorMessage(e)));
    if (withMembers) api<Member[]>(`${wsBase(id)}/members`).then(setMembers).catch(() => {});
  }, [id, withMembers]);

  const nameOf = (userId: string | null) => (userId ? members.find((m) => m.user_id === userId)?.display_name ?? "Former member" : "Unassigned");
  return { workspace, members, error, setError, nameOf };
}

/** The signed-in user's session, for pages that need to know who they are. */
export function useMe(): Session | null {
  const [me, setMe] = useState<Session | null>(null);
  useEffect(() => {
    api<Session>("/api/v1/auth/me").then(setMe).catch(() => {});
  }, []);
  return me;
}
