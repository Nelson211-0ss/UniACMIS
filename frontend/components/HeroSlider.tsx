"use client";

import { useEffect, useState } from "react";

const SLIDES = [
  { src: "/campus/gate-day.jpg" },
  { src: "/campus/gate-close.jpg" },
];

const INTERVAL_MS = 6000;

/** A decorative, auto-advancing backdrop for the login hero — campus
 * photography behind the pitch, never the other way round. Purely
 * ambient: `alt=""` and `aria-hidden` throughout, since nothing here
 * carries information the headline and feature list don't already say.
 * Skips the rotation for `prefers-reduced-motion` rather than just
 * speeding up the crossfade, since auto-advancing imagery is the kind of
 * motion that setting is asking to opt out of. */
export function HeroSlider() {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const timer = setInterval(() => {
      setIndex((current) => (current + 1) % SLIDES.length);
    }, INTERVAL_MS);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="hero-slider" aria-hidden="true">
      {SLIDES.map((slide, i) => (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          key={slide.src}
          src={slide.src}
          alt=""
          className="hero-slider__img"
          style={{ opacity: i === index ? 1 : 0 }}
        />
      ))}
      <div className="hero-slider__dots">
        {SLIDES.map((slide, i) => (
          <span key={slide.src} className={`hero-slider__dot ${i === index ? "is-active" : ""}`} />
        ))}
      </div>
    </div>
  );
}
