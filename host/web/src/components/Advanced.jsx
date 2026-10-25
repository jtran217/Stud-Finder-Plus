import ActivityLog from "./ActivityLog.jsx";

// Tucked-away controls for redoing a step, plus the activity log.
export default function Advanced({ state, command, flow, onChangeSize, onAdjustBox, onRedoLaser, onRepick }) {
  const L = state.laser;
  const object = state.tracker.mode === "object";
  return (
    <details className="advanced">
      <summary>Settings and log</summary>
      <div className="row">
        <button disabled={L.calibrating} onClick={onChangeSize}>Change size</button>
        <button disabled={!state.wall_size_set || L.calibrating} onClick={onAdjustBox}>
          Adjust corners <kbd>C</kbd>
        </button>
        {L.available && (
          <button disabled={!flow.boxDone || L.calibrating} onClick={onRedoLaser}>
            Recalibrate laser <kbd>K</kbd>
          </button>
        )}
        {object && (
          <button disabled={!state.tracker.ready} onClick={onRepick}>
            Pick color again <kbd>T</kbd>
          </button>
        )}
      </div>
      <p className="hint">
        Laser: {L.available ? L.status : "none connected (map only)"}
        {L.x != null && ` · seen at ${L.x.toFixed(2)} in`}
      </p>
      <Diagnostics state={state} />
      <ActivityLog messages={state.messages} />
    </details>
  );
}

// Live numbers for figuring out why something isn't working. The full
// record is in the session log (host/logs/...).
function Diagnostics({ state }) {
  const d = state.diag;
  const c = d.counts;
  const L = d.laser_stats || {};
  const pct = c.frames ? Math.round((100 * c.tracker_seen) / c.frames) : 0;
  return (
    <dl className="diag">
      <dt>Stud finder board</dt>
      <dd>
        {c.S1} edges received · {c.paired} paired · {c.ignored} ignored (not on Scan) · {c.not_seen} ignored
        (finder not tracked)
      </dd>
      <dt>Tracking</dt>
      <dd>
        {state.tracker.x != null ? `seen at ${state.tracker.x.toFixed(2)} in` : `not seen: ${d.tracker_why || "?"}`} · seen in{" "}
        {pct}% of frames
      </dd>
      <dt>Laser line</dt>
      <dd>
        {state.laser.x != null ? `seen at ${state.laser.x.toFixed(2)} in` : `not seen: ${d.laser_why || "?"}`}
        {L.contrast != null && ` · contrast ${L.contrast.toFixed(1)}, ${L.snr.toFixed(0)}× noise`}
        {L.cover != null && `, covers ${Math.round(L.cover * 100)}% of the height`}
      </dd>
      <dt>Session log</dt>
      <dd className="path">{d.log ? `${d.log}/events.log` : "off"}</dd>
    </dl>
  );
}
