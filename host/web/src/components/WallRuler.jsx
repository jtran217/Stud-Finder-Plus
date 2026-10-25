// Top-down strip of the scan area: studs as lumber, where the stud finder is,
// the edge waiting for its pair, and where the laser line is.
const VW = 320;
const PAD = 12;
const TOP = 16;
const BOT = 58;

export default function WallRuler({ state, flash }) {
  const { x0, x1 } = state.wall;
  const span = x1 - x0 || 1;
  const sx = (x) => PAD + ((x - x0) / span) * (VW - 2 * PAD);
  const inside = (x) => x != null && x >= x0 - 1 && x <= x1 + 1;

  const minor = span <= 48 ? 1 : span <= 120 ? 2 : 6;
  const major = span <= 24 ? 6 : 12;
  const ticks = [];
  for (let v = Math.ceil(x0 / minor) * minor; v <= x1 + 1e-6; v += minor) ticks.push(v);

  const finder = state.tracker.x;
  const laser = state.laser.x;
  const aimed = state.laser.aim_index;

  return (
    <svg className="ruler" viewBox={`0 0 ${VW} 84`} role="img" aria-label="Map of the studs found on the wall">
      <rect x={PAD} y={TOP} width={VW - 2 * PAD} height={BOT - TOP} className="ruler-wall" />

      {state.studs.map((s, i) => {
        const l = sx(s.left);
        const w = Math.max(sx(s.right) - l, 3);
        const cls = ["ruler-stud", i === aimed && "aimed", flash && flash.index === i && "flash"]
          .filter(Boolean)
          .join(" ");
        return (
          <g key={i} className={cls}>
            <rect x={l} y={TOP} width={w} height={BOT - TOP} />
            <line x1={sx(s.center)} x2={sx(s.center)} y1={TOP} y2={BOT} />
            <text x={sx(s.center)} y={TOP - 4} textAnchor="middle">
              {i + 1}
            </text>
          </g>
        );
      })}

      {state.open_edges.filter((e) => inside(e.x)).map((e, i) => (
        <g key={i} className="ruler-edge">
          <line x1={sx(e.x)} x2={sx(e.x)} y1={TOP - 2} y2={BOT + 2} />
          {e.dir !== 0 && (
            <path d={`M${sx(e.x)} ${(TOP + BOT) / 2} l${-e.dir * 6} -4 v8 z`} />
          )}
        </g>
      ))}
      {inside(laser) && <line className="ruler-laser" x1={sx(laser)} x2={sx(laser)} y1={TOP} y2={BOT} />}
      {inside(finder) && (
        <g className="ruler-finder" transform={`translate(${sx(finder)} 0)`}>
          <line x1="0" x2="0" y1={TOP} y2={BOT} />
          <path d={`M0 ${BOT - 1} l-5 8 h10 z`} />
        </g>
      )}

      {ticks.map((v) => {
        const big = Math.abs(v % major) < 1e-6;
        return (
          <g key={v} className="ruler-tick">
            <line x1={sx(v)} x2={sx(v)} y1={BOT + 8} y2={BOT + (big ? 14 : 11)} />
            {big && (
              <text x={sx(v)} y={BOT + 24} textAnchor="middle">
                {v}″
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
