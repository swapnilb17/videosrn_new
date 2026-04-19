import { createHmac, timingSafeEqual } from "node:crypto";
import { getServerSession } from "next-auth";
import { authOptions } from "@/lib/auth";
import {
  INTERNAL_BACKEND_URL,
  internalBackendHeaders,
} from "@/lib/internal-backend";
import { razorpayStarterAmountPaise } from "@/lib/razorpay-server";
import { NextRequest, NextResponse } from "next/server";

const BACKEND_FETCH_MS = 90_000;

function verifySignature(orderId: string, paymentId: string, signature: string, secret: string): boolean {
  const expected = createHmac("sha256", secret)
    .update(`${orderId}|${paymentId}`)
    .digest("hex");
  const a = Buffer.from(expected, "utf8");
  const b = Buffer.from(signature.trim(), "utf8");
  if (a.length !== b.length) return false;
  try {
    return timingSafeEqual(a, b);
  } catch {
    return false;
  }
}

export async function POST(request: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const keySecret = (process.env.RAZORPAY_KEY_SECRET || "").trim();
  if (!keySecret) {
    return NextResponse.json(
      { detail: "Razorpay is not configured (missing RAZORPAY_KEY_SECRET)." },
      { status: 503 },
    );
  }

  let body: {
    razorpay_order_id?: string;
    razorpay_payment_id?: string;
    razorpay_signature?: string;
  };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON" }, { status: 400 });
  }

  const orderId = (body.razorpay_order_id || "").trim();
  const paymentId = (body.razorpay_payment_id || "").trim();
  const signature = (body.razorpay_signature || "").trim();
  if (!orderId || !paymentId || !signature) {
    return NextResponse.json(
      { detail: "Missing razorpay_order_id, razorpay_payment_id, or razorpay_signature" },
      { status: 400 },
    );
  }

  if (!verifySignature(orderId, paymentId, signature, keySecret)) {
    return NextResponse.json({ detail: "Invalid payment signature" }, { status: 400 });
  }

  const amountPaise = razorpayStarterAmountPaise();
  const sub = (session.user as { id?: string }).id;

  let res: Response;
  try {
    res = await fetch(`${INTERNAL_BACKEND_URL}/internal/credits/razorpay-starter-confirm`, {
      method: "POST",
      headers: internalBackendHeaders({
        "Content-Type": "application/json",
        "x-user-email": session.user.email,
        ...(sub ? { "x-user-sub": sub } : {}),
      }),
      body: JSON.stringify({
        payment_id: paymentId,
        order_id: orderId,
        amount_paise: amountPaise,
      }),
      signal: AbortSignal.timeout(BACKEND_FETCH_MS),
    });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    const timedOut =
      e instanceof Error && (e.name === "TimeoutError" || e.name === "AbortError");
    return NextResponse.json(
      { detail: timedOut ? "Confirm timed out — try again or contact support." : msg },
      { status: timedOut ? 504 : 502 },
    );
  }

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail =
      typeof data.detail === "string"
        ? data.detail
        : typeof data.error === "string"
          ? data.error
          : `HTTP ${res.status}`;
    return NextResponse.json({ detail }, { status: res.status });
  }

  return NextResponse.json(data);
}
