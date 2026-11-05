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
      dialogs: 4,
    },
    {
      id: "user-2",
      login: "Sovunya",
      role: "admin",
      registered_at: "2026-08-17T12:00:00Z",
      last_active_at: null,
      status: "inactive",
      dialogs: 0,
    },
  ],
  feedback: { answers_total: 10, rated_answers: 5, counts: [1, 0, 1, 1, 2] },
  reports_new: 2,
  dialogs: 3,
  messages: 18,
  activity: [
    { start: "2026-09-16T12:00:00Z", dialogs: 1 },
    { start: "2026-09-19T12:00:00Z", dialogs: 2 },
  ],
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
        dialogs: 4,
      },
      {
        id: "user-2",
        login: "Sovunya",
        role: "admin",
        registeredAt: "2026-08-17T12:00:00Z",
        lastActiveAt: null,
        status: "inactive",
        dialogs: 0,
      },
    ],
    feedback: { answersTotal: 10, ratedAnswers: 5, counts: [1, 0, 1, 1, 2] },
    reportsNew: 2,
    dialogs: 3,
    messages: 18,
    activity: [
      { start: "2026-09-16T12:00:00Z", dialogs: 1 },
      { start: "2026-09-19T12:00:00Z", dialogs: 2 },
    ],
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
    { ...BODY, reports_new: -1 },
    { ...BODY, reports_new: undefined },
    { ...BODY, dialogs: -1 },
    { ...BODY, messages: "18" },
    { ...BODY, activity: null },
    { ...BODY, activity: [] },
    { ...BODY, activity: [{ start: "вчера", dialogs: 3 }] },
    { ...BODY, activity: [{ start: "2026-09-16T12:00:00Z", dialogs: 2 }] },
    { ...BODY, recent_users: [{ ...user, dialogs: 1.5 }] },
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

const REPORT = {
  id: 4,
  reason: "rude",
  comment: "Обидно",
  request_text: "Про Нюшу",
  answer_text: "Грубый ответ",
  status: "new",
  created_at: "2026-10-18T09:00:00Z",
  resolved_at: null,
  dialog_deleted: false,
};

test("reports are read by status with the session cookie", async () => {
  const { api, calls } = recordingApi(response(200, {
    reports: [REPORT, { ...REPORT, id: 5, comment: null, request_text: null, status: "resolved", resolved_at: "2026-10-18T10:00:00Z", dialog_deleted: true }],
  }));

  assert.deepEqual(await api.listReports("all"), [
    {
      id: 4,
      reason: "rude",
      comment: "Обидно",
      requestText: "Про Нюшу",
      answerText: "Грубый ответ",
      status: "new",
      createdAt: "2026-10-18T09:00:00Z",
      resolvedAt: null,
      dialogDeleted: false,
    },
    {
      id: 5,
      reason: "rude",
      comment: null,
      requestText: null,
      answerText: "Грубый ответ",
      status: "resolved",
      createdAt: "2026-10-18T09:00:00Z",
      resolvedAt: "2026-10-18T10:00:00Z",
      dialogDeleted: true,
    },
  ]);
  assert.deepEqual(calls, [["/api/v1/admin/reports?status=all", { method: "GET", credentials: "same-origin" }]]);
  await assert.rejects(api.listReports("open"), RangeError);
});

test("malformed reports are rejected", async () => {
  const bodies = [
    null,
    { reports: "nope" },
    { reports: [{ ...REPORT, id: "4" }] },
    { reports: [{ ...REPORT, reason: "boring" }] },
    { reports: [{ ...REPORT, status: "open" }] },
    { reports: [{ ...REPORT, comment: 5 }] },
    { reports: [{ ...REPORT, request_text: 5 }] },
    { reports: [{ ...REPORT, answer_text: null }] },
    { reports: [{ ...REPORT, created_at: "вчера" }] },
    { reports: [{ ...REPORT, resolved_at: "потом" }] },
    { reports: [{ ...REPORT, dialog_deleted: "no" }] },
  ];
  for (const body of bodies) {
    await assertAdminError(recordingApi(response(200, body)).api.listReports("new"), "invalid_response");
  }
});

test("a report status is patched with the session cookie", async () => {
  const { api, calls } = recordingApi(response(204));

  await api.setReportStatus(4, "dismissed");

  assert.deepEqual(calls, [["/api/v1/admin/reports/4", {
    method: "PATCH",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: "dismissed" }),
  }]]);
});

test("report requests map statuses to error codes", async () => {
  const cases = [
    [response(401), "unauthorized"],
    [response(403), "forbidden"],
    [response(503), "unavailable"],
    [new TypeError("offline"), "unavailable"],
  ];
  for (const [result, code] of cases) {
    await assertAdminError(recordingApi(result).api.listReports("new"), code);
    await assertAdminError(recordingApi(result).api.setReportStatus(1, "new"), code);
  }
  await assertAdminError(recordingApi(response(404)).api.setReportStatus(1, "new"), "not_found");
});
