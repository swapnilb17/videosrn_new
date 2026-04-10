import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.INTERNAL_BACKEND_URL || "http://backend:8000";

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

  const res = await fetch(`${BACKEND_URL}/internal/credits/redeem`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-user-email": session.user.email,
      ...(sub ? { "x-user-sub": sub } : {}),
    },
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
