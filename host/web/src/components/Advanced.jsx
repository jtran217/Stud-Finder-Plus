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
      <ActivityLog messages={state.messages} />
    </details>
  );
}
