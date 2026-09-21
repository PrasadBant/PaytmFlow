import { useEffect, useState } from 'react';

/**
 * Ticks once a second from mount. This is a UI-pacing clock only (which
 * story beat / copy to show) — never fed back into BootGate and never used
 * to fake progress. A 1s interval is cheap enough to keep mounted for
 * minutes without the rAF-loop/expensive-rerender risk called out for this
 * screen.
 */
export function useElapsedSeconds(): number {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const start = Date.now();
    const id = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, []);

  return elapsed;
}
