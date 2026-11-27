// @vitest-environment jsdom
import assert from 'node:assert/strict';
import { afterEach, test, vi } from 'vitest';
import { flushSync, mount as mountComponent, unmount } from 'svelte';
import { AuthApiError } from '../src/entities/session/index.ts';
import { createLogin, LoginPage } from '../src/pages/login/index.ts';

const USER = { id: "user-1", login: "krosh", role: "user" };
const ADMIN = { id: "admin-1", login: "sovunya", role: "admin" };

function fakeApi({
  me = () => Promise.reject(new AuthApiError("unauthorized")),
  register = () => Promise.resolve(USER),
  login = () => Promise.resolve(USER),
  refresh = () => Promise.reject(new AuthApiError("unauthorized")),
} = {}) {
  const calls = [];
  return {
    calls,
    me: (...args) => (calls.push(["me", ...args]), me(...args)),
    refresh: (...args) => (calls.push(["refresh", ...args]), refresh(...args)),
    register: (...args) => (calls.push(["register", ...args]), register(...args)),
    login: (...args) => (calls.push(["login", ...args]), login(...args)),
  };
}

const pages = [];
afterEach(async () => {
  for (const page of pages.splice(0)) await unmount(page);
  document.body.replaceChildren();
  vi.unstubAllGlobals();
});

function settled() {
  return new Promise(resolve => setTimeout(resolve, 0));
}

async function mount(apiOptions) {
  const api = fakeApi(apiOptions);
  const navigations = [];
  const target = document.createElement('div');
  document.body.append(target);
  pages.push(mountComponent(LoginPage, { target, props: { model: createLogin(api, url => navigations.push(url)) } }));
  flushSync();
  await settled();
  const elements = Object.fromEntries(Array.from(target.querySelectorAll('[id]'), el => [el.id, el]));
  return { elements, api, navigations };
}

function fill(elements, { login = "krosh", password = "carrot123", confirm } = {}) {
  elements.authLogin.value = login;
  elements.authPassword.value = password;
  if (confirm !== undefined) elements.authConfirm.value = confirm;
}

function submit(elements) {
  elements.authForm.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  flushSync();
  return settled();
}

test("page starts in login mode and stays for a guest", async () => {
  const { elements, navigations, api } = await mount();

  assert.deepEqual(api.calls, [["me"], ["refresh"]]);
  assert.deepEqual(navigations, []);
  assert.equal(elements.authTabLogin.getAttribute("aria-selected"), "true");
  assert.equal(elements.authTabRegister.getAttribute("aria-selected"), "false");
  assert.equal(elements.authConfirmField.hidden, true);
  assert.equal(elements.authSubmit.textContent, "Войти");
  assert.equal(elements.authSubmit.disabled, false);
});

test("an existing session redirects to the chat", async () => {
  const { navigations } = await mount({ me: () => Promise.resolve(USER) });

  assert.deepEqual(navigations, ["/"]);
});

test("an existing administrator session redirects to the admin panel", async () => {
  const { navigations } = await mount({ me: () => Promise.resolve(ADMIN) });

  assert.deepEqual(navigations, ["/admin/"]);
});

test("an expired access token is renewed with refresh before redirecting", async () => {
  const { api, navigations } = await mount({ refresh: () => Promise.resolve(USER) });

  assert.deepEqual(api.calls, [["me"], ["refresh"]]);
  assert.deepEqual(navigations, ["/"]);
});

test("an unavailable backend keeps the form usable", async () => {
  const { elements, navigations } = await mount({
    me: () => Promise.reject(new AuthApiError("unavailable")),
  });

  assert.deepEqual(navigations, []);
  assert.equal(elements.authSubmit.disabled, false);
  assert.equal(elements.authLogin.disabled, false);
});

test("tabs switch between login and registration", async () => {
  const { elements } = await mount();

  flushSync(() => elements.authTabRegister.click());
  assert.equal(elements.authTabRegister.getAttribute("aria-selected"), "true");
  assert.equal(elements.authTabLogin.getAttribute("aria-selected"), "false");
  assert.equal(elements.authConfirmField.hidden, false);
  assert.equal(elements.authSubmit.textContent, "Зарегистрироваться");
  assert.equal(elements.authPassword.getAttribute("autocomplete"), "new-password");

  flushSync(() => elements.authTabLogin.click());
  assert.equal(elements.authConfirmField.hidden, true);
  assert.equal(elements.authSubmit.textContent, "Войти");
  assert.equal(elements.authPassword.getAttribute("autocomplete"), "current-password");
});

test("invalid fields are reported without a request", async () => {
  const { elements, api } = await mount();

  fill(elements, { login: "kr", password: "short" });
  await submit(elements);

  assert.deepEqual(api.calls, [["me"], ["refresh"]]);
  assert.match(elements.authLoginError.textContent, /от 3 до 32/i);
  assert.match(elements.authPasswordError.textContent, /от 8 до 128/);
  assert.equal(elements.authLogin.getAttribute("aria-invalid"), "true");
  assert.equal(document.activeElement, elements.authLogin);

  fill(elements, { login: "крош", password: "carrot123" });
  await submit(elements);
  assert.deepEqual(api.calls, [["me"], ["refresh"]]);
  assert.match(elements.authLoginError.textContent, /латинские/);
  assert.equal(elements.authPasswordError.textContent, "");
});

test("registration requires a matching confirmation", async () => {
  const { elements, api } = await mount();

  flushSync(() => elements.authTabRegister.click());
  fill(elements, { confirm: "carrot124" });
  await submit(elements);

  assert.deepEqual(api.calls, [["me"], ["refresh"]]);
  assert.equal(elements.authConfirmError.textContent, "Пароли не совпадают");
});

test("successful login redirects to the chat", async () => {
  const { elements, api, navigations } = await mount();

  fill(elements, { login: "  krosh " });
  await submit(elements);

  assert.deepEqual(api.calls.at(-1), ["login", { login: "krosh", password: "carrot123" }]);
  assert.deepEqual(navigations, ["/"]);
});

test("successful registration logs in and redirects to the chat", async () => {
  const { elements, api, navigations } = await mount();

  flushSync(() => elements.authTabRegister.click());
  fill(elements, { confirm: "carrot123" });
  await submit(elements);

  const credentials = { login: "krosh", password: "carrot123" };
  assert.deepEqual(api.calls.slice(2), [["register", credentials], ["login", credentials]]);
  assert.deepEqual(navigations, ["/"]);
});

test("successful administrator login redirects to the admin panel", async () => {
  const { elements, navigations } = await mount({ login: () => Promise.resolve(ADMIN) });

  fill(elements, { login: "sovunya" });
  await submit(elements);

  assert.deepEqual(navigations, ["/admin/"]);
});

test("API errors show a message, keep the login and clear passwords", async () => {
  const cases = [
    ["register", "login_taken", "Этот логин уже занят"],
    ["login", "invalid_credentials", "Неверный логин или пароль"],
    ["login", "invalid_fields", "Проверьте логин и пароль"],
    ["login", "too_many_attempts", "Слишком много попыток. Попробуйте позже"],
    ["register", "too_many_attempts", "Слишком много попыток. Попробуйте позже"],
    ["login", "unavailable", "Сервис временно недоступен. Попробуйте позже"],
    ["login", "invalid_response", "Сервис временно недоступен. Попробуйте позже"],
  ];

  for (const [method, code, message] of cases) {
    const { elements, navigations } = await mount({
      [method]: () => Promise.reject(new AuthApiError(code)),
    });
    if (method === "register") flushSync(() => elements.authTabRegister.click());
    fill(elements, { confirm: "carrot123" });
    await submit(elements);

    assert.equal(elements.authMessage.textContent, message, code);
    assert.equal(elements.authLogin.value, "krosh");
    assert.equal(elements.authPassword.value, "");
    assert.equal(elements.authConfirm.value, "");
    assert.equal(elements.authSubmit.disabled, false);
    assert.deepEqual(navigations, []);
  }
});

test("the form is locked while a request is pending", async () => {
  let resolveLogin;
  const { elements, api } = await mount({
    login: () => new Promise(resolve => { resolveLogin = resolve; }),
  });

  fill(elements);
  const pending = submit(elements);

  for (const id of ["authSubmit", "authLogin", "authPassword", "authConfirm", "authTabLogin", "authTabRegister"]) {
    assert.equal(elements[id].disabled, true, id);
  }
  assert.equal(elements.authForm.getAttribute("aria-busy"), "true");

  await submit(elements);
  flushSync(() => elements.authTabRegister.click());
  assert.equal(api.calls.filter(([name]) => name === "login").length, 1);
  assert.equal(elements.authConfirmField.hidden, true);

  resolveLogin(USER);
  await pending;
});

test("passwords never reach browser storage", async () => {
  const touched = [];
  const storage = new Proxy({}, { get: (_target, key) => touched.push(key) });
  vi.stubGlobal('localStorage', storage);
  vi.stubGlobal('sessionStorage', storage);
  const { elements } = await mount();
  flushSync(() => elements.authTabRegister.click());
  fill(elements, { confirm: "carrot123" });
  await submit(elements);
  assert.deepEqual(touched, []);
});

test('an older session check cannot replace a successful manual sign-in', async () => {
  let finishCheck;
  const { elements, navigations } = await mount({
    me: () => new Promise(resolve => { finishCheck = resolve; }),
  });
  fill(elements);
  await submit(elements);
  finishCheck(ADMIN);
  await settled();
  assert.deepEqual(navigations, ['/']);
});
