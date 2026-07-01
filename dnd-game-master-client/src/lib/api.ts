// Central place for every backend call. Components never call fetch directly —
// they go through hooks, which call these functions.
//
// ROOT_API is intentionally empty: requests are same-origin and proxied to the
// FastAPI backend by next.config.ts rewrites (no CORS). Set it to an absolute
// origin only if you bypass the proxy.

import type { Campaign, CampaignSummary, ClassProfile } from "./types";

export const ROOT_API = "";

/** ADK app name — must match the backend `App(name="app")`. */
export const APP_NAME = "app";

/** Fixed interrupt id the workflow's hitl_gate pauses on (see app/agent.py). */
export const HITL_INTERRUPT_ID = "hitl_approval";

async function getJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${ROOT_API}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

/** GET /tools/classes — class DNA profiles for the party builder. */
export function getClasses(): Promise<ClassProfile[]> {
  return getJSON<ClassProfile[]>("/tools/classes");
}

/** GET /campaigns — saved-campaign summaries for the resume flow. */
export function getCampaigns(): Promise<CampaignSummary[]> {
  return getJSON<CampaignSummary[]>("/campaigns");
}

/** GET /campaign/{id} — full campaign document (`state` = 1 or N turns). */
export function getCampaign(
  campaignId: string,
  includeHistory = false,
): Promise<Campaign> {
  const q = includeHistory ? "?include_history=true" : "";
  return getJSON<Campaign>(`/campaign/${encodeURIComponent(campaignId)}${q}`);
}

/** POST /tools/fetch_campaign_files — fetch adventure markdown docs by path. */
export function fetchCampaignFiles(paths: string[]): Promise<unknown> {
  return getJSON("/tools/fetch_campaign_files", {
    method: "POST",
    body: JSON.stringify({ paths }),
  });
}

/** POST /tools/get_asset_url — fuzzy-resolve an image URL by description. */
export function getAssetUrl(description: string): Promise<{ url?: string }> {
  return getJSON("/tools/get_asset_url", {
    method: "POST",
    body: JSON.stringify({ description }),
  });
}

/** GET /health/db — backend MongoDB health. */
export function healthDb(): Promise<{ status: string }> {
  return getJSON("/health/db");
}

// ---------------------------------------------------------------------------
// ADK run lifecycle (ambient submit → SSE event stream → approve/reject).
//
// A turn is submitted through the ambient Pub/Sub handler (POST /ambient), which
// creates/reuses the session keyed by campaign_id and runs the workflow until it
// finishes or pauses at the HITL gate. The UI streams the session events over SSE
// (sessionStreamUrl) to render the live trace + detect the pending approval, and
// resolves it via the built-in /run endpoint.
// ---------------------------------------------------------------------------

/**
 * POST /ambient (→ backend "/") — submit a turn as a Pub/Sub-style push message.
 * The subscription is the session id (== campaign id); `data` is the JSON payload
 * the workflow reads — a regular turn sends `{ action }`, the first turn of a new
 * campaign sends `{ game, party }`. Resolves when the run finishes or pauses.
 *
 * `data` is sent as a raw JSON object (not base64). Real GCP Pub/Sub requires a
 * base64 string here, but this local bridge talks straight to the ambient
 * handler, whose `_extract_player_action` accepts an object directly — so the
 * backend receives readable JSON with no decode step.
 */
export async function submitTurn(args: {
  sessionId: string;
  userId: string;
  data: Record<string, unknown>;
}): Promise<void> {
  const payload = {
    message: {
      data: args.data,
      attributes: { user_id: args.userId },
    },
    subscription: args.sessionId,
  };
  const res = await fetch(`${ROOT_API}/ambient`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`ambient submit failed: ${res.status}`);
}

/**
 * The SSE URL that streams a session's events
 * (GET /ambient/sessions/{id}/stream). The console opens an EventSource on this
 * instead of polling — the server pushes each event once as it's written.
 */
export function sessionStreamUrl(sessionId: string): string {
  return `${ROOT_API}/ambient/sessions/${encodeURIComponent(sessionId)}/stream`;
}

/**
 * POST /run — resolve a turn paused at the HITL gate. Sends the
 * `adk_request_input` functionResponse; "approve" passes the gate, anything else
 * (e.g. "reject") cancels the turn. Returns when the resumed run completes.
 */
export async function sendDecision(args: {
  sessionId: string;
  userId: string;
  approved: boolean;
}): Promise<void> {
  const payload = {
    app_name: APP_NAME,
    user_id: args.userId,
    session_id: args.sessionId,
    new_message: {
      role: "user",
      parts: [
        {
          functionResponse: {
            id: HITL_INTERRUPT_ID,
            name: "adk_request_input",
            response: { result: args.approved ? "approve" : "reject" },
          },
        },
      ],
    },
  };
  const res = await fetch(`${ROOT_API}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`decision failed: ${res.status}`);
}
