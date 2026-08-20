/**
 * Chart colours as literal hex values, mirroring the `--chart-*` custom
 * properties in globals.css.
 *
 * Recharts renders bars, lines and axes as raw SVG attributes rather than
 * through an inline `style`, and a CSS custom property only resolves inside
 * an actual CSS context — so `fill="var(--chart-1)"` on an SVG shape silently
 * fails to resolve in every browser. Literal values here are the fix; keep
 * them in sync with globals.css by hand, since there are only five of them.
 */

export const CHART_SERIES = [
  "#1b2a4a", // --chart-1 / --ink
  "#b8862e", // --chart-2 / --seal
  "#1f7a72", // --chart-3
  "#7a3b69", // --chart-4
  "#5b6b85", // --chart-5
];

export const CHART_GRID = "#d8dce3"; // --border
export const CHART_TICK = "#6b7280"; // --muted

export const CHART_STATUS = {
  good: "#2f6844", // --status-verified
  warning: "#8a6d1f", // --status-pending
  bad: "#a83c32", // --status-hold
  neutral: "#4b5563", // --status-neutral
};

/** A fixed-width y-axis clips a six-figure amount (currency totals routinely
 * are) down to its last couple of digits rather than wrapping — this keeps
 * every tick short enough to fit regardless of magnitude. Tooltips still
 * show the exact figure; only the axis compacts. */
export function compactNumber(value: number): string {
  return new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(value);
}
