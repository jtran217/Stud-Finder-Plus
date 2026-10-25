// The 3 steps, and how far the user is allowed to go.
//   1 calibrate: scan-area size -> box on the tape crosses -> laser sweep
//   2 finder:    pick the stud finder's color (or see its marker)
//   3 scan:      sweep the wall (stud detection only runs here)
// The user can move between any steps they've reached; changing something
// in an earlier step (e.g. the box) pulls them back to it.
export const STAGES = [
  { id: "calibrate", label: "Calibrate" },
  { id: "finder", label: "Stud finder" },
  { id: "scan", label: "Scan" },
];

export function getFlow(state, { laserSkipped, editSize, seenFinder, view }) {
  const L = state.laser;
  const sizeDone = state.wall_size_set && !editSize;
  const boxDone = state.wall_size_set && state.clicks >= 4;
  const laserNeeded = L.available && !laserSkipped;
  // A calibration loaded from last time doesn't count: sweep once per launch.
  const laserDone = !laserNeeded || (L.calibrated_this_run && !L.calibrating);
  const laserFailed = !L.calibrating && !L.calibrated && /fail/i.test(L.status);
  const finderReady = state.tracker.ready && (state.tracker.mode === "object" || seenFinder);

  const calibrated = sizeDone && boxDone && laserDone;
  // furthest step the user may open
  const allowedIndex = !calibrated ? 0 : !finderReady ? 1 : 2;
  const viewIndex = Math.min(STAGES.findIndex((s) => s.id === view), allowedIndex);
  const stage = STAGES[Math.max(viewIndex, 0)].id;

  return {
    stage,
    stageIndex: Math.max(viewIndex, 0),
    allowedIndex,
    calibrated,
    finderReady,
    sizeDone,
    boxDone,
    laserNeeded,
    laserDone,
    laserFailed,
    // Space / Enter start the laser sweep when this is true
    laserCanStart: stage === "calibrate" && sizeDone && boxDone && laserNeeded && !L.calibrating && !laserDone,
  };
}
