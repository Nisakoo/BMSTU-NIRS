import { AuthApi } from "../auth-api.js";
import { SESSION, checkSession, homeFor } from "../auth-session.js";

const LOGIN_PATTERN = /^[A-Za-z0-9_.-]{3,32}$/;
const UNAVAILABLE_MESSAGE = "Сервис временно недоступен. Попробуйте позже";

const ERROR_MESSAGES = Object.freeze({
  login_taken: "Этот логин уже занят",
  invalid_credentials: "Неверный логин или пароль",
  invalid_fields: "Проверьте логин и пароль",
});

const MODES = Object.freeze({
  login: {
    subtitle: "Вход в аккаунт",
    submit: "Войти",
    passwordAutocomplete: "current-password",
  },
  register: {
    subtitle: "Новый аккаунт",
    submit: "Зарегистрироваться",
    passwordAutocomplete: "new-password",
  },
});

function validate(mode, { login, password, confirm }) {
  const errors = {};
  if (!LOGIN_PATTERN.test(login)) {
    errors.login = "От 3 до 32 символов: латинские буквы, цифры, «_», «.» или «-»";
  }
  if (password.length < 8 || password.length > 128) {
    errors.password = "Пароль должен быть от 8 до 128 символов";
  }
  if (mode === "register" && confirm !== password) {
    errors.confirm = "Пароли не совпадают";
  }
  return errors;
}

export function mountLogin(documentRef, { api, navigate }) {
  const $ = id => documentRef.querySelector(`#${id}`);
  const form = $("authForm");
  const tabs = [$("authTabLogin"), $("authTabRegister")];
  const subtitle = $("authSubtitle");
  const submitButton = $("authSubmit");
  const message = $("authMessage");
  const confirmField = $("authConfirmField");
  const fields = {
    login: { input: $("authLogin"), error: $("authLoginError") },
    password: { input: $("authPassword"), error: $("authPasswordError") },
    confirm: { input: $("authConfirm"), error: $("authConfirmError") },
  };

  let mode = "login";
  let busy = false;

  const showErrors = (errors = {}) => {
    for (const [name, field] of Object.entries(fields)) {
      field.error.textContent = errors[name] ?? "";
      if (errors[name]) {
        field.input.setAttribute("aria-invalid", "true");
      } else {
        field.input.removeAttribute("aria-invalid");
      }
    }
  };

  const setMode = nextMode => {
    mode = nextMode;
    const config = MODES[mode];
    for (const tab of tabs) {
      tab.setAttribute("aria-selected", String(tab.dataset.mode === mode));
    }
    confirmField.hidden = mode !== "register";
    subtitle.textContent = config.subtitle;
    submitButton.textContent = config.submit;
    fields.password.input.setAttribute("autocomplete", config.passwordAutocomplete);
    message.textContent = "";
    showErrors();
  };

  const setBusy = value => {
    busy = value;
    for (const element of [submitButton, ...tabs, ...Object.values(fields).map(field => field.input)]) {
      element.disabled = value;
    }
    form.setAttribute("aria-busy", String(value));
  };

  const clearPasswords = () => {
    fields.password.input.value = "";
    fields.confirm.input.value = "";
  };

  const handleSubmit = async event => {
    event.preventDefault();
    if (busy) return;

    const values = {
      login: fields.login.input.value.trim(),
      password: fields.password.input.value,
      confirm: fields.confirm.input.value,
    };
    message.textContent = "";
    const errors = validate(mode, values);
    showErrors(errors);
    const firstInvalid = Object.keys(fields).find(name => errors[name]);
    if (firstInvalid) {
      fields[firstInvalid].input.focus();
      return;
    }

    const credentials = { login: values.login, password: values.password };
    setBusy(true);
    try {
      if (mode === "register") await api.register(credentials);
      const user = await api.login(credentials);
      navigate(homeFor(user));
    } catch (error) {
      message.textContent = ERROR_MESSAGES[error?.code] ?? UNAVAILABLE_MESSAGE;
      clearPasswords();
      setBusy(false);
      fields.password.input.focus();
    }
  };

  for (const tab of tabs) {
    tab.addEventListener("click", () => {
      if (!busy) setMode(tab.dataset.mode);
    });
  }
  form.addEventListener("submit", handleSubmit);
  setMode("login");

  const ready = checkSession(api).then(session => {
    if (session.status === SESSION.USER) navigate(homeFor(session.user));
  });
  return { ready };
}

if (typeof document !== "undefined") {
  mountLogin(document, {
    api: new AuthApi(),
    navigate: url => window.location.assign(url),
  });
}
