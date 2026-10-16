const PERIODS = ["7", "30", "90"];
const ROLES = ["user", "admin"];
const STATUSES = ["new", "active", "inactive"];

export class AdminApiError extends Error {
  constructor(code) {
    super(code);
    this.name = "AdminApiError";
    this.code = code;
  }
}

const isCount = value => Number.isInteger(value) && value >= 0;
const isTimestamp = value => typeof value === "string" && !Number.isNaN(Date.parse(value));

function parseUser(entry) {
  if (
    typeof entry?.id !== "string" || !entry.id
    || typeof entry.login !== "string" || !entry.login
    || !ROLES.includes(entry.role)
    || !isTimestamp(entry.registered_at)
    || !(entry.last_active_at === null || isTimestamp(entry.last_active_at))
    || !STATUSES.includes(entry.status)
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
  };
}

function parseStats(body, period) {
  if (
    body?.period !== period
    || !isCount(body.users_total)
    || !isCount(body.active_users)
    || !isCount(body.new_users)
    || !Array.isArray(body.recent_users)
  ) {
    throw new AdminApiError("invalid_response");
  }
  return {
    period,
    usersTotal: body.users_total,
    activeUsers: body.active_users,
    newUsers: body.new_users,
    recentUsers: body.recent_users.map(parseUser),
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

    let response;
    try {
      response = await this.fetchImpl(
        `/api/v1/admin/stats?period=${period}`,
        { method: "GET", credentials: "same-origin" },
      );
    } catch {
      throw new AdminApiError("unavailable");
    }
    if (response.status === 401) throw new AdminApiError("unauthorized");
    if (response.status === 403) throw new AdminApiError("forbidden");
    if (response.status !== 200) throw new AdminApiError("unavailable");

    let body;
    try {
      body = await response.json();
    } catch {
      throw new AdminApiError("invalid_response");
    }
    return parseStats(body, period);
  }
}
