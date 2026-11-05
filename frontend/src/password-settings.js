// The "Настройки" window with the password change, shared by the chat and /admin/.
// The page passes its elements and a changePassword that already handles 401.

// Password limits and messages of the settings window; the backend checks the same.
const PASSWORD_MIN_LENGTH = 8;
const PASSWORD_MAX_LENGTH = 128;
const PASSWORD_LENGTH_ERROR = "Пароль должен быть от 8 до 128 символов";
const PASSWORD_SAME_ERROR = "Новый пароль совпадает с текущим";
const PASSWORD_ERRORS = {
  wrong_password: "Неверный текущий пароль",
  same_password: PASSWORD_SAME_ERROR,
  invalid_fields: PASSWORD_LENGTH_ERROR,
  too_many_attempts: "Слишком много попыток. Попробуйте позже",
};
const PASSWORD_FAILED = "Не удалось сменить пароль. Попробуйте ещё раз";
const PASSWORD_CHANGED = "Пароль изменён. На других устройствах нужно войти заново";

function passwordProblem(current, next, repeat) {
  const fits = value => value.length >= PASSWORD_MIN_LENGTH && value.length <= PASSWORD_MAX_LENGTH;
  if (!fits(current) || !fits(next)) return PASSWORD_LENGTH_ERROR;
  if (next !== repeat) return "Пароли не совпадают";
  if (next === current) return PASSWORD_SAME_ERROR;
  return null;
}

export function mountPasswordSettings({
  button,
  dialog,
  close,
  form,
  currentPassword,
  newPassword,
  repeatPassword,
  save,
  status,
  changePassword,
  beforeOpen = () => {},
  isUnloading = () => false,
}) {
  const fields = [currentPassword, newPassword, repeatPassword];
  let changing = false;

  const setStatus = (text, state = "") => {
    status.textContent = text;
    status.dataset.state = state;
  };

  const lock = locked => {
    for (const control of [...fields, save, close]) control.disabled = locked;
  };

  const open = () => {
    beforeOpen();
    dialog.hidden = false;
    button.setAttribute("aria-expanded", "true");
    setStatus("");
    currentPassword.focus();
  };

  // The window stays open while the password is being saved.
  const closeWindow = () => {
    if (dialog.hidden || changing) return;
    dialog.hidden = true;
    button.setAttribute("aria-expanded", "false");
    for (const field of fields) field.value = "";
    setStatus("");
    button.focus();
  };

  const submit = async () => {
    if (changing) return;
    const current = currentPassword.value;
    const next = newPassword.value;
    const problem = passwordProblem(current, next, repeatPassword.value);
    if (problem) {
      setStatus(problem, "error");
      return;
    }
    changing = true;
    lock(true);
    setStatus("Сохраняем…");
    let failure = null;
    try {
      await changePassword({ currentPassword: current, newPassword: next });
    } catch (error) {
      failure = error;
    }
    changing = false;
    lock(false);
    if (isUnloading()) return;
    if (failure === null) {
      for (const field of fields) field.value = "";
      setStatus(PASSWORD_CHANGED, "ok");
      return;
    }
    setStatus(PASSWORD_ERRORS[failure?.code] ?? PASSWORD_FAILED, "error");
    if (failure?.code === "wrong_password") {
      currentPassword.value = "";
      currentPassword.focus();
    }
  };

  button.addEventListener("click", open);
  close.addEventListener("click", closeWindow);
  dialog.addEventListener("click", event => {
    if (event.target === dialog) closeWindow();
  });
  form.addEventListener("submit", event => {
    event.preventDefault();
    return submit();
  });

  return { isOpen: () => !dialog.hidden, close: closeWindow };
}
