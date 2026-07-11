import { useCallback, useRef, useState } from "react";

export function useAsyncGuard() {
  const inFlightRef = useRef(false);
  const [busy, setBusy] = useState(false);

  const run = useCallback(async <T>(operation: () => Promise<T>): Promise<T | undefined> => {
    if (inFlightRef.current) {
      return undefined;
    }

    inFlightRef.current = true;
    setBusy(true);
    try {
      return await operation();
    } finally {
      inFlightRef.current = false;
      setBusy(false);
    }
  }, []);

  const isRunning = useCallback(() => inFlightRef.current, []);

  return { busy, run, isRunning };
}
