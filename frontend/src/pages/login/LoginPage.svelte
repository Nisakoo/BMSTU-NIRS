<script lang="ts">
  import { onMount, tick } from 'svelte';
  import type { createLogin } from './model';
  import friends from '../../static/characters/smeshariki.png';
  import './login.css';

  let { model }: { model: ReturnType<typeof createLogin> } = $props();
  let registering = $derived($model.mode === 'register');
  let loginInput: HTMLInputElement;
  let passwordInput: HTMLInputElement;
  let confirmInput: HTMLInputElement;

  onMount(() => {
    void model.check();
    return model.destroy;
  });

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    const result = await model.submit({ login: loginInput.value.trim(), password: passwordInput.value }, confirmInput.value);
    if (!result) return;
    await tick();
    if (result.clearPasswords) {
      passwordInput.value = '';
      confirmInput.value = '';
    }
    const inputs = { login: loginInput, password: passwordInput, confirm: confirmInput };
    inputs[result.focus].focus();
  }
</script>

<main class="auth">
  <section class="auth-scene">
    <div class="auth-moon" aria-hidden="true"></div>

    <div class="auth-landscape" aria-hidden="true">
      <svg viewBox="0 0 1200 430" preserveAspectRatio="none">
        <defs>
          <linearGradient id="authHillBack" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1d5a4c"/><stop offset="1" stop-color="#123b34"/></linearGradient>
          <linearGradient id="authHillMid" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#246b55"/><stop offset="1" stop-color="#174738"/></linearGradient>
          <linearGradient id="authGrass" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2d7a57"/><stop offset=".62" stop-color="#225e47"/><stop offset="1" stop-color="#153f34"/></linearGradient>
          <filter id="authGlow" x="-200%" y="-200%" width="400%" height="400%"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        </defs>
        <path d="M0 191 C118 132 224 137 338 189 C451 240 551 170 671 160 C815 149 901 229 1018 196 C1087 176 1143 153 1200 171 L1200 430 L0 430 Z" fill="url(#authHillBack)"/>
        <path d="M0 244 C146 183 253 197 384 246 C523 299 609 216 752 211 C899 206 994 279 1200 221 L1200 430 L0 430 Z" fill="url(#authHillMid)"/>
        <path d="M0 286 C198 243 340 266 503 301 C667 337 820 275 983 274 C1085 274 1148 289 1200 306 L1200 430 L0 430 Z" fill="url(#authGrass)"/>
        <g fill="#fff" opacity=".92">
          <g transform="translate(178 350)"><circle cx="0" cy="-7" r="5"/><circle cx="7" cy="0" r="5"/><circle cx="0" cy="7" r="5"/><circle cx="-7" cy="0" r="5"/><circle cx="0" cy="0" r="4" fill="#ffd84d"/></g>
          <g transform="translate(801 370) scale(.9)"><circle cx="0" cy="-7" r="5"/><circle cx="7" cy="0" r="5"/><circle cx="0" cy="7" r="5"/><circle cx="-7" cy="0" r="5"/><circle cx="0" cy="0" r="4" fill="#ffd84d"/></g>
          <g transform="translate(1090 382) scale(.75)"><circle cx="0" cy="-7" r="5"/><circle cx="7" cy="0" r="5"/><circle cx="0" cy="7" r="5"/><circle cx="-7" cy="0" r="5"/><circle cx="0" cy="0" r="4" fill="#ffd84d"/></g>
        </g>
        <g fill="#ffe775" filter="url(#authGlow)"><circle cx="144" cy="304" r="2.2"/><circle cx="338" cy="327" r="2"/><circle cx="781" cy="312" r="2.1"/><circle cx="1077" cy="320" r="2.2"/></g>
      </svg>
    </div>

    <a class="auth-brand" href="/"><span class="auth-mark" aria-hidden="true">✦</span>Смешарики AI</a>

    <div class="auth-layout">
      <div class="auth-side">
        <div class="auth-intro">
          <p class="auth-intro-title">Сочиняй истории<br>вместе со <span>Смешариками</span></p>
        </div>

        <figure class="auth-friends">
          <img src={friends} alt="Смешарики радостно машут лапами" width="1200" height="508" decoding="async" />
        </figure>
      </div>

      <section class="auth-card" aria-labelledby="authTitle">
        <header class="auth-card-head">
          <h1 id="authTitle">Заходи в<br>Ромашковую долину</h1>
          <p id="authSubtitle">{registering ? "Новый аккаунт" : "Вход в аккаунт"}</p>
        </header>

        <div class="auth-tabs" role="tablist" aria-label="Режим">
          <button type="button" role="tab" id="authTabLogin" data-mode="login" aria-selected={!registering} disabled={$model.busy} onclick={() => model.select('login')}>Вход</button>
          <button type="button" role="tab" id="authTabRegister" data-mode="register" aria-selected={registering} disabled={$model.busy} onclick={() => model.select('register')}>Регистрация</button>
        </div>

        <form class="auth-form" id="authForm" method="post" novalidate aria-busy={$model.busy} onsubmit={submit}>
          <div class="auth-field">
            <label for="authLogin">Логин</label>
            <input id="authLogin" bind:this={loginInput} disabled={$model.busy} aria-invalid={$model.errors.login ? true : undefined} name="login" type="text" autocomplete="username" autocapitalize="none" spellcheck="false" maxlength="32" aria-describedby="authLoginError" placeholder="например, krosh" required />
            <p class="auth-field-error" id="authLoginError">{$model.errors.login ?? ""}</p>
          </div>
          <div class="auth-field">
            <label for="authPassword">Пароль</label>
            <input id="authPassword" bind:this={passwordInput} disabled={$model.busy} aria-invalid={$model.errors.password ? true : undefined} name="password" type="password" autocomplete={registering ? "new-password" : "current-password"} maxlength="128" aria-describedby="authPasswordError" placeholder="не меньше 8 символов" required />
            <p class="auth-field-error" id="authPasswordError">{$model.errors.password ?? ""}</p>
          </div>
          <div class="auth-field" id="authConfirmField" hidden={!registering}>
            <label for="authConfirm">Повторите пароль</label>
            <input id="authConfirm" bind:this={confirmInput} disabled={$model.busy} aria-invalid={$model.errors.confirm ? true : undefined} name="confirm" type="password" autocomplete="new-password" maxlength="128" aria-describedby="authConfirmError" />
            <p class="auth-field-error" id="authConfirmError">{$model.errors.confirm ?? ""}</p>
          </div>
          <p class="auth-message" id="authMessage" role="alert" aria-live="assertive">{$model.message}</p>
          <button class="auth-submit" id="authSubmit" type="submit" disabled={$model.busy}>{registering ? "Зарегистрироваться" : "Войти"}</button>
        </form>
      </section>
    </div>
  </section>
</main>
