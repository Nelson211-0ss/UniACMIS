"use client";

import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import { CHART_SERIES } from "@/lib/chartColors";

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
}

/** A proportion of a whole (pass/fail/incomplete, collected/outstanding) —
 * a donut rather than a bare pie so a headline number can sit in the
 * centre, and never more than a handful of slices. */
export function DonutChartCard({ title, subtitle, data, height = 240, centre }: DonutChartCardProps) {
  const total = data.reduce((sum, slice) => sum + slice.value, 0);

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
                innerRadius="62%"
                outerRadius="92%"
                paddingAngle={data.length > 1 ? 2 : 0}
                stroke="#ffffff"
                strokeWidth={2}
              >
                {data.map((slice, index) => (
                  <Cell
                    key={slice.key}
                    fill={slice.color ?? CHART_SERIES[index % CHART_SERIES.length]}
                  />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  borderRadius: 8,
                  border: "1px solid var(--border)",
                  fontSize: 13,
                  boxShadow: "var(--shadow-md)",
                }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
          {centre ? (
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
