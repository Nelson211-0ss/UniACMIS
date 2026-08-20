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

import { compactNumber, useChartPalette } from "@/lib/chartColors";
import { useTheme } from "@/lib/theme";

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
  const { series: seriesColors, grid, tick } = useChartPalette();
  const { theme } = useTheme();
  const cursorFill = theme === "dark" ? "#1a1a1a" : "#eef1f5";

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
          <BarChart data={data} margin={{ top: 4, right: 8, left: -4, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke={grid} />
            <XAxis
              dataKey={xKey}
              tick={{ fill: tick, fontSize: 12 }}
              axisLine={{ stroke: grid }}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: tick, fontSize: 12 }}
              axisLine={false}
              tickLine={false}
              width={52}
              allowDecimals={false}
              tickFormatter={compactNumber}
            />
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
              cursor={{ fill: cursorFill }}
            />
            {series.length > 1 ? <Legend wrapperStyle={{ fontSize: 12 }} /> : null}
            {series.map((s, index) => (
              <Bar
                key={s.key}
                dataKey={s.key}
                name={s.label}
                fill={s.color ?? seriesColors[index % seriesColors.length]}
                radius={stacked ? [0, 0, 0, 0] : [4, 4, 0, 0]}
                stackId={stacked ? "stack" : undefined}
                maxBarSize={48}
                animationDuration={700}
                animationEasing="ease-out"
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
