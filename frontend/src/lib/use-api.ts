"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * One shape for every data view: loading, success, or a friendly error with a retry. The loader is
 * kept in a ref so a screen can re-run it by changing `key` (a patient id, a day range) without
 * re-fetching on every render.
 */
export type QueryState<T> =
  | { status: "loading"; data: null; message: string }
  | { status: "success"; data: T; message: string }
  | { status: "error"; data: null; message: string };

export function useApi<T>(loader: () => Promise<T>, key: string) {
  const loaderRef = useRef(loader);
  const [state, setState] = useState<QueryState<T>>({
    status: "loading",
    data: null,
    message: "",
  });

  useEffect(() => {
    loaderRef.current = loader;
  });

  const run = useCallback(async () => {
    try {
      const data = await loaderRef.current();
      setState({ status: "success", data, message: "" });
    } catch (error) {
      setState({
        status: "error",
        data: null,
        message:
          error instanceof Error && error.message
            ? error.message
            : "Something went wrong. Please try again.",
      });
    }
  }, []);

  useEffect(() => {
    void run();
  }, [key, run]);

  return { ...state, reload: run };
}
