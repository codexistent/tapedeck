/** Pass rate (0-1) over runs, oldest to newest. Regressed runs are marked. */
export function Sparkline({
  points,
  width = 160,
  height = 28,
  label,
}: {
  points: { rate: number; regressed: boolean }[];
  width?: number;
  height?: number;
  label: string;
}) {
  if (points.length === 0) return null;
  const pad = 3;
  const x = (i: number) =>
    points.length === 1 ? width / 2 : pad + (i * (width - 2 * pad)) / (points.length - 1);
  const y = (r: number) => pad + (1 - r) * (height - 2 * pad);
  const d = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(p.rate).toFixed(1)}`).join(" ");
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
      <line x1={pad} x2={width - pad} y1={y(1)} y2={y(1)} stroke="var(--rule)" />
      <path d={d} fill="none" stroke="var(--accent)" strokeWidth="1.6" />
      {points.map((p, i) =>
        p.regressed ? <circle key={i} cx={x(i)} cy={y(p.rate)} r="3" fill="var(--bad)" /> : null,
      )}
      <circle cx={x(points.length - 1)} cy={y(points[points.length - 1].rate)} r="2.4" fill="var(--accent)" />
    </svg>
  );
}
