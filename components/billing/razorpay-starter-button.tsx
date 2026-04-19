"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  ApiError,
  createRazorpayStarterOrder,
  verifyRazorpayStarterPayment,
} from "@/lib/api";

type RazorpayHandlerResponse = {
  razorpay_payment_id: string;
  razorpay_order_id: string;
  razorpay_signature: string;
};

type RazorpayConstructorOptions = {
  key: string;
  order_id: string;
  currency: string;
  name: string;
  description: string;
  handler: (response: RazorpayHandlerResponse) => void | Promise<void>;
  prefill?: { email?: string; name?: string };
  theme?: { color?: string };
  modal?: { ondismiss?: () => void };
};

type RazorpayInstance = { open: () => void };

function loadRazorpayScript(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (document.querySelector('script[src="https://checkout.razorpay.com/v1/checkout.js"]')) {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://checkout.razorpay.com/v1/checkout.js";
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Could not load Razorpay Checkout"));
    document.body.appendChild(s);
  });
}

function getRazorpayConstructor(): new (opts: RazorpayConstructorOptions) => RazorpayInstance {
  const w = window as unknown as { Razorpay?: new (o: RazorpayConstructorOptions) => RazorpayInstance };
  if (!w.Razorpay) {
    throw new Error("Razorpay is not available");
  }
  return w.Razorpay;
}

type Props = {
  userEmail: string;
  userName?: string;
  disabled?: boolean;
  onPaid?: () => void;
  className?: string;
};

export function RazorpayStarterButton({
  userEmail,
  userName,
  disabled,
  onPaid,
  className,
}: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handlePay() {
    setError(null);
    setBusy(true);
    try {
      const order = await createRazorpayStarterOrder();
      await loadRazorpayScript();
      const Razorpay = getRazorpayConstructor();

      const rzp = new Razorpay({
        key: order.keyId,
        order_id: order.orderId,
        currency: order.currency,
        name: "Enably AI",
        description: "Starter bundle — unlock Starter plan & top up toward 500 credits",
        handler: async (response) => {
          try {
            await verifyRazorpayStarterPayment({
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
            });
            onPaid?.();
          } catch (e) {
            const msg =
              e instanceof ApiError
                ? e.detail
                : e instanceof Error
                  ? e.message
                  : "Could not confirm payment";
            setError(msg);
          } finally {
            setBusy(false);
          }
        },
        prefill: {
          email: userEmail || undefined,
          name: userName || undefined,
        },
        theme: { color: "#7c3aed" },
        modal: {
          ondismiss: () => {
            setBusy(false);
          },
        },
      });
      rzp.open();
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.detail
          : e instanceof Error
            ? e.message
            : "Payment failed";
      setError(msg);
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <Button
        type="button"
        className={className}
        disabled={disabled || busy}
        onClick={() => void handlePay()}
      >
        {busy ? "…" : "Pay ₹499 with Razorpay"}
      </Button>
      {error ? (
        <p className="text-sm text-red-300/90 whitespace-pre-wrap">{error}</p>
      ) : null}
    </div>
  );
}
