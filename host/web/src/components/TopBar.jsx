import { fmt } from "../geometry.js";

export default function TopBar({ state }) {
  let camera = ["", "Camera"];
  let signal = ["", "Stud signal"];
  let laser = ["", "Laser"];

  if (state) {
    const L = state.laser;
    camera = [state.fps > 5 ? "good" : "bad", `Camera ${fmt(state.fps, 0)} fps`];
    signal =
      state.signal.source === "serial"
        ? ["good", "Stud signal: Pro Micro"]
        : ["sim", "Stud signal: keyboard"];
    laser = L.simulated
      ? ["sim", "Laser: simulated"]
      : L.calibrated
        ? ["good", "Laser: calibrated"]
        : ["", "Laser: not calibrated"];
  }

  return (
    <header className="topbar">
      <h1 className="brand">Stud Mapper</h1>
      <ul className="status" aria-label="Connections">
        {[camera, signal, laser].map(([cls, text]) => (
          <li key={text.split(":")[0]} className={cls}>
            {text}
          </li>
        ))}
      </ul>
    </header>
  );
}
