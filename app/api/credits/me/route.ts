import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.INTERNAL_BACKEND_URL || "http://backend:8000";

export async function GET(_request: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const sub = (session.user as { id?: string }).id;

  const res = await fetch(`${BACKEND_URL}/internal/credits/me`, {
    headers: {
      "x-user-email": session.user.email,
      ...(sub ? { "x-user-sub": sub } : {}),
    },
    cache: "no-store",
  });

  if (!res.ok) {
    return NextResponse.json(
      { error: "Backend error" },
      { status: res.status },
    );
  }

  const data = await res.json();
  return NextResponse.json(data);
}
