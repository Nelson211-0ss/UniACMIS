"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { GraduationCapIcon } from "@/components/icons";
import { useAuth } from "@/lib/auth";

export default function Home() {
  const router = useRouter();
  const { user, loading } = useAuth();

  useEffect(() => {
    if (loading) return;
    router.replace(user ? "/dashboard" : "/login");
  }, [user, loading, router]);

  return (
    <main className="splash">
      <div className="splash__card">
        <span className="splash__brand">
          <GraduationCapIcon size={26} />
        </span>
        <h1 className="login__title">UniACMIS</h1>
        <p className="login__sub" style={{ marginBottom: 0 }}>
          <span className="spinner" aria-hidden="true" /> Loading…
        </p>
      </div>
    </main>
  );
}
