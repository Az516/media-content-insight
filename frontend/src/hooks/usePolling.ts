/**
 * `usePolling` — periodically invoke an async fetch until a stop
 * predicate fires (task 8.6).
 *
 * Contract:
 *
 * - Calls `fn` immediately on mount, then every `intervalMs`
 *   milliseconds while `shouldStop(data)` returns `false`.
 * - Each invocation is wrapped in a single-shot 5 s timeout (per the
 *   task spec). The timeout error is surfaced in `error` and polling
 *   continues — the design lets the caller decide between displaying
 *   a transient warning and pausing the loop entirely.
 * - On unmount the in-flight timer is cleared so React 18 strict
 *   mode double-mount does not leak intervals.
 * - On non-2xx or network error the most recent successful `data`
 *   stays put so the UI does not flicker to "loading" while the next
 *   tick retries.
 *
 * The hook intentionally does not own retry/backoff policy — callers
 * compose that on top (e.g. TaskDetail pauses polling on error and
 * lets the user press a "retry" button).
 */

import { useEffect, useRef, useState } from 'react';

/** Per-request timeout, requirement 5.3. */
const SINGLE_REQUEST_TIMEOUT_MS = 5_000;

export interface UsePollingResult<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
  /** Imperative refresh (re-runs `fn` immediately, resets the timer). */
  refetch: () => void;
}

function withTimeout<T>(promise: Promise<T>, timeoutMs: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('请求超时')), timeoutMs);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (err) => {
        clearTimeout(timer);
        reject(err);
      },
    );
  });
}

export function usePolling<T>(
  fn: () => Promise<T>,
  intervalMs: number,
  shouldStop: (data: T) => boolean,
): UsePollingResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  // `tick` increments on every manual `refetch()` so the effect re-runs.
  const [tick, setTick] = useState(0);

  // Stable refs to allow the effect to depend ONLY on the inputs we
  // intend to react to (intervalMs + tick). Otherwise a new `fn`
  // identity on every render would restart the polling loop and we'd
  // never reach a steady state.
  const fnRef = useRef(fn);
  const stopRef = useRef(shouldStop);
  useEffect(() => {
    fnRef.current = fn;
    stopRef.current = shouldStop;
  }, [fn, shouldStop]);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const run = async (): Promise<void> => {
      try {
        setLoading(true);
        const value = await withTimeout(fnRef.current(), SINGLE_REQUEST_TIMEOUT_MS);
        if (cancelled) return;
        setData(value);
        setError(null);
        if (stopRef.current(value)) {
          // Steady state reached. Stop scheduling further runs.
          return;
        }
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err : new Error(String(err)));
        // Keep the previous `data` snapshot visible so the UI does
        // not blank out on a transient network blip.
      } finally {
        if (!cancelled) setLoading(false);
      }
      if (!cancelled) {
        timer = setTimeout(run, intervalMs);
      }
    };

    void run();

    return () => {
      cancelled = true;
      if (timer != null) clearTimeout(timer);
    };
  }, [intervalMs, tick]);

  const refetch = (): void => setTick((t) => t + 1);

  return { data, loading, error, refetch };
}

export default usePolling;
