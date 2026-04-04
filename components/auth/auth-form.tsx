"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";

type AuthFormProps = {
  mode: "login" | "signup";
};

export function AuthForm({ mode }: AuthFormProps) {
  const router = useRouter();
  const { login } = useAuth();
  const [name, setName] = useState("");

  const isLogin = mode === "login";

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    login(name);
    router.push("/dashboard");
  };

  return (
    <div className="bg-aurora flex min-h-screen items-center justify-center p-4">
      <form
        onSubmit={handleSubmit}
        className="glass w-full max-w-md space-y-4 rounded-3xl p-8"
      >
        <h1 className="text-2xl font-semibold">
          {isLogin ? "Welcome back" : "Create your account"}
        </h1>
        <p className="text-sm text-slate-300">
          {isLogin
            ? "Sign in to continue creating AI videos."
            : "Start generating videos in minutes."}
        </p>
        <input
          required
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Name"
          className="w-full rounded-xl border border-white/20 bg-[#0f1325]/80 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-purple-400/40"
        />
        <input
          required
          type="email"
          placeholder="Email"
          className="w-full rounded-xl border border-white/20 bg-[#0f1325]/80 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-purple-400/40"
        />
        <input
          required
          type="password"
          placeholder="Password"
          className="w-full rounded-xl border border-white/20 bg-[#0f1325]/80 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-purple-400/40"
        />
        <Button type="submit" className="w-full">
          {isLogin ? "Login" : "Sign up"}
        </Button>
        <p className="text-center text-sm text-slate-300">
          {isLogin ? "No account yet?" : "Already registered?"}{" "}
          <Link
            href={isLogin ? "/signup" : "/login"}
            className="font-medium text-purple-200 hover:text-white"
          >
            {isLogin ? "Create one" : "Login"}
          </Link>
        </p>
      </form>
    </div>
  );
}
