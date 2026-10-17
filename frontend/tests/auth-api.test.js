import assert from "node:assert/strict";
import test from "node:test";

import { AuthApi, AuthApiError } from "../src/auth-api.js";

const USER = { id: "user-1", login: "krosh", role: "user" };

function response(status, body, { invalidJson = false } = {}) {
  return {
    status,
    ok: status >= 200 && status < 300,
    async json() {
      if (invalidJson) throw new SyntaxError("bad json");
      return body;
    },
  };
}

function recordingApi(result) {
  const calls = [];
  const api = new AuthApi({
    fetchImpl: async (...args) => {
      calls.push(args);
      if (result instanceof Error) throw result;
      return result;
    },
  });
  return { api, calls };
}

async function assertAuthError(promise, code) {
  await assert.rejects(promise, error => {
    assert.ok(error instanceof AuthApiError);
    assert.equal(error.code, code);
    return true;
  });
}

const JSON_POST = {
  method: "POST",
  credentials: "same-origin",
  headers: { "Content-Type": "application/json" },
};

test("register posts credentials to the user collection and returns the user", async () => {
  const { api, calls } = recordingApi(response(201, USER));

  assert.deepEqual(await api.register({ login: "krosh", password: "carrot123" }), USER);
  assert.deepEqual(calls, [[
    "/api/v1/users",
    { ...JSON_POST, body: JSON.stringify({ login: "krosh", password: "carrot123" }) },
  ]]);
});

test("login posts credentials to the auth endpoint and returns the user", async () => {
  const { api, calls } = recordingApi(response(200, USER));

  assert.deepEqual(await api.login({ login: "krosh", password: "carrot123" }), USER);
  assert.deepEqual(calls, [[
    "/api/v1/auth/login",
    { ...JSON_POST, body: JSON.stringify({ login: "krosh", password: "carrot123" }) },
  ]]);
});

test("logout posts without a body and accepts 204", async () => {
  const { api, calls } = recordingApi(response(204));

  assert.equal(await api.logout(), undefined);
  assert.deepEqual(calls, [["/api/v1/auth/logout", { method: "POST", credentials: "same-origin" }]]);
});

test("me reads the current user with the session cookie", async () => {
  const { api, calls } = recordingApi(response(200, { ...USER, role: "admin" }));

  assert.deepEqual(await api.me(), { ...USER, role: "admin" });
  assert.deepEqual(calls, [["/api/v1/users/me", { method: "GET", credentials: "same-origin" }]]);
});

test("refresh posts without a body and returns the renewed user", async () => {
  const { api, calls } = recordingApi(response(200, USER));

  assert.deepEqual(await api.refresh(), USER);
  assert.deepEqual(calls, [["/api/v1/auth/refresh", { method: "POST", credentials: "same-origin" }]]);
});

test("only contract fields of the user are returned", async () => {
  const { api } = recordingApi(response(200, { ...USER, password_hash: "secret" }));

  assert.deepEqual(await api.login({ login: "krosh", password: "carrot123" }), USER);
});

test("HTTP statuses map to stable error codes", async () => {
  const cases = [
    ["register", 409, "login_taken"],
    ["register", 422, "invalid_fields"],
    ["register", 429, "too_many_attempts"],
    ["register", 500, "unavailable"],
    ["login", 401, "invalid_credentials"],
    ["login", 422, "invalid_fields"],
    ["login", 429, "too_many_attempts"],
    ["login", 404, "unavailable"],
    ["logout", 500, "unavailable"],
    ["me", 401, "unauthorized"],
    ["me", 404, "unavailable"],
    ["refresh", 401, "unauthorized"],
    ["refresh", 503, "unavailable"],
  ];

  for (const [method, status, code] of cases) {
    const { api } = recordingApi(response(status, {}));
    await assertAuthError(api[method]({ login: "krosh", password: "carrot123" }), code);
  }
});

test("network failures map to unavailable", async () => {
  for (const method of ["register", "login", "logout", "me", "refresh"]) {
    const { api } = recordingApi(new TypeError("Failed to fetch"));
    await assertAuthError(api[method]({ login: "krosh", password: "carrot123" }), "unavailable");
  }
});

test("malformed success bodies are rejected", async () => {
  const bodies = [
    [null, false],
    [{ id: "", login: "krosh", role: "user" }, false],
    [{ id: "user-1", role: "user" }, false],
    [{ id: "user-1", login: "krosh", role: "root" }, false],
    [USER, true],
  ];

  for (const [body, invalidJson] of bodies) {
    const { api } = recordingApi(response(200, body, { invalidJson }));
    await assertAuthError(api.me(), "invalid_response");
  }
});

test("the client never touches browser storage", async () => {
  const touched = [];
  const storage = new Proxy({}, { get: (_target, key) => touched.push(key) });
  globalThis.localStorage = storage;
  globalThis.sessionStorage = storage;
  try {
    const { api } = recordingApi(response(200, USER));
    await api.login({ login: "krosh", password: "carrot123" });
    await api.me();
    assert.deepEqual(touched, []);
  } finally {
    delete globalThis.localStorage;
    delete globalThis.sessionStorage;
  }
});

test("fetchImpl must be a function", () => {
  assert.throws(() => new AuthApi({ fetchImpl: null }), TypeError);
});
