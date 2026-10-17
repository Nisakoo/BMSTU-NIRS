export const LOGIN_PATH = "/login/";
export const CHAT_PATH = "/";
export const ADMIN_PATH = "/admin/";

export const SESSION = Object.freeze({
  USER: "user",
  ANONYMOUS: "anonymous",
  UNAVAILABLE: "unavailable",
});

function outcome(error) {
  return { status: error?.code === "unauthorized" ? SESSION.ANONYMOUS : SESSION.UNAVAILABLE };
}

export const REFRESH_LOCK = "smeshariki-auth-refresh";

async function callRefresh(api) {
  try {
    return { status: SESSION.USER, user: await api.refresh() };
  } catch (error) {
    return outcome(error);
  }
}

// A refresh token is single-use: tabs of one origin take turns, and a tab that
// waited first looks for the session another tab has just renewed.
async function refreshOnce(api) {
  try {
    return { status: SESSION.USER, user: await api.me() };
  } catch (error) {
    if (error?.code !== "unauthorized") return outcome(error);
  }
  return callRefresh(api);
}

export async function refreshSession(api, { locks = globalThis.navigator?.locks } = {}) {
  if (typeof locks?.request !== "function") return callRefresh(api);
  return locks.request(REFRESH_LOCK, () => refreshOnce(api));
}

// Only a 401 means "no session": a failing backend must not log the user out.
export async function checkSession(api, options) {
  try {
    return { status: SESSION.USER, user: await api.me() };
  } catch (error) {
    if (error?.code !== "unauthorized") return outcome(error);
  }
  return refreshSession(api, options);
}

export function homeFor(user) {
  return user.role === "admin" ? ADMIN_PATH : CHAT_PATH;
}
