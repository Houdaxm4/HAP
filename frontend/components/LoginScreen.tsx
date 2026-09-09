"use client";

import { useState, type FormEvent } from "react";
import { APP_CONFIG, getApplicationInitial } from "@/lib/app_config";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";

export default function LoginScreen() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setError("Too many attempts. Wait a minute and try again.");
      } else {
        setError("Invalid credentials.");
      }
    } finally {
      setSubmitting(false);
      setPassword("");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-md rounded-xl border border-hap-border bg-hap-panel p-8">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded bg-hap-orange text-sm font-bold text-black">
            {getApplicationInitial()}
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-wider text-hap-orange">
              {APP_CONFIG.applicationName}
            </h1>
            <p className="text-[10px] uppercase tracking-widest text-hap-muted">
              Private access
            </p>
          </div>
        </div>
        <form onSubmit={onSubmit} className="space-y-4" autoComplete="on">
          <label className="block text-sm">
            <span className="text-hap-muted">Username</span>
            <input
              name="username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="mt-1 w-full rounded-lg border border-hap-border bg-background px-3 py-2 text-sm outline-none focus:border-hap-orange/50"
              required
            />
          </label>
          <label className="block text-sm">
            <span className="text-hap-muted">Password</span>
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 w-full rounded-lg border border-hap-border bg-background px-3 py-2 text-sm outline-none focus:border-hap-orange/50"
              required
            />
          </label>
          {error ? <p className="text-sm text-red-400">{error}</p> : null}
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded border border-hap-orange/40 bg-hap-orange/10 px-4 py-2.5 text-sm font-semibold text-hap-orange hover:bg-hap-orange/20 disabled:opacity-50"
          >
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
