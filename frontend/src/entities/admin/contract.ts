export const PERIODS = ["7", "30", "90"] as const;
const ROLES = ["user", "admin"] as const;
const STATUSES = ["new", "active", "inactive"] as const;
const REPORT_REASONS = ["scary", "rude", "wrong", "other"] as const;
const REPORT_STATUSES = ["new", "resolved", "dismissed"] as const;
export const REPORT_FILTERS = [...REPORT_STATUSES, "all"] as const;

export class AdminApiError extends Error {
  readonly code: string;

  constructor(code: string) {
    super(code);
    this.name = "AdminApiError";
    this.code = code;
  }
}

export type Period = (typeof PERIODS)[number];
export type ReportStatus = (typeof REPORT_STATUSES)[number];
export type ReportFilter = (typeof REPORT_FILTERS)[number];

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;
const hasValue = <T extends string>(values: readonly T[], value: unknown): value is T =>
  values.some(candidate => candidate === value);
const isCount = (value: unknown): value is number => typeof value === "number" && Number.isInteger(value) && value >= 0;
// counts[i] is the number of answers rated i + 1 out of 5.
const SCORE_COUNT = 5;
const isTimestamp = (value: unknown): value is string => typeof value === "string" && !Number.isNaN(Date.parse(value));
const isText = (value: unknown): value is string | null => value === null || typeof value === "string";

function parseUser(entry: unknown) {
  if (
    !isRecord(entry) || typeof entry.id !== "string" || !entry.id
    || typeof entry.login !== "string" || !entry.login
    || !hasValue(ROLES, entry.role)
    || !isTimestamp(entry.registered_at)
    || !(entry.last_active_at === null || isTimestamp(entry.last_active_at))
    || !hasValue(STATUSES, entry.status)
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

function parseFeedback(feedback: unknown) {
  if (
    !isRecord(feedback) || !isCount(feedback.answers_total)
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
interface ActivityPoint {
  start: string;
  dialogs: number;
}

function isActivityPoint(value: unknown): value is ActivityPoint {
  return isRecord(value) && isTimestamp(value.start) && isCount(value.dialogs);
}

function parseActivity(activity: unknown, dialogs: number): ActivityPoint[] {
  if (
    !Array.isArray(activity)
    || activity.length === 0
    || !activity.every(isActivityPoint)
    || activity.reduce((sum, point) => sum + point.dialogs, 0) !== dialogs
  ) {
    throw new AdminApiError("invalid_response");
  }
  return activity.map(point => ({ start: point.start, dialogs: point.dialogs }));
}

export function parseStats(body: unknown, period: Period) {
  if (
    !isRecord(body) || body.period !== period
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

export function parseReport(entry: unknown) {
  if (
    !isRecord(entry) || typeof entry.id !== "number" || !Number.isInteger(entry.id)
    || !hasValue(REPORT_REASONS, entry.reason)
    || !isText(entry.comment)
    || !isText(entry.request_text)
    || typeof entry.answer_text !== "string"
    || !hasValue(REPORT_STATUSES, entry.status)
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


export type AdminStats = ReturnType<typeof parseStats>;
export type Report = ReturnType<typeof parseReport>;
