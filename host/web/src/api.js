import { useCallback, useEffect, useRef, useState } from "react";

const POLL_MS = 150;

async function post(path, body) {
  await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// Polls /api/state. `refresh` fetches right away (used after a command).
export function useServerState() {
  const [state, setState] = useState(null);
  const [online, setOnline] = useState(true);
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch("/api/state", { cache: "no-store" });
      const data = await res.json();
      if (alive.current) {
        setState(data);
        setOnline(true);
      }
    } catch {
      if (alive.current) setOnline(false);
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    let timer;
    const loop = async () => {
      await refresh();
      if (alive.current) timer = setTimeout(loop, POLL_MS);
    };
    loop();
    return () => {
      alive.current = false;
      clearTimeout(timer);
    };
  }, [refresh]);

  const command = useCallback(
    (name, arg) => post("/api/command", { name, arg }).then(refresh, () => {}),
    [refresh]
  );
  const click = useCallback(
    (x, y) => post("/api/click", { x, y }).then(refresh, () => {}),
    [refresh]
  );

  return { state, online, command, click };
}
