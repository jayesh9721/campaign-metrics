"use client";

export interface SparklinePoint {
  date: string;
  value: number | null;
}

// Lightweight inline-SVG line chart — avoids pulling in a charting library
// for a single trailing-30-day sparkline (hackathon scope).
export default function Sparkline({
  data,
  highlightDate,
  width = 640,
  height = 180,
}: {
  data: SparklinePoint[];
  highlightDate?: string;
  width?: number;
  height?: number;
}) {
  const values = data.map((d) => d.value).filter((v): v is number => v !== null && !Number.isNaN(v));

  if (values.length === 0) {
    return <div className="p-4 text-sm text-slate-400 dark:text-slate-500">No metric history available.</div>;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const padding = 28;
  const innerW = width - padding * 2;
  const innerH = height - padding * 2;
  const n = data.length;

  const points = data.map((d, i) => {
    const x = padding + (n === 1 ? innerW / 2 : (i / (n - 1)) * innerW);
    const v = d.value ?? min;
    const y = padding + innerH - ((v - min) / range) * innerH;
    return { x, y, ...d };
  });

  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full text-blue-500 dark:text-blue-400" style={{ maxHeight: height }}>
      <line x1={padding} y1={padding} x2={padding} y2={height - padding} stroke="currentColor" strokeOpacity={0.15} />
      <line
        x1={padding}
        y1={height - padding}
        x2={width - padding}
        y2={height - padding}
        stroke="currentColor"
        strokeOpacity={0.15}
      />
      <text x={padding} y={padding - 8} fontSize={10} fill="currentColor" opacity={0.6}>
        {max.toLocaleString(undefined, { maximumFractionDigits: 2 })}
      </text>
      <text x={padding} y={height - padding + 16} fontSize={10} fill="currentColor" opacity={0.6}>
        {min.toLocaleString(undefined, { maximumFractionDigits: 2 })}
      </text>
      <path d={path} fill="none" stroke="currentColor" strokeWidth={2} />
      {points.map((p, i) => {
        const isAnomaly = highlightDate && p.date === highlightDate;
        return (
          <circle
            key={i}
            cx={p.x}
            cy={p.y}
            r={isAnomaly ? 5 : 2}
            className={isAnomaly ? "fill-red-500 stroke-red-500" : "fill-current"}
          />
        );
      })}
    </svg>
  );
}
