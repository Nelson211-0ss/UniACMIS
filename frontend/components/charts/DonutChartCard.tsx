"use client";

import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { useChartPalette } from "@/lib/chartColors";
import { useTheme } from "@/lib/theme";

export interface DonutSlice {
  key: string;
  label: string;
  value: number;
  color?: string;
}

interface DonutChartCardProps {
  title: string;
  subtitle?: string;
  data: DonutSlice[];
  height?: number;
  /** Shown in the centre of the ring — typically the total or a headline %. */
  centre?: { value: string; label: string };
  /** 0 renders a true pie (no hole, no centre label) — for a status
   * breakdown where there is no single headline number to anchor there. */
  innerRadius?: string | number;
}

/** A proportion of a whole (pass/fail/incomplete, collected/outstanding) —
 * a donut by default so a headline number can sit in the centre, or a true
 * pie via `innerRadius={0}` when the whole has no single number to show.
 * Never more than a handful of slices either way. */
export function DonutChartCard({
  title,
  subtitle,
  data,
  height = 240,
  centre,
  innerRadius = "62%",
}: DonutChartCardProps) {
  const total = data.reduce((sum, slice) => sum + slice.value, 0);
  const isPie = innerRadius === 0 || innerRadius === "0" || innerRadius === "0%";
  const { series: seriesColors } = useChartPalette();
  const { theme } = useTheme();
  const ringGap = theme === "dark" ? "#121212" : "#ffffff";

  return (
    <div className="card chart-card">
      <div className="chart-card__header">
        <div>
          <h3 className="chart-card__title">{title}</h3>
          {subtitle ? <p className="chart-card__subtitle">{subtitle}</p> : null}
        </div>
      </div>
      {total === 0 ? (
        <div className="chart-empty">No data yet.</div>
      ) : (
        <div style={{ position: "relative" }}>
          <ResponsiveContainer width="100%" height={height}>
            <PieChart>
              <Pie
                data={data}
                dataKey="value"
                nameKey="label"
                innerRadius={innerRadius}
                outerRadius="92%"
                paddingAngle={data.length > 1 ? 2 : 0}
                stroke={ringGap}
                strokeWidth={2}
                animationDuration={700}
                animationEasing="ease-out"
              >
                {data.map((slice, index) => (
                  <Cell
                    key={slice.key}
                    fill={slice.color ?? seriesColors[index % seriesColors.length]}
                  />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  background: "var(--surface)",
                  borderRadius: 8,
                  border: "1px solid var(--border)",
                  fontSize: 13,
                  boxShadow: "var(--shadow-md)",
                }}
                itemStyle={{ color: "var(--text)" }}
                labelStyle={{ color: "var(--text)" }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
          {centre && !isPie ? (
            <div
              style={{
                position: "absolute",
                top: "42%",
                left: "50%",
                transform: "translate(-50%, -50%)",
                textAlign: "center",
                pointerEvents: "none",
              }}
            >
              <div
                style={{
                  fontFamily: "var(--font-display)",
                  fontWeight: 700,
                  fontSize: "1.5rem",
                  color: "var(--ink)",
                  lineHeight: 1.1,
                }}
              >
                {centre.value}
              </div>
              <div style={{ fontSize: "0.75rem", color: "var(--muted)" }}>{centre.label}</div>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
