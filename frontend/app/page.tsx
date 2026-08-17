"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/lib/auth";

export default function Home() {
  const router = useRouter();
  const { user, loading } = useAuth();

  useEffect(() => {
    if (loading) return;
    router.replace(user ? "/dashboard" : "/login");
  }, [user, loading, router]);

  return (
    <main className="login">
      <div className="login__card">
        <h1 className="login__title">UniACMIS</h1>
        <p className="login__sub">Loading…</p>
      </div>
    </main>
  );
}
