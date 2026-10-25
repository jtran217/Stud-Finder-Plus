import { useEffect, useRef, useState } from "react";

const SHOW_MS = 2800;

// Returns the stud that was just found (for a few seconds), or null.
// The server bumps found.seq each time a stud is added or refined.
export function useFoundFlash(state) {
  const [flash, setFlash] = useState(null);
  const lastSeq = useRef(null);
  const found = state?.found;

  useEffect(() => {
    if (!found) return;
    if (lastSeq.current === null) {
      lastSeq.current = found.seq; // don't flash old studs on page load
      return;
    }
    if (found.seq === lastSeq.current || found.index == null) return;
    lastSeq.current = found.seq;
    const stud = state.studs[found.index];
    if (!stud) return;
    setFlash({ ...found, seq: found.seq, center: stud.center, n: stud.n });
    const t = setTimeout(() => setFlash(null), SHOW_MS);
    return () => clearTimeout(t);
  }, [found?.seq]); // eslint-disable-line react-hooks/exhaustive-deps

  return flash;
}
