import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.INTERNAL_BACKEND_URL || "http://backend:8000";

export async function GET(request: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const type = searchParams.get("type") || "";
  const qs = type ? `?type=${encodeURIComponent(type)}` : "";

  const res = await fetch(`${BACKEND_URL}/internal/user-media${qs}`, {
    headers: { "x-user-email": session.user.email },
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
