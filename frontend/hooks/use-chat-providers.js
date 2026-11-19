"use client";

import { useEffect, useState } from "react";
import axios from "axios";
import { providerService } from "../services/providers";
import { getProviderError } from "../utils/providers";

// Loads only what the chat picker needs: configured + enabled providers and their
// synced models. Reuses the Phase 2 provider service; no key handling lives here.
// Loading is derived (not set synchronously in an effect) to match use-providers.
export function useChatProviders(initialProviderId = "") {
  const [catalogState, setCatalogState] = useState({ data: null, revision: -1, error: "" });
  const [providerId, setProviderId] = useState(initialProviderId);
  const [modelState, setModelState] = useState({ provider: null, revision: -1, models: [], error: "" });
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    providerService.list(controller.signal)
      .then((data) => { if (!controller.signal.aborted) setCatalogState({ data, revision, error: "" }); })
      .catch((error) => { if (!controller.signal.aborted && !axios.isCancel(error)) setCatalogState({ data: null, revision, error: getProviderError(error) }); });
    return () => controller.abort();
  }, [revision]);

  const catalog = { ...catalogState, loading: catalogState.revision !== revision };
  const providers = catalog.data?.providers ?? [];
  const available = providers.filter((item) => item.implemented && item.configured && item.enabled);
  // Fall back to the first available provider when the selection is unset or stale.
  const selected = available.find((item) => item.id === providerId) ?? available[0] ?? null;
  const effectiveId = selected?.id ?? "";

  useEffect(() => {
    if (!effectiveId) return;
    const controller = new AbortController();
    providerService.models(effectiveId, controller.signal)
      .then((data) => { if (!controller.signal.aborted) setModelState({ provider: effectiveId, revision, models: data.models, error: "" }); })
      .catch((error) => { if (!controller.signal.aborted && !axios.isCancel(error)) setModelState({ provider: effectiveId, revision, models: [], error: getProviderError(error) }); });
    return () => controller.abort();
  }, [effectiveId, revision]);

  const modelsLoading = Boolean(effectiveId) && (modelState.provider !== effectiveId || modelState.revision !== revision);
  const current = !modelsLoading && modelState.provider === effectiveId ? modelState : { models: [], error: "" };
  // Tri-state capability: only an explicit false blocks chat; unknown is allowed.
  const models = current.models.filter((model) => model.capabilities?.chat !== false);

  return {
    catalog,
    available,
    providerId: effectiveId,
    setProviderId,
    models,
    modelsLoading,
    modelsError: current.error,
    encryptionReady: catalog.data?.encryption_ready ?? false,
    reload: () => setRevision((value) => value + 1),
  };
}