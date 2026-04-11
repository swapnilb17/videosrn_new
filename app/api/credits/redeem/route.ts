import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import {
  INTERNAL_BACKEND_URL,
  internalBackendHeaders,
} from "@/lib/internal-backend";
import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  let body: { code?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const sub = (session.user as { id?: string }).id;

  const res = await fetch(`${INTERNAL_BACKEND_URL}/internal/credits/redeem`, {
    method: "POST",
    headers: internalBackendHeaders({
      "Content-Type": "application/json",
      "x-user-email": session.user.email,
      ...(sub ? { "x-user-sub": sub } : {}),
    }),
    body: JSON.stringify({ code: body.code ?? "" }),
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    return NextResponse.json(
      { detail: data.detail || "Redeem failed" },
      { status: res.status },
    );
  }

  return NextResponse.json(data);
}
