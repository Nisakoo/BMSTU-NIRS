import assert from "node:assert/strict";
import test from "node:test";

import { AuthApiError } from "../src/auth-api.js";
import { mountLogin } from "../src/login/login.js";

class FakeElement {
  constructor(id) {
    this.id = id;
    this.value = "";
    this.hidden = false;
    this.disabled = false;
    this.textContent = "";
    this.dataset = {};
    this.attributes = new Map();
    this.listeners = new Map();
    this.focused = false;
  }

  addEventListener(type, listener) {
    this.listeners.set(type, listener);
  }

  dispatch(type) {
    return this.listeners.get(type)?.({ preventDefault() {} });
  }

  click() {
    return this.dispatch("click");
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    return this.attributes.get(name) ?? null;
  }

  removeAttribute(name) {
    this.attributes.delete(name);
  }

  focus() {
    this.focused = true;
  }

  set innerHTML(_value) {
    throw new Error("dynamic innerHTML is forbidden");
  }
}

const IDS = [
  "authForm",
  "authTabLogin",
  "authTabRegister",
  "authSubtitle",
  "authLogin",
  "authLoginError",
  "authPassword",
  "authPasswordError",
  "authConfirmField",
  "authConfirm",
  "authConfirmError",
  "authMessage",
  "authSubmit",
];

function createDocument() {
  const elements = Object.fromEntries(IDS.map(id => [id, new FakeElement(id)]));
  elements.authTabLogin.dataset.mode = "login";
  elements.authTabRegister.dataset.mode = "register";
  elements.authConfirmField.hidden = true;
  return {
    elements,
    querySelector(selector) {
      return elements[selector.replace(/^#/, "")] ?? null;
    },
  };
}

const USER = { id: "user-1", login: "krosh", role: "user" };

function fakeApi({
  me = () => Promise.reject(new AuthApiError("unauthorized")),
  register = () => Promise.resolve(USER),
  login = () => Promise.resolve(USER),
} = {}) {
  const calls = [];
  return {
    calls,
    me: (...args) => (calls.push(["me", ...args]), me(...args)),
    register: (...args) => (calls.push(["register", ...args]), register(...args)),
    login: (...args) => (calls.push(["login", ...args]), login(...args)),
  };
}

async function mount(apiOptions) {
  const documentRef = createDocument();
  const api = fakeApi(apiOptions);
  const navigations = [];
  const page = mountLogin(documentRef, { api, navigate: url => navigations.push(url) });
  await page.ready;
  return { ...documentRef, api, navigations };
}

function fill(elements, { login = "krosh", password = "carrot123", confirm } = {}) {
  elements.authLogin.value = login;
  elements.authPassword.value = password;
  if (confirm !== undefined) elements.authConfirm.value = confirm;
}

function submit(elements) {
  return elements.authForm.dispatch("submit");
}

test("page starts in login mode and stays for a guest", async () => {
  const { elements, navigations, api } = await mount();

  assert.deepEqual(api.calls, [["me"]]);
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

  elements.authTabRegister.click();
  assert.equal(elements.authTabRegister.getAttribute("aria-selected"), "true");
  assert.equal(elements.authTabLogin.getAttribute("aria-selected"), "false");
  assert.equal(elements.authConfirmField.hidden, false);
  assert.equal(elements.authSubmit.textContent, "Зарегистрироваться");
  assert.equal(elements.authPassword.getAttribute("autocomplete"), "new-password");

  elements.authTabLogin.click();
  assert.equal(elements.authConfirmField.hidden, true);
  assert.equal(elements.authSubmit.textContent, "Войти");
  assert.equal(elements.authPassword.getAttribute("autocomplete"), "current-password");
});

test("invalid fields are reported without a request", async () => {
  const { elements, api } = await mount();

  fill(elements, { login: "kr", password: "short" });
  await submit(elements);

  assert.deepEqual(api.calls, [["me"]]);
  assert.match(elements.authLoginError.textContent, /от 3 до 32/i);
  assert.match(elements.authPasswordError.textContent, /от 8 до 128/);
  assert.equal(elements.authLogin.getAttribute("aria-invalid"), "true");
  assert.equal(elements.authLogin.focused, true);

  fill(elements, { login: "крош", password: "carrot123" });
  await submit(elements);
  assert.deepEqual(api.calls, [["me"]]);
  assert.match(elements.authLoginError.textContent, /латинские/);
  assert.equal(elements.authPasswordError.textContent, "");
});

test("registration requires a matching confirmation", async () => {
  const { elements, api } = await mount();

  elements.authTabRegister.click();
  fill(elements, { confirm: "carrot124" });
  await submit(elements);

  assert.deepEqual(api.calls, [["me"]]);
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

  elements.authTabRegister.click();
  fill(elements, { confirm: "carrot123" });
  await submit(elements);

  const credentials = { login: "krosh", password: "carrot123" };
  assert.deepEqual(api.calls.slice(1), [["register", credentials], ["login", credentials]]);
  assert.deepEqual(navigations, ["/"]);
});

test("API errors show a message, keep the login and clear passwords", async () => {
  const cases = [
    ["register", "login_taken", "Этот логин уже занят"],
    ["login", "invalid_credentials", "Неверный логин или пароль"],
    ["login", "invalid_fields", "Проверьте логин и пароль"],
    ["login", "unavailable", "Сервис временно недоступен. Попробуйте позже"],
    ["login", "invalid_response", "Сервис временно недоступен. Попробуйте позже"],
  ];

  for (const [method, code, message] of cases) {
    const { elements, navigations } = await mount({
      [method]: () => Promise.reject(new AuthApiError(code)),
    });
    if (method === "register") elements.authTabRegister.click();
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
  elements.authTabRegister.click();
  assert.equal(api.calls.filter(([name]) => name === "login").length, 1);
  assert.equal(elements.authConfirmField.hidden, true);

  resolveLogin(USER);
  await pending;
});

test("passwords never reach browser storage", async () => {
  const touched = [];
  const storage = new Proxy({}, { get: (_target, key) => touched.push(key) });
  globalThis.localStorage = storage;
  globalThis.sessionStorage = storage;
  try {
    const { elements } = await mount();
    elements.authTabRegister.click();
    fill(elements, { confirm: "carrot123" });
    await submit(elements);
    assert.deepEqual(touched, []);
  } finally {
    delete globalThis.localStorage;
    delete globalThis.sessionStorage;
  }
});
