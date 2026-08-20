"use client";

/**
 * Chart colours as literal hex values, mirroring the `--chart-*` custom
 * properties in globals.css.
 *
 * Recharts renders bars, lines and axes as raw SVG attributes rather than
 * through an inline `style`, and a CSS custom property only resolves inside
 * an actual CSS context — so `fill="var(--chart-1)"` on an SVG shape silently
 * fails to resolve in every browser. Literal values here are the fix; keep
 * them in sync with globals.css by hand, since there are only five of them.
 *
 * Two full sets, not one: the light-mode navy (`#1b2a4a`) reads as almost
 * the same tone as a dark card background, so a single-series bar or line
 * chart would all but disappear under the dark theme rather than merely
 * looking slightly off. `useChartPalette()` is how the three chart
 * components pick the right set; `CHART_SERIES`/`CHART_GRID`/`CHART_TICK`/
 * `CHART_STATUS` stay exported as the light set for the handful of pages
 * that build an explicit slice colour (e.g. `CHART_STATUS.good`) outside a
 * chart component — those stay legible in dark mode too since status hues
 * are saturated enough not to wash out, so it was not worth threading the
 * theme through every page that calls them just for this.
 */

import { useTheme } from "@/lib/theme";

export const CHART_SERIES_LIGHT = [
  "#1b2a4a", // --chart-1 / --ink
  "#b8862e", // --chart-2 / --seal
  "#1f7a72", // --chart-3
  "#7a3b69", // --chart-4
  "#5b6b85", // --chart-5
];

export const CHART_SERIES_DARK = [
  "#7195d6", // --ink-strong (dark)
  "#e0b568", // --seal-strong (dark)
  "#4fb3a3", // brightened --chart-3
  "#c17ba8", // brightened --chart-4
  "#93a2bd", // brightened --chart-5
];

export const CHART_GRID_LIGHT = "#d8dce3"; // --border
export const CHART_GRID_DARK = "#272727"; // --border (dark)

export const CHART_TICK_LIGHT = "#6b7280"; // --muted
export const CHART_TICK_DARK = "#9a9a9a"; // --muted (dark)

export const CHART_STATUS_LIGHT = {
  good: "#2f6844", // --status-verified
  warning: "#8a6d1f", // --status-pending
  bad: "#a83c32", // --status-hold
  neutral: "#4b5563", // --status-neutral
};

export const CHART_STATUS_DARK = {
  good: "#4caf72", // --status-verified (dark)
  warning: "#d4ac4e", // --status-pending (dark)
  bad: "#e2685a", // --status-hold (dark)
  neutral: "#9aa5b8", // --status-neutral (dark)
};

// Kept as the light set, for callers outside a chart component — see the
// file header for why these do not also switch with the theme.
export const CHART_SERIES = CHART_SERIES_LIGHT;
export const CHART_GRID = CHART_GRID_LIGHT;
export const CHART_TICK = CHART_TICK_LIGHT;
export const CHART_STATUS = CHART_STATUS_LIGHT;

/** The literal-hex set a chart component should draw with right now —
 * call from inside `BarChartCard`/`DonutChartCard`/`LineChartCard`, not
 * from a page building its own slice/series colours. */
export function useChartPalette() {
  const { theme } = useTheme();
  return theme === "dark"
    ? { series: CHART_SERIES_DARK, grid: CHART_GRID_DARK, tick: CHART_TICK_DARK, status: CHART_STATUS_DARK }
    : { series: CHART_SERIES_LIGHT, grid: CHART_GRID_LIGHT, tick: CHART_TICK_LIGHT, status: CHART_STATUS_LIGHT };
}

/** A fixed-width y-axis clips a six-figure amount (currency totals routinely
 * are) down to its last couple of digits rather than wrapping — this keeps
 * every tick short enough to fit regardless of magnitude. Tooltips still
 * show the exact figure; only the axis compacts. */
export function compactNumber(value: number): string {
  return new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(value);
}
