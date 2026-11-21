import React from "react";

interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  isPositive?: boolean;
  className?: string;
}

export const Sparkline: React.FC<SparklineProps> = ({
  data,
  width = 100,
  height = 28,
  isPositive = true,
  className = "",
}) => {
  if (!data || data.length < 2) {
    return (
      <div className={`w-[${width}px] h-[${height}px] bg-muted/40 rounded flex items-center justify-center text-[10px] text-text-tertiary`}>
        --
      </div>
    );
  }

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const padding = 2;
  const usableHeight = height - padding * 2;
  const stepX = (width - padding * 2) / (data.length - 1);

  const points = data.map((val, idx) => {
    const x = padding + idx * stepX;
    const y = height - padding - ((val - min) / range) * usableHeight;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const pathD = `M ${points.join(" L ")}`;
  const strokeColor = isPositive ? "var(--color-success)" : "var(--color-error)";
  const startVal = data[0].toFixed(2);
  const endVal = data[data.length - 1].toFixed(2);
  const ariaLabel = `7-day trend starting at ${startVal} and ending at ${endVal}, trending ${isPositive ? "up" : "down"}`;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={`overflow-visible ${className}`}
      role="img"
      aria-label={ariaLabel}
    >
      <title>{ariaLabel}</title>
      <path
        d={pathD}
        fill="none"
        stroke={strokeColor}
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
};
