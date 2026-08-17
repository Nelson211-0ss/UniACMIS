"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiFailure } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const { user, signIn } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (user) router.replace("/dashboard");
  }, [user, router]);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");

    try {
      await signIn(email, password);
      router.replace("/dashboard");
    } catch (caught) {
      if (caught instanceof ApiFailure) {
        // Signing in genuinely needs the network, so say so rather than implying
        // the credentials were wrong.
        setError(
          caught.offline
            ? "No connection to the server. Signing in needs a network; entries you already queued are safe."
            : caught.error.message || "Sign-in failed.",
        );
      } else {
        setError("Sign-in failed.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <form className="login__card" onSubmit={onSubmit}>
        <h1 className="login__title">UniACMIS</h1>
        <p className="login__sub">Academic Management Information System</p>

        {error ? <div className="alert alert--error">{error}</div> : null}

        <div className="field">
          <label htmlFor="email">Email address</label>
          <input
            id="email"
            type="email"
            autoComplete="username"
            inputMode="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>

        <button type="submit" disabled={busy} style={{ width: "100%" }}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
