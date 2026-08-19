"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { CHART_GRID, CHART_SERIES, CHART_TICK } from "@/lib/chartColors";

export interface BarSeries {
  key: string;
  label: string;
  color?: string;
}

interface BarChartCardProps {
  title: string;
  subtitle?: string;
  data: Array<Record<string, string | number>>;
  xKey: string;
  series: BarSeries[];
  height?: number;
  stacked?: boolean;
}

/** A bar chart card for a magnitude comparison across categories (enrollment
 * by programme, revenue by month) — never dual-axis, one hue per series in
 * the fixed institutional order unless the caller names its own. */
export function BarChartCard({
  title,
  subtitle,
  data,
  xKey,
  series,
  height = 260,
  stacked = false,
}: BarChartCardProps) {
  return (
    <div className="card chart-card">
      <div className="chart-card__header">
        <div>
          <h3 className="chart-card__title">{title}</h3>
          {subtitle ? <p className="chart-card__subtitle">{subtitle}</p> : null}
        </div>
      </div>
      {data.length === 0 ? (
        <div className="chart-empty">No data yet.</div>
      ) : (
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={data} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke={CHART_GRID} />
            <XAxis
              dataKey={xKey}
              tick={{ fill: CHART_TICK, fontSize: 12 }}
              axisLine={{ stroke: CHART_GRID }}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: CHART_TICK, fontSize: 12 }}
              axisLine={false}
              tickLine={false}
              width={40}
              allowDecimals={false}
            />
            <Tooltip
              contentStyle={{
                borderRadius: 8,
                border: "1px solid var(--border)",
                fontSize: 13,
                boxShadow: "var(--shadow-md)",
              }}
              cursor={{ fill: "#eef1f5" }}
            />
            {series.length > 1 ? <Legend wrapperStyle={{ fontSize: 12 }} /> : null}
            {series.map((s, index) => (
              <Bar
                key={s.key}
                dataKey={s.key}
                name={s.label}
                fill={s.color ?? CHART_SERIES[index % CHART_SERIES.length]}
                radius={stacked ? [0, 0, 0, 0] : [4, 4, 0, 0]}
                stackId={stacked ? "stack" : undefined}
                maxBarSize={48}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
