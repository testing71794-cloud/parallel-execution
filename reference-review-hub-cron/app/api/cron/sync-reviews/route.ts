import { NextRequest, NextResponse } from "next/server";

/**
 * Vercel Cron: GET (only Vercel should call this, or you with the secret).
 * Set CRON_SECRET in Vercel project env, and configure SYNC how your app does sync
 * (webhook, internal route, or edge calls your worker).
 */
export const maxDuration = 300;

export async function GET(request: NextRequest) {
  if (!authorizeCronRequest(request)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const url = process.env.SYNC_REVIEW_WEBHOOK_URL;
  if (!url) {
    return NextResponse.json(
      { error: "SYNC_REVIEW_WEBHOOK_URL is not set" },
      { status: 500 }
    );
  }

  const r = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
  });

  const text = await r.text();
  if (!r.ok) {
    return NextResponse.json(
      { ok: false, status: r.status, body: text.slice(0, 2000) },
      { status: 502 }
    );
  }

  return NextResponse.json({ ok: true, triggered: true });
}

function authorizeCronRequest(request: NextRequest): boolean {
  const secret = process.env.CRON_SECRET;
  if (!secret) return false;

  const header = request.headers.get("authorization");
  return header === `Bearer ${secret}`;
}
