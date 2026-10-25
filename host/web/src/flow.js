// The 3 steps. The server decides which step is on screen (state.flow), so
// every open tab shows the same one and agrees on whether studs are being
// detected. The page only adds what's purely visual (the size form open).
//   1 calibrate: scan-area size -> box on the tape crosses -> laser sweep
//   2 finder:    pick the stud finder's color (or see its marker)
//   3 scan:      sweep the wall (stud detection only runs here)
export const STAGES = [
  { id: "calibrate", label: "Calibrate" },
  { id: "finder", label: "Stud finder" },
  { id: "scan", label: "Scan" },
];

export function getFlow(state, { editSize }) {
  const f = state.flow;
  const stage = editSize ? "calibrate" : f.stage;
  const sizeDone = f.size_done && !editSize;
  return {
    stage,
    stageIndex: STAGES.findIndex((s) => s.id === stage),
    allowedIndex: f.allowed_index,
    calibrated: f.calibrated && !editSize,
    finderReady: f.finder_ready,
    sizeDone,
    boxDone: f.box_done,
    laserNeeded: f.laser_needed,
    laserDone: f.laser_done,
    laserFailed: f.laser_failed,
    // Space / Enter start the laser sweep when this is true
    laserCanStart:
      stage === "calibrate" && sizeDone && f.box_done && f.laser_needed && !f.laser_done && !state.laser.calibrating,
  };
}
