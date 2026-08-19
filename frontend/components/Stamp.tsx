/**
 * A circular "seal" for a status meant to read as an official decision —
 * ported from the UI/UX reference generated in Figma. Rendered as a dashed
 * outer ring + a solid inner ring, like a rubber stamp, so it reads as a
 * document metaphor rather than another coloured pill.
 */

type StampStatus = "verified" | "hold" | "pending";

const STAMP_LABEL: Record<StampStatus, string> = {
  verified: "Verified",
  hold: "On hold",
  pending: "Pending",
};

const SIZES = {
  sm: { outer: 64, inner: 52, font: 9 },
  md: { outer: 88, inner: 72, font: 10.5 },
  lg: { outer: 112, inner: 92, font: 12.5 },
} as const;

interface StampProps {
  status: StampStatus;
  size?: keyof typeof SIZES;
  label?: string;
  rotation?: number;
}

export function Stamp({ status, size = "md", label, rotation }: StampProps) {
  const s = SIZES[size];
  const rot = rotation ?? (status === "hold" ? -3 : status === "pending" ? 2 : 3);
  const text = (label ?? STAMP_LABEL[status]).toUpperCase();

  return (
    <div
      className={`stamp stamp--${status}`}
      style={{ transform: `rotate(${rot}deg)`, width: s.outer, height: s.outer }}
      role="img"
      aria-label={text}
    >
      <svg width={s.outer} height={s.outer} viewBox={`0 0 ${s.outer} ${s.outer}`}>
        <circle
          cx={s.outer / 2}
          cy={s.outer / 2}
          r={s.outer / 2 - 2}
          fill="currentColor"
          fillOpacity={0.08}
          stroke="currentColor"
          strokeWidth={2}
          strokeDasharray="4 3"
        />
        <circle
          cx={s.outer / 2}
          cy={s.outer / 2}
          r={s.inner / 2}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.5}
        />
        <text
          x={s.outer / 2}
          y={s.outer / 2 + s.font * 0.4}
          textAnchor="middle"
          fill="currentColor"
          fontSize={s.font}
          fontWeight={700}
          fontFamily="'Plus Jakarta Sans', sans-serif"
          letterSpacing={1}
          textLength={s.inner * 0.72}
          lengthAdjust="spacingAndGlyphs"
        >
          {text}
        </text>
      </svg>
    </div>
  );
}

export type { StampStatus };
