// Live view of the laser calibration: the wall as a strip, the red line where
// the camera sees the laser right now, and a dot for each measured point.
const VW = 320;
const PAD = 10;

export default function LaserSweep({ state }) {
  const L = state.laser;
  const { x0, x1 } = state.wall;
  const span = x1 - x0 || 1;
  const sx = (x) => PAD + ((Math.min(Math.max(x, x0), x1) - x0) / span) * (VW - 2 * PAD);

  const measuring = L.phase === "measure" || L.phase === "preload";
  const total = L.points.length + L.todo + (L.phase === "measure" ? 1 : 0);
  const pct = L.calibrating
    ? measuring && total
      ? Math.round((L.points.length / total) * 100)
      : null
    : L.points.length
      ? 100
      : 0;

  let label;
  if (L.calibrating) label = measuring ? `Measuring point ${L.points.length + 1} of ${total}` : "Finding the edges of the wall";
  else if (L.points.length) label = `${L.points.length} points measured, ${Math.min(...L.points).toFixed(1)}–${Math.max(...L.points).toFixed(1)} in`;
  else label = "Not calibrated yet";

  return (
    <div className="laser-sweep" role="status">
      <svg viewBox={`0 0 ${VW} 54`} className="sweep-svg" aria-hidden="true">
        <rect x={PAD} y="4" width={VW - 2 * PAD} height="38" className="sweep-wall" />
        {L.points.map((x, i) => (
          <g key={i} className="sweep-point">
            <line x1={sx(x)} x2={sx(x)} y1="4" y2="42" />
            <circle cx={sx(x)} cy="23" r="4" />
          </g>
        ))}
        {L.x != null && (
          <line className={`sweep-live${L.calibrating ? " moving" : ""}`} x1={sx(L.x)} x2={sx(L.x)} y1="2" y2="44" />
        )}
        <text x={PAD} y="53" className="sweep-tick">
          {x0}″
        </text>
        <text x={VW - PAD} y="53" textAnchor="end" className="sweep-tick">
          {x1}″
        </text>
      </svg>
      <div className={`sweep-bar${pct == null ? " indeterminate" : ""}`}>
        <span style={pct == null ? undefined : { width: `${pct}%` }} />
      </div>
      <p className="sweep-label">
        <strong>{label}</strong>
        {L.calibrating && (L.x == null ? " · laser not in view" : ` · laser at ${L.x.toFixed(1)} in`)}
      </p>
    </div>
  );
}
