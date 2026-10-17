import assert from "node:assert/strict";
import test from "node:test";

import { AdminApi, AdminApiError } from "../src/admin/admin-api.js";

const BODY = {
  period: "30",
  users_total: 3,
  active_users: 2,
  new_users: 1,
  recent_users: [
    {
      id: "user-1",
      login: "Krosh",
      role: "user",
      registered_at: "2026-10-15T12:00:00Z",
      last_active_at: "2026-10-16T10:00:00Z",
      status: "new",
    },
    {
      id: "user-2",
      login: "Sovunya",
      role: "admin",
      registered_at: "2026-08-17T12:00:00Z",
      last_active_at: null,
      status: "inactive",
    },
  ],
  feedback: { answers_total: 10, rated_answers: 5, counts: [1, 0, 1, 1, 2] },
};

function response(status, body, { invalidJson = false } = {}) {
  return {
    status,
    async json() {
      if (invalidJson) throw new SyntaxError("bad json");
      return body;
    },
  };
}

function recordingApi(result) {
  const calls = [];
  const api = new AdminApi({
    fetchImpl: async (...args) => {
      calls.push(args);
      if (result instanceof Error) throw result;
      return result;
    },
  });
  return { api, calls };
}

async function assertAdminError(promise, code) {
  await assert.rejects(promise, error => {
    assert.ok(error instanceof AdminApiError);
    assert.equal(error.code, code);
    return true;
  });
}

test("stats reads the selected period with the session cookie", async () => {
  const { api, calls } = recordingApi(response(200, BODY));

  assert.deepEqual(await api.stats("30"), {
    period: "30",
    usersTotal: 3,
    activeUsers: 2,
    newUsers: 1,
    recentUsers: [
      {
        id: "user-1",
        login: "Krosh",
        role: "user",
        registeredAt: "2026-10-15T12:00:00Z",
        lastActiveAt: "2026-10-16T10:00:00Z",
        status: "new",
      },
      {
        id: "user-2",
        login: "Sovunya",
        role: "admin",
        registeredAt: "2026-08-17T12:00:00Z",
        lastActiveAt: null,
        status: "inactive",
      },
    ],
    feedback: { answersTotal: 10, ratedAnswers: 5, counts: [1, 0, 1, 1, 2] },
  });
  assert.deepEqual(calls, [["/api/v1/admin/stats?period=30", { method: "GET", credentials: "same-origin" }]]);
});

test("HTTP statuses and network failures map to stable error codes", async () => {
  const cases = [
    [response(401, { error: "unauthorized" }), "unauthorized"],
    [response(403, { error: "forbidden" }), "forbidden"],
    [response(503, { error: "unavailable" }), "unavailable"],
    [response(422, {}), "unavailable"],
    [new TypeError("Failed to fetch"), "unavailable"],
  ];

  for (const [result, code] of cases) {
    await assertAdminError(recordingApi(result).api.stats("7"), code);
  }
});

test("malformed bodies are rejected", async () => {
  const user = BODY.recent_users[0];
  const bodies = [
    null,
    { ...BODY, period: "7" },
    { ...BODY, users_total: -1 },
    { ...BODY, active_users: 1.5 },
    { ...BODY, new_users: "1" },
    { ...BODY, recent_users: null },
    { ...BODY, recent_users: [{ ...user, login: "" }] },
    { ...BODY, recent_users: [{ ...user, role: "root" }] },
    { ...BODY, recent_users: [{ ...user, status: "banned" }] },
    { ...BODY, recent_users: [{ ...user, registered_at: "yesterday" }] },
    { ...BODY, recent_users: [{ ...user, last_active_at: 5 }] },
  ];

  for (const body of bodies) {
    await assertAdminError(recordingApi(response(200, body)).api.stats("30"), "invalid_response");
  }
  await assertAdminError(
    recordingApi(response(200, BODY, { invalidJson: true })).api.stats("30"),
    "invalid_response",
  );
});

test("unsupported periods are not sent to the backend", async () => {
  const { api, calls } = recordingApi(response(200, BODY));

  await assert.rejects(api.stats("365"), RangeError);
  assert.equal(calls.length, 0);
});

test("stats reject inconsistent answer feedback", async () => {
  for (const feedback of [
    undefined,
    { answers_total: 10, rated_answers: 5 },
    { answers_total: 10, rated_answers: 5, likes: 4, dislikes: 1 },
    { answers_total: 10, rated_answers: 5, counts: [1, 1, 1, 2] },
    { answers_total: 10, rated_answers: 5, counts: [1, 1, 1, 1, 1, 0] },
    { answers_total: 10, rated_answers: 5, counts: [-1, 1, 1, 2, 2] },
    { answers_total: 10, rated_answers: 5, counts: [1, 1, 1, 1, 1.5] },
    { answers_total: 10, rated_answers: 5, counts: [1, 1, 1, 1, 2] },
    { answers_total: 3, rated_answers: 5, counts: [1, 1, 1, 1, 1] },
    { answers_total: 10, rated_answers: 5, counts: "11111" },
  ]) {
    const { api } = recordingApi(response(200, { ...BODY, feedback }));
    await assertAdminError(api.stats("30"), "invalid_response");
  }
});
