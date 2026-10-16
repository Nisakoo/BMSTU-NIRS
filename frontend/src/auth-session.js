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

export async function refreshSession(api) {
  try {
    return { status: SESSION.USER, user: await api.refresh() };
  } catch (error) {
    return outcome(error);
  }
}

// Only a 401 means "no session": a failing backend must not log the user out.
export async function checkSession(api) {
  try {
    return { status: SESSION.USER, user: await api.me() };
  } catch (error) {
    if (error?.code !== "unauthorized") return outcome(error);
  }
  return refreshSession(api);
}

export function homeFor(user) {
  return user.role === "admin" ? ADMIN_PATH : CHAT_PATH;
}
