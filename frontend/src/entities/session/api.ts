export interface User {
  id: string;
  login: string;
  role: 'user' | 'admin';
}

export interface Credentials {
  login: string;
  password: string;
}

export interface PasswordChange {
  currentPassword: string;
  newPassword: string;
}

type ErrorCode = 'invalid_response' | 'unavailable' | 'unauthorized' | 'invalid_fields'
  | 'wrong_password' | 'same_password' | 'invalid_credentials' | 'login_taken' | 'too_many_attempts';

export class AuthApiError extends Error {
  readonly code: ErrorCode;

  constructor(code: ErrorCode) {
    super(code);
    this.name = 'AuthApiError';
    this.code = code;
  }
}

export function errorCode(error: unknown): string {
  return error && typeof error === 'object' && 'code' in error && typeof error.code === 'string'
    ? error.code : '';
}

async function readUser(response: Response): Promise<User> {
  const body: unknown = await response.json().catch(() => null);
  if (!body || typeof body !== 'object'
    || !('id' in body) || typeof body.id !== 'string' || !body.id
    || !('login' in body) || typeof body.login !== 'string' || !body.login
    || !('role' in body) || (body.role !== 'user' && body.role !== 'admin')) {
    throw new AuthApiError('invalid_response');
  }
  return { id: body.id, login: body.login, role: body.role };
}

type Request = { method: 'GET' | 'POST' | 'PUT'; body?: unknown };

export class AuthApi {
  private readonly fetchImpl: typeof fetch;

  constructor({ fetchImpl = globalThis.fetch }: {fetchImpl?: typeof fetch} = {}) {
    if (typeof fetchImpl !== 'function') throw new TypeError('fetchImpl must be a function');
    this.fetchImpl = fetchImpl.bind(globalThis);
  }

  private async send(path: string, { method, body }: Request): Promise<Response> {
    const options: RequestInit = { method, credentials: 'same-origin' };
    if (body !== undefined) {
      options.headers = { 'Content-Type': 'application/json' };
      options.body = JSON.stringify(body);
    }
    try {
      return await this.fetchImpl(path, options);
    } catch {
      throw new AuthApiError('unavailable');
    }
  }

  private async request(path: string, options: Request, status: number, errors: Record<number, ErrorCode> = {}) {
    const response = await this.send(path, options);
    if (response.status !== status) throw new AuthApiError(errors[response.status] ?? 'unavailable');
    return response;
  }

  async register({ login, password }: Credentials) {
    return readUser(await this.request('/api/v1/users', { method: 'POST', body: { login, password } }, 201,
      { 409: 'login_taken', 422: 'invalid_fields', 429: 'too_many_attempts' }));
  }

  async login({ login, password }: Credentials) {
    return readUser(await this.request('/api/v1/auth/login', { method: 'POST', body: { login, password } }, 200,
      { 401: 'invalid_credentials', 422: 'invalid_fields', 429: 'too_many_attempts' }));
  }

  async logout() {
    await this.request('/api/v1/auth/logout', { method: 'POST' }, 204);
  }

  async changePassword({ currentPassword, newPassword }: PasswordChange) {
    const response = await this.send('/api/v1/users/me/password', {
      method: 'PUT', body: { current_password: currentPassword, new_password: newPassword },
    });
    if (response.status === 204) return;
    if (response.status === 422) {
      const body: unknown = await response.json().catch(() => null);
      const same = body && typeof body === 'object' && 'error' in body && body.error === 'same_password';
      throw new AuthApiError(same ? 'same_password' : 'invalid_fields');
    }
    const errors: Record<number, ErrorCode> = { 400: 'wrong_password', 401: 'unauthorized', 429: 'too_many_attempts' };
    throw new AuthApiError(errors[response.status] ?? 'unavailable');
  }

  async refresh() {
    return readUser(await this.request('/api/v1/auth/refresh', { method: 'POST' }, 200, { 401: 'unauthorized' }));
  }

  async me() {
    return readUser(await this.request('/api/v1/users/me', { method: 'GET' }, 200, { 401: 'unauthorized' }));
  }
}
