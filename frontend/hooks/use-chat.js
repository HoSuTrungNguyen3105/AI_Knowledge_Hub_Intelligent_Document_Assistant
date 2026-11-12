"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { chatService } from "../services/chat";
import { chatErrorFromEvent, getChatError } from "../utils/chat";
import { useNotice } from "../stores/notice";

const idleThread = { data: null, loading: false, error: "" };

export function useChat() {
  const [conversations, setConversations] = useState({ items: [], loading: true, error: "" });
  const [activeId, setActiveId] = useState(null);
  const [thread, setThread] = useState(idleThread);
  const [messages, setMessages] = useState([]);
  const [streaming, setStreaming] = useState(null);
  const [streamError, setStreamError] = useState("");
  const [busy, setBusy] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [listRevision, setListRevision] = useState(0);

  const abortRef = useRef(null);
  const streamText = useRef("");
  const localId = useRef(0);
  const mounted = useRef(true);
  const activeRef = useRef(null);
  const show = useNotice((state) => state.show);

  useEffect(() => { mounted.current = true; return () => { mounted.current = false; abortRef.current?.abort(); }; }, []);
  useEffect(() => { activeRef.current = activeId; }, [activeId]);

  const loadList = useCallback((silent = false) => {
    const controller = new AbortController();
    if (!silent) setConversations((state) => ({ ...state, loading: true, error: "" }));
    chatService.list(controller.signal)
      .then((items) => { if (!controller.signal.aborted) setConversations({ items, loading: false, error: "" }); })
      .catch((error) => { if (!axios.isCancel(error)) setConversations((state) => ({ ...state, loading: false, error: getChatError(error) })); });
    return () => controller.abort();
  }, []);

  useEffect(() => loadList(), [listRevision, loadList]);

  useEffect(() => {
    if (!activeId) { setThread(idleThread); setMessages([]); return; }
    const controller = new AbortController();
    setThread({ data: null, loading: true, error: "" });
    setStreamError("");
    chatService.get(activeId, controller.signal)
      .then((data) => { if (!controller.signal.aborted) { setThread({ data, loading: false, error: "" }); setMessages(data.messages); } })
      .catch((error) => { if (!axios.isCancel(error)) setThread({ data: null, loading: false, error: getChatError(error) }); });
    return () => controller.abort();
  }, [activeId]);

  const stop = useCallback(() => { abortRef.current?.abort(); }, []);

  function syntheticAssistant(status, errorCode, model) {
    localId.current += 1;
    return {
      id: `local-${localId.current}`,
      role: "assistant",
      content: streamText.current,
      status,
      model: model ?? null,
      input_tokens: null,
      output_tokens: null,
      latency_ms: null,
      error_code: errorCode ?? null,
      created_at: new Date().toISOString(),
    };
  }

  function handleEvent(event, model) {
    if (event.event === "user_message") {
      setMessages((prev) => [...prev, event.data.message]);
    } else if (event.event === "delta") {
      streamText.current += event.data.text;
      setStreaming({ text: streamText.current });
    } else if (event.event === "done") {
      setMessages((prev) => [...prev, event.data.message]);
      setStreaming(null);
    } else if (event.event === "error") {
      setMessages((prev) => [...prev, syntheticAssistant("error", event.data.code, model)]);
      setStreaming(null);
      setStreamError(chatErrorFromEvent(event.data));
    }
  }

  async function runStream(start, model) {
    if (abortRef.current) return;
    const controller = new AbortController();
    abortRef.current = controller;
    streamText.current = "";
    setStreamError("");
    setStreaming({ text: "" });
    try {
      await start(controller.signal, (event) => handleEvent(event, model));
    } catch (error) {
      if (controller.signal.aborted) {
        setMessages((prev) => [...prev, syntheticAssistant("stopped", null, model)]);
      } else {
        setStreamError(getChatError(error));
      }
      setStreaming(null);
    } finally {
      abortRef.current = null;
      if (mounted.current) loadList(true);
    }
  }

  function sendMessage(content) {
    const text = content.trim();
    if (!activeId || !text || abortRef.current) return;
    const model = thread.data?.model ?? null;
    runStream((signal, onEvent) => chatService.sendMessage(activeId, text, { signal, onEvent }), model);
  }

  function regenerate() {
    if (!activeId || abortRef.current) return;
    const model = thread.data?.model ?? null;
    // Mirror the server: drop assistant replies after the last user turn.
    setMessages((prev) => {
      let lastUser = -1;
      prev.forEach((message, index) => { if (message.role === "user") lastUser = index; });
      return lastUser < 0 ? prev : prev.slice(0, lastUser + 1);
    });
    runStream((signal, onEvent) => chatService.regenerate(activeId, { signal, onEvent }), model);
  }

  async function createConversation(payload) {
    if (busy) return;
    setBusy("create");
    try {
      const created = await chatService.create(payload);
      if (!mounted.current) return;
      stop();
      setActiveId(created.id);
      setListRevision((value) => value + 1);
      show("Đã tạo hội thoại mới.");
    } catch (error) {
      if (mounted.current) show(getChatError(error), "error");
    } finally {
      if (mounted.current) setBusy("");
    }
  }

  async function renameConversation(title) {
    if (!activeId || busy) return;
    setBusy("rename");
    try {
      const updated = await chatService.patch(activeId, { title });
      if (!mounted.current) return;
      setThread((state) => ({ ...state, data: state.data ? { ...state.data, ...updated } : state.data }));
      setListRevision((value) => value + 1);
      show("Đã đổi tên hội thoại.");
    } catch (error) {
      if (mounted.current) show(getChatError(error), "error");
    } finally {
      if (mounted.current) setBusy("");
    }
  }

  async function updateConfig(values) {
    if (!activeId || busy) return;
    setBusy("config");
    try {
      const updated = await chatService.patch(activeId, values);
      if (!mounted.current) return;
      setThread((state) => ({ ...state, data: state.data ? { ...state.data, ...updated } : state.data }));
      show("Đã lưu cấu hình hội thoại.");
    } catch (error) {
      if (mounted.current) show(getChatError(error), "error");
    } finally {
      if (mounted.current) setBusy("");
    }
  }

  async function deleteConversation() {
    if (!activeId || busy) return;
    setBusy("delete");
    try {
      await chatService.remove(activeId);
      if (!mounted.current) return;
      stop();
      setActiveId(null);
      setConfirmDelete(false);
      setListRevision((value) => value + 1);
      show("Đã xóa hội thoại và toàn bộ tin nhắn của nó.");
    } catch (error) {
      if (mounted.current) show(getChatError(error), "error");
    } finally {
      if (mounted.current) setBusy("");
    }
  }

  function selectConversation(id) {
    if (id === activeId) return;
    stop();
    setConfirmDelete(false);
    setActiveId(id);
  }

  function newConversation() {
    stop();
    setConfirmDelete(false);
    setActiveId(null);
  }

  const lastUserIndex = messages.reduce((acc, message, index) => (message.role === "user" ? index : acc), -1);

  return {
    conversations,
    activeId,
    thread,
    messages,
    streaming,
    isStreaming: streaming !== null,
    streamError,
    busy,
    confirmDelete,
    setConfirmDelete,
    canRegenerate: lastUserIndex >= 0 && !streaming,
    selectConversation,
    newConversation,
    createConversation,
    sendMessage,
    regenerate,
    stop,
    renameConversation,
    updateConfig,
    deleteConversation,
    reloadList: () => setListRevision((value) => value + 1),
    reloadThread: () => setActiveId((id) => id),
  };
}