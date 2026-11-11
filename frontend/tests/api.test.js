import { afterEach, describe, expect, it } from "vitest";
import MockAdapter from "axios-mock-adapter";
import { api, refreshClient, getErrorMessage } from "../services/api";
import { authService } from "../services/auth";

const requests = new MockAdapter(api);
const refresh = new MockAdapter(refreshClient);

afterEach(() => { requests.reset(); refresh.reset(); });

describe("HTTP session lifecycle", () => {
  it("refreshes and retries an expired access session", async () => {
    requests.onGet("/auth/me").replyOnce(401);
    requests.onGet("/auth/me").reply(200, { id: "u1" });
    refresh.onPost("/auth/refresh").reply(200, { user: { id: "u1" } });
    expect(await authService.me()).toEqual({ id: "u1" });
    expect(refresh.history.post).toHaveLength(1);
    expect(requests.history.get).toHaveLength(2);
  });
  it("shares one refresh between simultaneous failed requests", async () => {
    requests.onGet("/auth/me").replyOnce(401);
    requests.onGet("/dashboard").replyOnce(401);
    requests.onGet("/auth/me").reply(200, { id: "u1" });
    requests.onGet("/dashboard").reply(200, { total_documents: 0 });
    refresh.onPost("/auth/refresh").reply(() => new Promise((resolve) => setTimeout(() => resolve([200, {}]), 10)));
    const results = await Promise.all([api.get("/auth/me"), api.get("/dashboard")]);
    expect(results.every((result) => result.status === 200)).toBe(true);
    expect(refresh.history.post).toHaveLength(1);
  });
  it("does not retry invalid login credentials", async () => {
    requests.onPost("/auth/login").reply(401);
    await expect(authService.login({ email: "a@example.com", password: "invalid" })).rejects.toMatchObject({ response: { status: 401 } });
    expect(refresh.history.post).toHaveLength(0);
  });
  it("never loops when refresh is rejected", async () => {
    requests.onGet("/auth/me").reply(401);
    refresh.onPost("/auth/refresh").reply(401);
    await expect(authService.me()).rejects.toMatchObject({ response: { status: 401 } });
    expect(requests.history.get).toHaveLength(1);
    expect(refresh.history.post).toHaveLength(1);
  });
  it("does not retry a request more than once", async () => {
    requests.onGet("/auth/me").reply(401);
    refresh.onPost("/auth/refresh").reply(200, {});
    await expect(authService.me()).rejects.toMatchObject({ response: { status: 401 } });
    expect(requests.history.get).toHaveLength(2);
    expect(refresh.history.post).toHaveLength(1);
  });
  it("keeps service errors distinct from an expired session", async () => {
    requests.onGet("/auth/me").replyOnce(401);
    refresh.onPost("/auth/refresh").reply(503);
    await expect(authService.me()).rejects.toMatchObject({ response: { status: 503 } });
  });
  it("logout never creates a replacement session", async () => {
    requests.onPost("/auth/logout").reply(401);
    await expect(authService.logout()).rejects.toMatchObject({ response: { status: 401 } });
    expect(refresh.history.post).toHaveLength(0);
  });
  it("uses same-origin HttpOnly cookie transport, not bearer storage", () => {
    expect(api.defaults.baseURL).toBe("/api/v1");
    expect(api.defaults.withCredentials).toBe(true);
    expect(api.defaults.headers.common.Authorization).toBeUndefined();
  });
});

describe("safe user-facing errors", () => {
  it("does not display backend exception details", () => {
    expect(getErrorMessage({ response: { status: 500, data: { detail: "password=secret" } } })).not.toContain("secret");
  });
  it("handles network failure and validation", () => {
    expect(getErrorMessage({})).toContain("Không kết nối");
    expect(getErrorMessage({ response: { status: 422 } })).toContain("chưa hợp lệ");
  });
});
