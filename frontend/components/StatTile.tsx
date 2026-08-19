import type { ReactNode } from "react";

interface StatTileProps {
  label: string;
  value: ReactNode;
  icon: ReactNode;
  accent: "blue" | "teal" | "amber" | "purple" | "rose";
  foot?: ReactNode;
}

/** A single dashboard number: label, big value, coloured icon, optional footnote. */
export function StatTile({ label, value, icon, accent, foot }: StatTileProps) {
  return (
    <div className={`card stat stat--accent-${accent}`}>
      <div className="stat__top">
        <span className="stat__label">{label}</span>
        <span className="stat__icon">{icon}</span>
      </div>
      <div className="stat__value">{value}</div>
      {foot ? <div className="stat__foot">{foot}</div> : null}
    </div>
  );
}

export function StatTileSkeleton() {
  return (
    <div className="card stat">
      <div className="stat__top">
        <span className="skeleton skeleton-row" style={{ width: "50%" }} />
        <span className="skeleton" style={{ width: 30, height: 30, borderRadius: 8 }} />
      </div>
      <span className="skeleton skeleton-row" style={{ width: "35%", height: 32, marginTop: 4 }} />
    </div>
  );
}
