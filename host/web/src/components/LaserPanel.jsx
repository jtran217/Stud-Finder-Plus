import { fmt } from "../geometry.js";

export default function LaserPanel({ state, command }) {
  const L = state.laser;
  // Calibrating only needs the wall box, not the stud finder's color.
  const boxReady = state.wall_size_set && state.clicks >= 4;
  const status = L.x == null && !L.calibrating ? `Laser line not in view. ${L.status}` : L.status;

  return (
    <section className="block" aria-labelledby="h-laser">
      <h2 id="h-laser">Laser</h2>
      <p className={`readout small${L.x == null ? " lost" : ""}`}>
        {fmt(L.x, 2)}
        <span className="unit">in</span>
      </p>
      <p className="sub">{status}</p>
      <p className="aim">{L.aim_status}</p>
      <div className="row">
        <button disabled={!boxReady || L.calibrating} onClick={() => command("laser_calibrate")}>
          Calibrate <kbd>K</kbd>
        </button>
        <button
          className="primary"
          disabled={!L.calibrated || !state.studs.length || L.calibrating}
          onClick={() => command("next_stud")}
        >
          Next stud <kbd>N</kbd>
        </button>
        <button className={L.on ? "is-on" : undefined} onClick={() => command("laser_toggle")}>
          {L.on ? "Laser off" : "Laser on"} <kbd>L</kbd>
        </button>
      </div>
    </section>
  );
}
