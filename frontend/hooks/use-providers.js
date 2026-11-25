"use client";

import { useEffect, useRef, useState } from "react";
import axios from "axios";
import { providerService } from "../services/providers";
import { getProviderError, validateApiKey } from "../utils/providers";
import { useNotice } from "../stores/notice";

export function useProviders() {
  const [catalog, setCatalog] = useState({ data: null, loading: true, error: "" });
  const [selectedId, setSelectedId] = useState("openai");
  const [modelState, setModelState] = useState({ provider: null, models: [], error: "", synced_at: null });
  const [modelRevision, setModelRevision] = useState(0);
  const [catalogRevision, setCatalogRevision] = useState(0);
  const [busy, setBusy] = useState("");
  const [checking, setChecking] = useState("");
  const [keyError, setKeyError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const inFlight = useRef(false);
  const mounted = useRef(true);
  const show = useNotice((state) => state.show);

  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    const controller = new AbortController();
    providerService.list(controller.signal)
      .then((data) => { if (!controller.signal.aborted) setCatalog({ data, loading: false, error: "" }); })
      .catch((error) => { if (!axios.isCancel(error)) setCatalog((state) => ({ ...state, loading: false, error: getProviderError(error) })); });
    return () => controller.abort();
  }, [catalogRevision]);

  const provider = catalog.data?.providers.find((item) => item.id === selectedId);
  const implemented = provider?.implemented;
  useEffect(() => {
    if (!implemented) return;
    const controller = new AbortController();
    providerService.models(selectedId, controller.signal)
      .then((data) => { if (!controller.signal.aborted) setModelState({ ...data, error: "" }); })
      .catch((error) => {
        if (!axios.isCancel(error)) setModelState({ provider: selectedId, models: [], synced_at: null, error: getProviderError(error) });
      });
    return () => controller.abort();
  }, [selectedId, implemented, modelRevision]);

  function refreshModels() {
    setModelState({ provider: null, models: [], error: "", synced_at: null });
    setModelRevision((value) => value + 1);
  }
  function replaceProvider(updated) {
    if (!mounted.current) return;
    setCatalog((state) => ({ ...state, data: { ...state.data, providers: state.data.providers.map((item) => item.id === updated.id ? updated : item) } }));
  }
  async function run(action, operation, successMessage) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(action);
    setKeyError("");
    try {
      await operation();
      if (mounted.current) show(successMessage);
    } catch (error) {
      if (mounted.current) {
        show(getProviderError(error), "error");
        setCatalogRevision((value) => value + 1);
        refreshModels();
      }
    } finally {
      inFlight.current = false;
      if (mounted.current) setBusy("");
    }
  }
  async function saveKey(event) {
    event.preventDefault();
    const field = event.currentTarget.elements.namedItem("apiKey");
    const key = field.value.trim();
    const validation = validateApiKey(key);
    if (validation) { setKeyError(validation); return; }
    field.value = "";
    await run("save-key", async () => {
      replaceProvider(await providerService.update(selectedId, { api_key: key }));
      if (mounted.current) refreshModels();
    }, "Đã lưu API key mã hóa. Hãy kiểm tra kết nối để đồng bộ model.");
  }
  async function testConnection() {
    await run("test", async () => {
      const result = await providerService.test(selectedId);
      replaceProvider(result.provider);
      if (mounted.current) refreshModels();
    }, "Đã kiểm tra API danh sách model. Chưa thực hiện yêu cầu tạo nội dung AI.");
  }
  async function checkModel(modelId) {
    if (checking) return;
    setChecking(modelId);
    try {
      const result = await providerService.checkModel(selectedId, modelId);
      show(
        result.status === "ok"
          ? `Model ${modelId} hoạt động tốt (${result.latency_ms} ms).`
          : `Model ${modelId} chưa chạy được: ${result.error_code || "lỗi không rõ"}.`,
        result.status === "ok" ? undefined : "error"
      );
      refreshModels();
    } catch (error) {
      show(getProviderError(error), "error");
    } finally {
      setChecking("");
    }
  }
  async function setEnabled(enabled) {
    await run("toggle", async () => replaceProvider(await providerService.update(selectedId, { enabled })), enabled ? "Đã bật provider cho các tính năng AI sắp triển khai." : "Đã tắt provider. API key vẫn được lưu mã hóa.");
  }
  async function saveDefaultModel(event) {
    event.preventDefault();
    const model = new FormData(event.currentTarget).get("defaultModel") || null;
    await run("default-model", async () => replaceProvider(await providerService.update(selectedId, { default_model: model })), "Đã lưu model mặc định.");
  }
  async function disconnect() {
    await run("delete", async () => {
      await providerService.disconnect(selectedId);
      const data = await providerService.list();
      if (mounted.current) { setCatalog({ data, error: "", loading: false }); setConfirmDelete(false); refreshModels(); }
    }, "Đã xóa API key và danh sách model đã lưu. Các dữ liệu khác được giữ nguyên.");
  }
  function selectProvider(id) {
    if (inFlight.current) return;
    setSelectedId(id);
    setKeyError("");
    setConfirmDelete(false);
  }
  function reload() {
    if (inFlight.current) return;
    setCatalog((state) => ({ ...state, loading: true, error: "" }));
    setCatalogRevision((value) => value + 1);
    refreshModels();
  }
  return { catalog, provider, selectedId, selectProvider, modelState, modelsLoading: implemented && modelState.provider !== selectedId, busy, checking, checkModel, keyError, saveKey, testConnection, setEnabled, saveDefaultModel, confirmDelete, setConfirmDelete, disconnect, reload };
}
