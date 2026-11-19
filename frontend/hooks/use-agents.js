"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { agentsService } from "../services/agents";
import { agentErrorFromEvent, applyExecutionEvent, getAgentError } from "../utils/agents";
import { useNotice } from "../stores/notice";

export function useAgents() {
  const [activeId, setActiveId] = useState(null);
  const [activeExecutionId, setActiveExecutionId] = useState(null);
  const [revisions, setRevisions] = useState({ list: 0, tools: 0, detail: 0, history: 0, execution: 0 });
  const revisionRef = useRef(revisions);
  const [listState, setListState] = useState({ items: [], error: "", revision: -1 });
  const [toolsState, setToolsState] = useState({ items: [], error: "", revision: -1 });
  const [detailState, setDetailState] = useState({ id: null, data: null, error: "", revision: -1 });
  const [historyState, setHistoryState] = useState({ id: null, items: [], error: "", revision: -1 });
  const [executionState, setExecutionState] = useState({ agentId: null, id: null, data: null, error: "", revision: -1 });
  const [live, setLive] = useState(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamError, setStreamError] = useState("");
  const [busy, setBusy] = useState("");
  const [editing, setEditing] = useState(false);
  const [deletion, setDeletion] = useState(null);
  const mounted = useRef(true);
  const context = useRef({ id: null, session: 0, executionId: null });
  const streamRef = useRef(null);
  const mutationRef = useRef(null);
  const show = useNotice((state) => state.show);

  const bump = useCallback((name) => {
    revisionRef.current = { ...revisionRef.current, [name]: revisionRef.current[name] + 1 };
    setRevisions(revisionRef.current);
  }, []);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      streamRef.current?.controller.abort();
      streamRef.current = null;
      mutationRef.current?.controller.abort();
      mutationRef.current = null;
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const revision = revisions.list;
    const valid = () => mounted.current && !controller.signal.aborted && revisionRef.current.list === revision;
    agentsService.list(controller.signal)
      .then((items) => { if (valid()) setListState({ items, error: "", revision }); })
      .catch((error) => { if (valid()) setListState((state) => ({ ...state, error: getAgentError(error), revision })); });
    return () => controller.abort();
  }, [revisions.list]);

  useEffect(() => {
    const controller = new AbortController();
    const revision = revisions.tools;
    const valid = () => mounted.current && !controller.signal.aborted && revisionRef.current.tools === revision;
    agentsService.tools(controller.signal)
      .then((items) => { if (valid()) setToolsState({ items, error: "", revision }); })
      .catch((error) => { if (valid()) setToolsState({ items: [], error: getAgentError(error), revision }); });
    return () => controller.abort();
  }, [revisions.tools]);

  useEffect(() => {
    if (!activeId) return;
    const controller = new AbortController();
    const session = context.current.session;
    const revision = revisions.detail;
    const valid = () => mounted.current && !controller.signal.aborted && context.current.id === activeId && context.current.session === session && revisionRef.current.detail === revision;
    agentsService.get(activeId, controller.signal)
      .then((data) => { if (valid()) setDetailState({ id: activeId, data, error: "", revision }); })
      .catch((error) => { if (valid()) setDetailState({ id: activeId, data: null, error: getAgentError(error), revision }); });
    return () => controller.abort();
  }, [activeId, revisions.detail]);

  useEffect(() => {
    if (!activeId) return;
    const controller = new AbortController();
    const session = context.current.session;
    const revision = revisions.history;
    const valid = () => mounted.current && !controller.signal.aborted && context.current.id === activeId && context.current.session === session && revisionRef.current.history === revision;
    agentsService.executions(activeId, controller.signal)
      .then((items) => { if (valid()) setHistoryState({ id: activeId, items, error: "", revision }); })
      .catch((error) => { if (valid()) setHistoryState({ id: activeId, items: [], error: getAgentError(error), revision }); });
    return () => controller.abort();
  }, [activeId, revisions.history]);

  const liveSelected = Boolean(live && live.agent_id === activeId && (live.id === activeExecutionId || (isStreaming && !live.id)));
  useEffect(() => {
    if (!activeId || !activeExecutionId || liveSelected || isStreaming) return;
    const controller = new AbortController();
    const session = context.current.session;
    const revision = revisions.execution;
    const valid = () => mounted.current && !controller.signal.aborted && context.current.id === activeId && context.current.session === session && context.current.executionId === activeExecutionId && revisionRef.current.execution === revision;
    agentsService.execution(activeId, activeExecutionId, controller.signal)
      .then((data) => { if (valid()) setExecutionState({ agentId: activeId, id: activeExecutionId, data, error: "", revision }); })
      .catch((error) => { if (valid()) setExecutionState({ agentId: activeId, id: activeExecutionId, data: null, error: getAgentError(error), revision }); });
    return () => controller.abort();
  }, [activeId, activeExecutionId, revisions.execution, liveSelected, isStreaming]);

  function stop() {
    const stream = streamRef.current;
    if (!stream) return;
    // Invalidate before abort: queued events and finally handlers cannot touch a
    // replacement stream, even when the transport resolves rather than rejects.
    streamRef.current = null;
    stream.controller.abort();
    if (!mounted.current) return;
    setIsStreaming(false);
    setLive({ ...stream.execution, status: "stopped" });
    setStreamError("Đã gửi yêu cầu dừng. Tải lại lịch sử để xem trạng thái được máy chủ lưu.");
    bump("history");
    bump("list");
  }

  function selectAgent(id) {
    stop();
    context.current = { id, session: context.current.session + 1, executionId: null };
    setActiveId(id);
    setActiveExecutionId(null);
    setLive(null);
    setStreamError("");
    setEditing(false);
    setDeletion(null);
    // Revisiting the same agent must fetch current persisted state too.
    bump("detail");
    bump("history");
    bump("execution");
  }

  function selectExecution(id) {
    stop();
    context.current.executionId = id;
    setActiveExecutionId(id);
    setLive(null);
    setStreamError("");
    setDeletion(null);
    bump("execution");
  }

  async function mutate(kind, request, onSuccess) {
    if (mutationRef.current || streamRef.current) return false;
    const operation = { controller: new AbortController(), session: context.current.session };
    mutationRef.current = operation;
    setBusy(kind);
    try {
      const data = await request(operation.controller.signal);
      if (!mounted.current || operation.controller.signal.aborted) return false;
      bump("list");
      if (context.current.session === operation.session) onSuccess(data);
      return true;
    } catch (error) {
      if (mounted.current && !operation.controller.signal.aborted && context.current.session === operation.session) show(getAgentError(error), "error");
      return false;
    } finally {
      if (mutationRef.current === operation) {
        mutationRef.current = null;
        if (mounted.current) setBusy("");
      }
    }
  }

  function saveAgent(payload) {
    const id = context.current.id;
    return mutate(id ? "save" : "create", (signal) => id ? agentsService.patch(id, payload, signal) : agentsService.create(payload, signal), (data) => {
      selectAgent(data.id);
      show(id ? "Đã lưu Agent." : "Đã tạo Agent trong tài khoản của bạn.");
    });
  }

  function duplicateAgent() {
    const id = context.current.id;
    if (!id) return;
    return mutate("duplicate", (signal) => agentsService.duplicate(id, signal), (data) => {
      selectAgent(data.id);
      show("Đã nhân bản cấu hình Agent. Lịch sử thực thi không được sao chép.");
    });
  }

  function confirmDeletion() {
    if (!deletion || deletion.agentId !== context.current.id) return;
    const target = deletion;
    return mutate("delete", (signal) => target.executionId
      ? agentsService.removeExecution(target.agentId, target.executionId, signal)
      : agentsService.remove(target.agentId, signal), () => {
      setDeletion(null);
      if (target.executionId) {
        if (context.current.executionId === target.executionId) selectExecution(null);
        bump("history");
        show("Đã xóa lượt thực thi.");
      } else {
        selectAgent(null);
        show("Đã xóa Agent và lịch sử thực thi của Agent.");
      }
    });
  }

  function run(prompt) {
    const id = context.current.id;
    if (!id || !prompt.trim() || streamRef.current || mutationRef.current || detailState.id !== id || detailState.revision !== revisionRef.current.detail || !detailState.data) return;
    const stream = { controller: new AbortController(), session: context.current.session,
      execution: { agent_id: id, prompt: prompt.trim(), status: "running", steps: [], content: "" }, done: false };
    streamRef.current = stream;
    context.current.executionId = null;
    setActiveExecutionId(null);
    bump("execution");
    setLive(stream.execution);
    setStreamError("");
    setIsStreaming(true);
    const valid = () => mounted.current && streamRef.current === stream && context.current.session === stream.session && context.current.id === id && !stream.controller.signal.aborted;
    const onEvent = (event) => {
      if (!valid() || stream.done) return;
      stream.execution = applyExecutionEvent(stream.execution, event);
      if (stream.execution.id) {
        context.current.executionId = stream.execution.id;
        setActiveExecutionId(stream.execution.id);
      }
      if (event.event === "execution_error") setStreamError(agentErrorFromEvent(event.data));
      if (event.event === "done") stream.done = true;
      setLive(stream.execution);
    };
    // Promise.resolve also captures a synchronous transport error.
    Promise.resolve().then(() => {
      if (valid()) return agentsService.run(id, { prompt: prompt.trim() }, { signal: stream.controller.signal, onEvent });
    }).then(() => {
      if (valid() && !stream.done) {
        stream.execution = { ...stream.execution, status: "error" };
        setLive(stream.execution);
        setStreamError("Luồng kết thúc trước khi có kết quả cuối. Tải lại lịch sử để kiểm tra trạng thái đã lưu.");
      }
    }).catch((error) => {
      if (!valid()) return;
      stream.execution = { ...stream.execution, status: "error" };
      setLive(stream.execution);
      setStreamError(getAgentError(error));
    }).finally(() => {
      if (!valid()) return;
      streamRef.current = null;
      setIsStreaming(false);
      bump("history");
      bump("list");
    });
  }

  const agent = detailState.id === activeId ? detailState.data : null;
  const detailLoading = Boolean(activeId) && (detailState.id !== activeId || detailState.revision !== revisions.detail);
  const executionMatches = executionState.agentId === activeId && executionState.id === activeExecutionId;
  return {
    activeId, agent, activeExecutionId, isStreaming, busy, editing, setEditing, deletion, setDeletion, streamError,
    selectionRevision: revisions.detail,
    agents: { items: listState.items, loading: listState.revision !== revisions.list, error: listState.error },
    tools: { items: toolsState.items, loading: toolsState.revision !== revisions.tools, error: toolsState.error },
    detailLoading, detailError: detailState.id === activeId ? detailState.error : "",
    history: { items: historyState.id === activeId ? historyState.items : [], loading: Boolean(activeId) && (historyState.id !== activeId || historyState.revision !== revisions.history), error: historyState.id === activeId ? historyState.error : "" },
    execution: liveSelected ? live : executionMatches ? executionState.data : null,
    executionLoading: Boolean(activeExecutionId) && !liveSelected && (!executionMatches || executionState.revision !== revisions.execution),
    executionError: !liveSelected && executionMatches ? executionState.error : "",
    selectAgent, newAgent: () => selectAgent(null), selectExecution, saveAgent, duplicateAgent, confirmDeletion, run, stop,
    reloadList: () => bump("list"), reloadTools: () => bump("tools"), reloadDetail: () => bump("detail"), reloadHistory: () => bump("history"),
    reloadExecution: () => { if (!streamRef.current) { setLive(null); bump("execution"); } },
  };
}
