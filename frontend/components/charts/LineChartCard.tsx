"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { compactNumber, useChartPalette } from "@/lib/chartColors";

export interface LineSeries {
  key: string;
  label: string;
  color?: string;
}

interface LineChartCardProps {
  title: string;
  subtitle?: string;
  data: Array<Record<string, string | number | null>>;
  xKey: string;
  series: LineSeries[];
  height?: number;
  unit?: string;
}

/** A trend across an ordered sequence — semesters, months — never a bare
 * area fill (that reads as a magnitude, not a path), always with visible
 * dots so even a two-point run reads as data rather than a rendering
 * glitch. `connectNulls` so one missing period doesn't sever the line. */
export function LineChartCard({
  title,
  subtitle,
  data,
  xKey,
  series,
  height = 260,
  unit,
}: LineChartCardProps) {
  const hasValues = data.some((row) => series.some((s) => row[s.key] !== null && row[s.key] !== undefined));
  const { series: seriesColors, grid, tick } = useChartPalette();

  return (
    <div className="card chart-card">
      <div className="chart-card__header">
        <div>
          <h3 className="chart-card__title">{title}</h3>
          {subtitle ? <p className="chart-card__subtitle">{subtitle}</p> : null}
        </div>
      </div>
      {data.length === 0 || !hasValues ? (
        <div className="chart-empty">No data yet.</div>
      ) : (
        <ResponsiveContainer width="100%" height={height}>
          <LineChart data={data} margin={{ top: 4, right: 8, left: -4, bottom: 0 }}>
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
              tickFormatter={(value) => `${compactNumber(value)}${unit ?? ""}`}
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
            />
            {series.length > 1 ? <Legend wrapperStyle={{ fontSize: 12 }} /> : null}
            {series.map((s, index) => {
              const color = s.color ?? seriesColors[index % seriesColors.length];
              return (
                <Line
                  key={s.key}
                  type="monotone"
                  dataKey={s.key}
                  name={s.label}
                  stroke={color}
                  strokeWidth={2.5}
                  dot={{ r: 4, strokeWidth: 0, fill: color }}
                  activeDot={{ r: 6 }}
                  connectNulls
                  animationDuration={700}
                  animationEasing="ease-out"
                />
              );
            })}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
