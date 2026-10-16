const ROLES = ["user", "admin"];

export class AuthApiError extends Error {
  constructor(code) {
    super(code);
    this.name = "AuthApiError";
    this.code = code;
  }
}

function parseUser(body) {
  if (
    typeof body?.id !== "string" || !body.id
    || typeof body.login !== "string" || !body.login
    || !ROLES.includes(body.role)
  ) {
    throw new AuthApiError("invalid_response");
  }
  return { id: body.id, login: body.login, role: body.role };
}

export class AuthApi {
  constructor({ fetchImpl = globalThis.fetch } = {}) {
    if (typeof fetchImpl !== "function") {
      throw new TypeError("fetchImpl must be a function");
    }
    this.fetchImpl = fetchImpl.bind(globalThis);
  }

  async request(path, { method, body }, expectedStatus, errorsByStatus = {}) {
    const options = { method, credentials: "same-origin" };
    if (body !== undefined) {
      options.headers = { "Content-Type": "application/json" };
      options.body = JSON.stringify(body);
    }

    let response;
    try {
      response = await this.fetchImpl(path, options);
    } catch {
      throw new AuthApiError("unavailable");
    }
    if (response.status !== expectedStatus) {
      throw new AuthApiError(errorsByStatus[response.status] ?? "unavailable");
    }
    return response;
  }

  async readUser(response) {
    let body;
    try {
      body = await response.json();
    } catch {
      throw new AuthApiError("invalid_response");
    }
    return parseUser(body);
  }

  async register({ login, password }) {
    const response = await this.request(
      "/api/v1/users",
      { method: "POST", body: { login, password } },
      201,
      { 409: "login_taken", 422: "invalid_fields" },
    );
    return this.readUser(response);
  }

  async login({ login, password }) {
    const response = await this.request(
      "/api/v1/auth/login",
      { method: "POST", body: { login, password } },
      200,
      { 401: "invalid_credentials", 422: "invalid_fields" },
    );
    return this.readUser(response);
  }

  async logout() {
    await this.request("/api/v1/auth/logout", { method: "POST" }, 204);
  }

  async refresh() {
    const response = await this.request(
      "/api/v1/auth/refresh",
      { method: "POST" },
      200,
      { 401: "unauthorized" },
    );
    return this.readUser(response);
  }

  async me() {
    const response = await this.request(
      "/api/v1/users/me",
      { method: "GET" },
      200,
      { 401: "unauthorized" },
    );
    return this.readUser(response);
  }
}
