/** Server-only: Starter SKU amount (must match FastAPI `STARTER_RAZORPAY_AMOUNT_PAISE`). */
export function razorpayStarterAmountPaise(): number {
  const raw = (process.env.RAZORPAY_STARTER_AMOUNT_PAISE || "49900").trim();
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 49900;
}
