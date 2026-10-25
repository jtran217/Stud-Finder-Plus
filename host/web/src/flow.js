// step comes from the server (state.flow) so multiple tabs stay in sync
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
    laserCanStart:
      stage === "calibrate" && sizeDone && f.box_done && f.laser_needed && !f.laser_done && !state.laser.calibrating,
  };
}
