import { afterEach, describe, expect, it, vi } from "vitest";
import {
  WAKE_PING_PATH,
  backendPingUrl,
  getBackendUrl,
  wakeBackend,
  warnIfBackendUrlMisconfigured,
} from "../utils/wake-backend";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("wake-backend url", () => {
  it("builds the ping url from BACKEND_URL", () => {
    vi.stubEnv("BACKEND_URL", "https://backend.example.com");
    expect(getBackendUrl()).toBe("https://backend.example.com");
    expect(backendPingUrl()).toBe(`https://backend.example.com${WAKE_PING_PATH}`);
  });

  it("falls back to the local backend when BACKEND_URL is unset", () => {
    vi.stubEnv("BACKEND_URL", "");
    expect(getBackendUrl()).toBe("http://127.0.0.1:8000");
    expect(backendPingUrl()).toBe(`http://127.0.0.1:8000${WAKE_PING_PATH}`);
  });
});

describe("warnIfBackendUrlMisconfigured", () => {
  it("warns in production when BACKEND_URL is missing", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("BACKEND_URL", "");
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    warnIfBackendUrlMisconfigured();
    expect(warn).toHaveBeenCalledTimes(1);
  });

  it("warns in production when BACKEND_URL points at localhost", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("BACKEND_URL", "http://127.0.0.1:8000");
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    warnIfBackendUrlMisconfigured();
    expect(warn).toHaveBeenCalledTimes(1);
  });

  it("stays quiet in production with a real BACKEND_URL", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("BACKEND_URL", "https://backend.example.com");
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    warnIfBackendUrlMisconfigured();
    expect(warn).not.toHaveBeenCalled();
  });

  it("stays quiet outside production", () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("BACKEND_URL", "");
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    warnIfBackendUrlMisconfigured();
    expect(warn).not.toHaveBeenCalled();
  });
});

describe("wakeBackend", () => {
  it("returns true on the first OK answer", async () => {
    const fetchMock = vi.fn(async () => ({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(wakeBackend({ attempts: 3, intervalMs: 1 })).resolves.toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("retries until the backend answers OK", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error("asleep"))
      .mockResolvedValueOnce({ ok: false })
      .mockResolvedValueOnce({ ok: true });
    vi.stubGlobal("fetch", fetchMock);
    await expect(wakeBackend({ attempts: 5, intervalMs: 1 })).resolves.toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("gives up after the attempt budget without throwing", async () => {
    const fetchMock = vi.fn(async () => {
      throw new Error("unreachable");
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(wakeBackend({ attempts: 3, intervalMs: 1 })).resolves.toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});

describe("nudgeBackend throttle", () => {
  it("starts at most one wake sequence per throttle window", async () => {
    vi.resetModules();
    const fetchMock = vi.fn(async () => ({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    const { nudgeBackend } = await import("../utils/wake-backend");
    const first = nudgeBackend();
    expect(first).not.toBeNull();
    expect(nudgeBackend()).toBeNull();
    await first;
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
