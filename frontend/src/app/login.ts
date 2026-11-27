import { mount } from 'svelte';
import { createLogin, LoginPage } from '../pages/login';
import { AuthApi } from '../entities/session';

mount(LoginPage, {
  target: document.getElementById('app')!,
  props: { model: createLogin(new AuthApi(), url => window.location.assign(url)) },
});
