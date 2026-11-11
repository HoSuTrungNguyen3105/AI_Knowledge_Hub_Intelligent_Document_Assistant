"use client";

import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { fetchDashboard } from "../services/dashboard";

export function useDashboard() {
  const [state, setState] = useState({ data: null, loading: true, error: null });
  const [revision, setRevision] = useState(0);
  const retry = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    const controller = new AbortController();
    fetchDashboard(controller.signal)
      .then((data) => { if (!controller.signal.aborted) setState({ data, loading: false, error: null }); })
      .catch((error) => {
        if (!axios.isCancel(error)) setState({ data: null, loading: false, error });
      });
    return () => controller.abort();
  }, [revision]);
  const reload = () => { setState((previous) => ({ ...previous, loading: true, error: null })); retry(); };
  return { ...state, retry: reload };
}
