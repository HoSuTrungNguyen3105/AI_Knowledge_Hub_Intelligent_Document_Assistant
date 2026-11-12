"use client";

import { useEffect, useState } from "react";
import axios from "axios";
import { providerService } from "../services/providers";
import { getProviderError } from "../utils/providers";

// Loads only what the chat picker needs: configured + enabled providers and their
// synced models. Reuses the Phase 2 provider service; no key handling lives here.
export function useChatProviders() {
  const [catalog, setCatalog] = useState({ data: null, loading: true, error: "" });
  const [providerId, setProviderId] = useState("");
  const [modelState, setModelState] = useState({ models: [], loading: false, error: "" });
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    providerService.list(controller.signal)
      .then((data) => { if (!controller.signal.aborted) setCatalog({ data, loading: false, error: "" }); })
      .catch((error) => { if (!axios.isCancel(error)) setCatalog({ data: null, loading: false, error: getProviderError(error) }); });
    return () => controller.abort();
  }, [revision]);

  const providers = catalog.data?.providers ?? [];
  const available = providers.filter((item) => item.implemented && item.configured && item.enabled);
  // Fall back to the first available provider when the selection is unset or stale.
  const selected = available.find((item) => item.id === providerId) ?? available[0] ?? null;
  const effectiveId = selected?.id ?? "";

  useEffect(() => {
    if (!effectiveId) { setModelState({ models: [], loading: false, error: "" }); return; }
    const controller = new AbortController();
    setModelState({ models: [], loading: true, error: "" });
    providerService.models(effectiveId, controller.signal)
      .then((data) => { if (!controller.signal.aborted) setModelState({ models: data.models, loading: false, error: "" }); })
      .catch((error) => { if (!axios.isCancel(error)) setModelState({ models: [], loading: false, error: getProviderError(error) }); });
    return () => controller.abort();
  }, [effectiveId, revision]);

  // Tri-state capability: only an explicit false blocks chat; unknown is allowed.
  const models = modelState.models.filter((model) => model.capabilities?.chat !== false);

  return {
    catalog,
    available,
    providerId: effectiveId,
    setProviderId,
    models,
    modelsLoading: modelState.loading,
    modelsError: modelState.error,
    encryptionReady: catalog.data?.encryption_ready ?? false,
    reload: () => setRevision((value) => value + 1),
  };
}