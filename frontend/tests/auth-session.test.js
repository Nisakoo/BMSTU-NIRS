import assert from "node:assert/strict";
import test from "node:test";

import { AuthApiError } from "../src/auth-api.js";
import {
  ADMIN_PATH,
  CHAT_PATH,
  LOGIN_PATH,
  SESSION,
  checkSession,
  homeFor,
  refreshSession,
} from "../src/auth-session.js";

const USER = { id: "user-1", login: "krosh", role: "user" };
const ADMIN = { id: "admin-1", login: "sovunya", role: "admin" };

const reject = code => () => Promise.reject(new AuthApiError(code));
const resolve = user => () => Promise.resolve(user);

function fakeApi({ me = reject("unauthorized"), refresh = reject("unauthorized") } = {}) {
  const calls = [];
  return {
    calls,
    me: () => (calls.push("me"), me()),
    refresh: () => (calls.push("refresh"), refresh()),
  };
}

test("a valid access token resolves the user without refresh", async () => {
  const api = fakeApi({ me: resolve(USER) });

  assert.deepEqual(await checkSession(api), { status: SESSION.USER, user: USER });
  assert.deepEqual(api.calls, ["me"]);
});

test("an expired access token is renewed once with refresh", async () => {
  const api = fakeApi({ refresh: resolve(ADMIN) });

  assert.deepEqual(await checkSession(api), { status: SESSION.USER, user: ADMIN });
  assert.deepEqual(api.calls, ["me", "refresh"]);
});

test("a rejected refresh means there is no session", async () => {
  const api = fakeApi();

  assert.deepEqual(await checkSession(api), { status: SESSION.ANONYMOUS });
  assert.deepEqual(api.calls, ["me", "refresh"]);
});

test("infrastructure failures are reported as unavailable, not as a guest", async () => {
  const cases = [
    [{ me: reject("unavailable") }, ["me"]],
    [{ me: reject("invalid_response") }, ["me"]],
    [{ refresh: reject("unavailable") }, ["me", "refresh"]],
    [{ refresh: reject("invalid_response") }, ["me", "refresh"]],
  ];

  for (const [options, calls] of cases) {
    const api = fakeApi(options);
    assert.deepEqual(await checkSession(api), { status: SESSION.UNAVAILABLE });
    assert.deepEqual(api.calls, calls);
  }
});

test("refreshSession maps refresh outcomes without calling me", async () => {
  const renewed = fakeApi({ refresh: resolve(USER) });
  assert.deepEqual(await refreshSession(renewed), { status: SESSION.USER, user: USER });
  assert.deepEqual(renewed.calls, ["refresh"]);

  assert.deepEqual(await refreshSession(fakeApi()), { status: SESSION.ANONYMOUS });
  assert.deepEqual(
    await refreshSession(fakeApi({ refresh: reject("unavailable") })),
    { status: SESSION.UNAVAILABLE },
  );
});

test("homeFor sends administrators to the panel and users to the chat", () => {
  assert.equal(homeFor(ADMIN), ADMIN_PATH);
  assert.equal(homeFor(USER), CHAT_PATH);
  assert.deepEqual([LOGIN_PATH, CHAT_PATH, ADMIN_PATH], ["/login/", "/", "/admin/"]);
});
