import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import { razorpayStarterAmountPaise } from "@/lib/razorpay-server";
import { NextResponse } from "next/server";

const BACKEND_FETCH_MS = 30_000;

export async function POST() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const keyId = (process.env.RAZORPAY_KEY_ID || "").trim();
  const keySecret = (process.env.RAZORPAY_KEY_SECRET || "").trim();
  if (!keyId || !keySecret) {
    return NextResponse.json(
      { detail: "Razorpay is not configured (missing RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET)." },
      { status: 503 },
    );
  }

  const amountPaise = razorpayStarterAmountPaise();
  const sub = (session.user as { id?: string }).id || "user";
  const receipt = `st_${String(sub).replace(/[^a-zA-Z0-9]/g, "").slice(0, 12)}_${Date.now()}`.slice(
    0,
    40,
  );

  const auth = Buffer.from(`${keyId}:${keySecret}`).toString("base64");

  let res: Response;
  try {
    res = await fetch("https://api.razorpay.com/v1/orders", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Basic ${auth}`,
      },
      body: JSON.stringify({
        amount: amountPaise,
        currency: "INR",
        receipt,
        notes: { product: "starter_bundle" },
      }),
      signal: AbortSignal.timeout(BACKEND_FETCH_MS),
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ detail: msg }, { status: 502 });
  }

  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) {
    const err =
      typeof data.error === "object" && data.error !== null
        ? (data.error as Record<string, unknown>)
        : null;
    const desc =
      typeof err?.description === "string"
        ? err.description
        : typeof data.description === "string"
          ? data.description
          : `Razorpay order failed (${res.status})`;
    return NextResponse.json({ detail: desc }, { status: 502 });
  }

  const orderId = typeof data.id === "string" ? data.id : "";
  if (!orderId) {
    return NextResponse.json({ detail: "Invalid Razorpay response (no order id)." }, { status: 502 });
  }

  return NextResponse.json({
    keyId,
    orderId,
    amount: amountPaise,
    currency: "INR",
  });
}
