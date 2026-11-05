const PERIODS = ["7", "30", "90"];
const ROLES = ["user", "admin"];
const STATUSES = ["new", "active", "inactive"];
const REPORT_REASONS = ["scary", "rude", "wrong", "other"];
const REPORT_STATUSES = ["new", "resolved", "dismissed"];
const REPORT_FILTERS = [...REPORT_STATUSES, "all"];

export class AdminApiError extends Error {
  constructor(code) {
    super(code);
    this.name = "AdminApiError";
    this.code = code;
  }
}

const isCount = value => Number.isInteger(value) && value >= 0;
// counts[i] is the number of answers rated i + 1 out of 5.
const SCORE_COUNT = 5;
const isTimestamp = value => typeof value === "string" && !Number.isNaN(Date.parse(value));
const isText = value => value === null || typeof value === "string";

function parseUser(entry) {
  if (
    typeof entry?.id !== "string" || !entry.id
    || typeof entry.login !== "string" || !entry.login
    || !ROLES.includes(entry.role)
    || !isTimestamp(entry.registered_at)
    || !(entry.last_active_at === null || isTimestamp(entry.last_active_at))
    || !STATUSES.includes(entry.status)
    || !isCount(entry.dialogs)
  ) {
    throw new AdminApiError("invalid_response");
  }
  return {
    id: entry.id,
    login: entry.login,
    role: entry.role,
    registeredAt: entry.registered_at,
    lastActiveAt: entry.last_active_at,
    status: entry.status,
    dialogs: entry.dialogs,
  };
}

function parseFeedback(feedback) {
  if (
    !isCount(feedback?.answers_total)
    || !isCount(feedback.rated_answers)
    || !Array.isArray(feedback.counts)
    || feedback.counts.length !== SCORE_COUNT
    || !feedback.counts.every(isCount)
    || feedback.counts.reduce((sum, count) => sum + count, 0) !== feedback.rated_answers
    || feedback.rated_answers > feedback.answers_total
  ) {
    throw new AdminApiError("invalid_response");
  }
  return {
    answersTotal: feedback.answers_total,
    ratedAnswers: feedback.rated_answers,
    counts: [...feedback.counts],
  };
}

// Stories created in each bucket of the period; together they are all its stories.
function parseActivity(activity, dialogs) {
  if (
    !Array.isArray(activity)
    || activity.length === 0
    || !activity.every(point => isTimestamp(point?.start) && isCount(point.dialogs))
    || activity.reduce((sum, point) => sum + point.dialogs, 0) !== dialogs
  ) {
    throw new AdminApiError("invalid_response");
  }
  return activity.map(point => ({ start: point.start, dialogs: point.dialogs }));
}

function parseStats(body, period) {
  if (
    body?.period !== period
    || !isCount(body.users_total)
    || !isCount(body.active_users)
    || !isCount(body.new_users)
    || !Array.isArray(body.recent_users)
    || !isCount(body.reports_new)
    || !isCount(body.dialogs)
    || !isCount(body.messages)
  ) {
    throw new AdminApiError("invalid_response");
  }
  return {
    period,
    usersTotal: body.users_total,
    activeUsers: body.active_users,
    newUsers: body.new_users,
    recentUsers: body.recent_users.map(parseUser),
    feedback: parseFeedback(body.feedback),
    reportsNew: body.reports_new,
    dialogs: body.dialogs,
    messages: body.messages,
    activity: parseActivity(body.activity, body.dialogs),
  };
}

function parseReport(entry) {
  if (
    !Number.isInteger(entry?.id)
    || !REPORT_REASONS.includes(entry.reason)
    || !isText(entry.comment)
    || !isText(entry.request_text)
    || typeof entry.answer_text !== "string"
    || !REPORT_STATUSES.includes(entry.status)
    || !isTimestamp(entry.created_at)
    || !(entry.resolved_at === null || isTimestamp(entry.resolved_at))
    || typeof entry.dialog_deleted !== "boolean"
  ) {
    throw new AdminApiError("invalid_response");
  }
  return {
    id: entry.id,
    reason: entry.reason,
    comment: entry.comment,
    requestText: entry.request_text,
    answerText: entry.answer_text,
    status: entry.status,
    createdAt: entry.created_at,
    resolvedAt: entry.resolved_at,
    dialogDeleted: entry.dialog_deleted,
  };
}

export class AdminApi {
  constructor({ fetchImpl = globalThis.fetch } = {}) {
    if (typeof fetchImpl !== "function") {
      throw new TypeError("fetchImpl must be a function");
    }
    this.fetchImpl = fetchImpl.bind(globalThis);
  }

  async stats(period) {
    if (!PERIODS.includes(period)) throw new RangeError("unsupported period");
    return parseStats(await this.#readJson(`/api/v1/admin/stats?period=${period}`), period);
  }

  async listReports(filter) {
    if (!REPORT_FILTERS.includes(filter)) throw new RangeError("unsupported filter");
    const body = await this.#readJson(`/api/v1/admin/reports?status=${filter}`);
    if (!Array.isArray(body?.reports)) throw new AdminApiError("invalid_response");
    return body.reports.map(parseReport);
  }

  async setReportStatus(reportId, status) {
    const response = await this.#request(`/api/v1/admin/reports/${encodeURIComponent(reportId)}`, {
      method: "PATCH",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    if (response.status === 404) throw new AdminApiError("not_found");
    if (response.status !== 204) throw new AdminApiError("unavailable");
  }

  async #readJson(url) {
    const response = await this.#request(url, { method: "GET", credentials: "same-origin" });
    if (response.status !== 200) throw new AdminApiError("unavailable");
    try {
      return await response.json();
    } catch {
      throw new AdminApiError("invalid_response");
    }
  }

  async #request(url, init) {
    let response;
    try {
      response = await this.fetchImpl(url, init);
    } catch {
      throw new AdminApiError("unavailable");
    }
    if (response.status === 401) throw new AdminApiError("unauthorized");
    if (response.status === 403) throw new AdminApiError("forbidden");
    return response;
  }
}
