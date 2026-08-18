"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import {
  AlertCircleIcon,
  CheckCircleIcon,
  EyeIcon,
  EyeOffIcon,
  GraduationCapIcon,
  WifiOffIcon,
} from "@/components/icons";
import { ApiFailure } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const HERO_FEATURES = [
  "Works through power and network outages",
  "Every grade and fee change is auditable",
  "Role-based access for every office on campus",
];

export default function LoginPage() {
  const router = useRouter();
  const { user, signIn } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [offline, setOffline] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (user) router.replace("/dashboard");
  }, [user, router]);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setOffline(false);

    try {
      await signIn(email, password);
      router.replace("/dashboard");
    } catch (caught) {
      if (caught instanceof ApiFailure) {
        // Signing in genuinely needs the network, so say so rather than implying
        // the credentials were wrong.
        setOffline(caught.offline);
        setError(
          caught.offline
            ? "No connection to the server. Signing in needs a network — entries you already queued on this device are safe."
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
      <section className="login__hero" aria-hidden="true">
        <div className="login__hero-brand">
          <span className="login__hero-mark">
            <GraduationCapIcon size={22} />
          </span>
          UniACMIS
        </div>

        <div className="login__hero-copy">
          <h1>Academic Management, built for South Sudan.</h1>
          <p>
            One system for admissions, registry, examinations and finance — designed
            to keep working when the power and the connection don&rsquo;t.
          </p>

          <ul className="login__hero-features">
            {HERO_FEATURES.map((feature) => (
              <li key={feature}>
                <CheckCircleIcon size={18} />
                {feature}
              </li>
            ))}
          </ul>
        </div>

        <p className="login__hero-foot">
          University Academic Management Information System
        </p>
      </section>

      <section className="login__panel">
        <form className="login__card" onSubmit={onSubmit}>
          <div className="login__mobile-brand">
            <GraduationCapIcon size={22} />
            UniACMIS
          </div>

          <h1 className="login__title">Sign in</h1>
          <p className="login__sub">Enter your university account to continue.</p>

          {error ? (
            <div className={`alert alert--${offline ? "warning" : "error"}`} role="alert">
              {offline ? <WifiOffIcon size={18} /> : <AlertCircleIcon size={18} />}
              <span>{error}</span>
            </div>
          ) : null}

          <div className="field">
            <label htmlFor="email">Email address</label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              inputMode="email"
              placeholder="you@university.edu.ss"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="password">Password</label>
            <div className="field--icon field--password">
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                style={{ paddingLeft: 12 }}
              />
              <button
                type="button"
                className="field-toggle icon-btn"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                aria-pressed={showPassword}
              >
                {showPassword ? <EyeOffIcon size={18} /> : <EyeIcon size={18} />}
              </button>
            </div>
          </div>

          <button type="submit" className="primary block" disabled={busy}>
            {busy ? <span className="spinner" aria-hidden="true" /> : null}
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}
