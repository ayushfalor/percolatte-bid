import { useCallback, useEffect, useState } from "react";

/** Load once and keep refreshing. The UI never computes a number; it only shows what the API returns. */
export function useLive<T>(load: () => Promise<T>, everyMs: number, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const loader = useCallback(load, deps);
  const refresh = useCallback(() => loader().then((d) => (setData(d), setError(null))).catch((e: Error) => setError(e.message)), [loader]);
  useEffect(() => {
    let alive = true;
    const tick = () => {
      if (alive) refresh();
    };
    tick();
    const id = everyMs > 0 ? setInterval(tick, everyMs) : undefined;
    return () => {
      alive = false;
      if (id) clearInterval(id);
    };
  }, [refresh, everyMs]);
  return { data, error, refresh };
}

/** The screen is the URL hash, so a link to any screen works and the back button does too. */
export function useScreen(fallback: string) {
  const read = () => window.location.hash.replace(/^#\/?/, "") || fallback;
  const [screen, setScreen] = useState(read);
  useEffect(() => {
    const on = () => setScreen(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return screen;
}
