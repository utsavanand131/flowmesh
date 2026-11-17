"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";

const API_URL = process.env.NEXT_PUBLIC_API_URL;

export default function LoginPage() {
  const router = useRouter();
  const { refreshUser } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleLogin(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const response = await fetch(`${API_URL}/auth/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify({ email, password }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Unable to sign in. Please check your credentials.",
        );
      }

      // Synchronize frontend authentication state with backend session.
      const authenticatedUser = await refreshUser();

      if (!authenticatedUser) {
        throw new Error(
          "Login succeeded, but your session could not be verified. Please try again.",
        );
      }

      router.push("/");
      router.refresh();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Something went wrong. Please try again.",
      );
    } finally {
      setLoading(false);
    }
  }

  function handleOAuth(provider: "google" | "github") {
    window.location.href = `${API_URL}/auth/${provider}/login`;
  }

  return (
    <main className="min-h-screen bg-background text-foreground flex items-center justify-center px-5 py-12">
      <div className="w-full max-w-md">
        {/* Login Card */}
        <div className="bg-surface border border-border rounded-2xl p-7 sm:p-9 shadow-xl">
          {/* Brand */}
          <div className="flex items-center gap-3 mb-8">
            <div className="h-11 w-11 rounded-xl bg-accent/15 border border-accent/25 flex items-center justify-center">
              <span className="text-accent text-xl font-bold">F</span>
            </div>

            <span className="text-2xl font-semibold tracking-tight">
              Flow<span className="text-accent">Mesh</span>
            </span>
          </div>

          {/* Heading */}
          <div className="mb-7">
            <h1 className="text-2xl font-semibold tracking-tight">
              Welcome back
            </h1>

            <p className="text-muted text-sm mt-2">
              Sign in to access your FlowMesh workspace.
            </p>
          </div>

          {/* OAuth */}
          <div className="space-y-3">
            <button
              type="button"
              onClick={() => handleOAuth("google")}
              className="w-full h-11 rounded-lg border border-border bg-surface-hover hover:border-accent/50 transition flex items-center justify-center gap-3 text-sm font-medium"
            >
              <span className="font-bold text-base">G</span>
              Continue with Google
            </button>

            <button
              type="button"
              onClick={() => handleOAuth("github")}
              className="w-full h-11 rounded-lg border border-border bg-surface-hover hover:border-accent/50 transition flex items-center justify-center gap-3 text-sm font-medium"
            >
              <span className="font-bold text-base">GH</span>
              Continue with GitHub
            </button>
          </div>

          {/* Divider */}
          <div className="flex items-center gap-4 my-6">
            <div className="h-px flex-1 bg-border" />

            <span className="text-xs text-muted">OR CONTINUE WITH EMAIL</span>

            <div className="h-px flex-1 bg-border" />
          </div>

          {/* Login Form */}
          <form onSubmit={handleLogin} className="space-y-5">
            <div>
              <label htmlFor="email" className="block text-sm font-medium mb-2">
                Email address
              </label>

              <input
                id="email"
                type="email"
                required
                autoComplete="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full h-11 px-3 rounded-lg bg-surface-muted border border-border text-sm outline-none focus:border-accent transition placeholder:text-muted"
              />
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <label htmlFor="password" className="text-sm font-medium">
                  Password
                </label>
              </div>

              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  required
                  autoComplete="current-password"
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full h-11 px-3 pr-16 rounded-lg bg-surface-muted border border-border text-sm outline-none focus:border-accent transition placeholder:text-muted"
                />

                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted hover:text-foreground transition"
                >
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>
            </div>

            {error && (
              <div className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-3 text-sm text-danger">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full h-11 rounded-lg bg-accent text-[#101817] font-semibold text-sm hover:bg-accent-hover transition disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {loading ? "Signing in..." : "Sign in"}
            </button>
          </form>

          {/* Register Link */}
          <p className="text-center text-sm text-muted mt-7">
            Don't have an account?{" "}
            <Link
              href="/register"
              className="text-accent hover:text-accent-hover font-medium transition"
            >
              Create account
            </Link>
          </p>
        </div>

        {/* Footer */}
        <p className="text-center text-xs text-muted mt-7">
          Secure authentication · FlowMesh
        </p>
      </div>
    </main>
  );
}
