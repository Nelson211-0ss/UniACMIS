"use client";

import { useEffect, useRef, useState } from "react";

interface CountUpProps {
  value: number;
  duration?: number;
  decimals?: number;
  formatter?: (value: number) => string;
}

/** Animates a stat tile's number counting up to its real value on mount (and
 * again on any later change) rather than just appearing — the kind of small
 * motion a dashboard number benefits from and a static "35" never gets.
 * Skips straight to the final value under `prefers-reduced-motion`. */
export function CountUp({ value, duration = 900, decimals = 0, formatter }: CountUpProps) {
  const [display, setDisplay] = useState(0);
  const fromRef = useRef(0);

  useEffect(() => {
    if (typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setDisplay(value);
      fromRef.current = value;
      return;
    }

    const from = fromRef.current;
    const delta = value - from;
    const start = performance.now();
    let raf = 0;

    function tick(now: number) {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(from + delta * eased);
      if (progress < 1) {
        raf = requestAnimationFrame(tick);
      } else {
        fromRef.current = value;
      }
    }

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);

  const rounded = Math.round(display * 10 ** decimals) / 10 ** decimals;
  return (
    <>
      {formatter
        ? formatter(rounded)
        : rounded.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}
    </>
  );
}
