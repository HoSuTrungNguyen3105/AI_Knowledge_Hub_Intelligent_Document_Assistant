"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { compareService } from "../services/compare";
import { compareErrorFromEvent, getCompareError } from "../utils/compare";
import { useNotice } from "../stores/notice";

// Parallel multi-model comparison. Each run streams into its own column; one
// provider failing never aborts the others. Loading is derived from revisions so
// effects never call setState synchronously (react-hooks/set-state-in-effect).
export function useCompare() {
  const [activeId, setActiveId] = useState(null);
  const [listRevision, setListRevision] = useState(0);
  const [listState, setListState] = useState({ items: [], error: "", revision: -1 });
  const [detailRevision, setDetailRevision] = useState(0);
  const [detailState, setDetailState] = useState({ id: null, data: null, error: "", revision: -1 });
  const [runText, setRunText] = useState({});
  const [synthesisText, setSynthesisText] = useState("");
  const [phase, setPhase] = useState(null);
  const [streamError, setStreamError] = useState("");
  const [busy, setBusy] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const abortRef = useRef(null);
  const mounted = useRef(true);
  const show = useNotice((state) => state.show);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; abortRef.current?.abort(); };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const revision = listRevision;
    compareService.list(controller.signal)
      .then((items) => { if (!controller.signal.aborted) setListState({ items, error: "", revision }); })
      .catch((error) => { if (!axios.isCancel(error)) setListState((state) => ({ ...state, error: getCompareError(error), revision })); });
    return () => controller.abort();
  }, [listRevision]);

  useEffect(() => {
    if (!activeId) return;
    const controller = new AbortController();
    const id = activeId;
    const revision = detailRevision;
    compareService.get(id, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        setDetailState({ id, data, error: "", revision });
        setRunText({});
        setSynthesisText("");
        setStreamError("");
      })
      .catch((error) => {
        if (axios.isCancel(error)) return;
        setDetailState({ id, data: null, error: getCompareError(error), revision });
      });
    return () => controller.abort();
  }, [activeId, detailRevision]);

  const comparisons = {
    items: listState.items,
    loading: listState.revision !== listRevision,
    error: listState.error,
  };
  const detailLoading = Boolean(activeId) && (detailState.id !== activeId || detailState.revision !== detailRevision);
  const comparison = detailState.id === activeId ? detailState.data : null;
  const detailError = detailState.id === activeId ? detailState.error : "";

  const stop = useCallback(() => { abortRef.current?.abort(); }, []);

  function patchRun(run) {
    setDetailState((state) => state.data
      ? { ...state, data: { ...state.data, runs: state.data.runs.map((item) => (item.id === run.id ? run : item)) } }
      : state);
  }

  function handleExecuteEvent(event) {
    if (event.event === "comparison" || event.event === "done") {
      setDetailState((state) => ({ ...state, data: event.data.comparison }));
      if (event.event === "done") setRunText({});
    } else if (event.event === "run_delta") {
      const { run_id: runId, text } = event.data;
      setRunText((prev) => ({ ...prev, [runId]: (prev[runId] || "") + text }));
    } else if (event.event === "run_done" || event.event === "run_error") {
      patchRun(event.data.run);
      setRunText((prev) => { const next = { ...prev }; delete next[event.data.run.id]; return next; });
      if (event.event === "run_error") setStreamError(compareErrorFromEvent({ code: event.data.run.error_code }));
    }
  }

  function handleSynthesisEvent(event) {
    if (event.event === "synthesis_delta") {
      setSynthesisText((prev) => prev + event.data.text);
    } else if (event.event === "synthesis_done") {
      setDetailState((state) => state.data ? { ...state, data: { ...state.data, synthesis: event.data.synthesis } } : state);
      setSynthesisText("");
    } else if (event.event === "synthesis_error") {
      setStreamError(compareErrorFromEvent(event.data));
    } else if (event.event === "done") {
      setDetailState((state) => ({ ...state, data: event.data.comparison }));
      setSynthesisText("");
    }
  }

  function runStream(start, onEvent, kind) {
    if (abortRef.current) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setStreamError("");
    setPhase(kind);
    if (kind === "execute") setRunText({});
    else setSynthesisText("");
    start(controller.signal, onEvent)
      .catch((error) => {
        if (controller.signal.aborted) {
          // The backend persists a "stopped" run; reload to show the saved state.
          setRunText({});
          setSynthesisText("");
          if (mounted.current) setDetailRevision((value) => value + 1);
        } else {
          setStreamError(getCompareError(error));
        }
      })
      .finally(() => {
        abortRef.current = null;
        if (mounted.current) { setPhase(null); setListRevision((value) => value + 1); }
      });
  }

  function execute() {
    if (!activeId || abortRef.current) return;
    runStream(
      (signal, onEvent) => compareService.execute(activeId, { signal, onEvent }),
      handleExecuteEvent,
      "execute",
    );
  }

  function synthesize(payload) {
    if (!activeId || abortRef.current) return;
    runStream(
      (signal, onEvent) => compareService.synthesize(activeId, payload, { signal, onEvent }),
      handleSynthesisEvent,
      "synthesize",
    );
  }

  async function createComparison(payload) {
    if (busy) return;
    setBusy("create");
    try {
      const created = await compareService.create(payload);
      if (!mounted.current) return;
      stop();
      setStreamError("");
      setActiveId(created.id);
      setListRevision((value) => value + 1);
      show("Đã tạo phép so sánh mới.");
    } catch (error) {
      if (mounted.current) show(getCompareError(error), "error");
    } finally {
      if (mounted.current) setBusy("");
    }
  }

  async function deleteComparison() {
    if (!activeId || busy) return;
    setBusy("delete");
    try {
      await compareService.remove(activeId);
      if (!mounted.current) return;
      stop();
      setActiveId(null);
      setConfirmDelete(false);
      setListRevision((value) => value + 1);
      show("Đã xóa phép so sánh và toàn bộ kết quả của nó.");
    } catch (error) {
      if (mounted.current) show(getCompareError(error), "error");
    } finally {
      if (mounted.current) setBusy("");
    }
  }

  function selectComparison(id) {
    if (id === activeId) return;
    stop();
    setConfirmDelete(false);
    setStreamError("");
    setActiveId(id);
  }

  function newComparison() {
    stop();
    setConfirmDelete(false);
    setStreamError("");
    setActiveId(null);
  }

  const successfulRuns = comparison?.runs?.filter((run) => run.status === "success" && run.content) ?? [];

  return {
    comparisons,
    activeId,
    comparison,
    detailLoading,
    detailError,
    runText,
    synthesisText,
    phase,
    isStreaming: phase !== null,
    streamError,
    busy,
    confirmDelete,
    setConfirmDelete,
    canExecute: Boolean(comparison) && !detailLoading && phase === null,
    canSynthesize: successfulRuns.length > 0 && phase === null,
    selectComparison,
    newComparison,
    createComparison,
    execute,
    synthesize,
    stop,
    deleteComparison,
    reloadList: () => setListRevision((value) => value + 1),
    reloadDetail: () => setDetailRevision((value) => value + 1),
  };
}