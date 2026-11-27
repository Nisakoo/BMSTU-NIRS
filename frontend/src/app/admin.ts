import { mount } from "svelte";
import { AdminApi } from "../entities/admin";
import { AuthApi } from "../entities/session";
import { AdminPage, createDashboard } from "../pages/admin";

mount(AdminPage, {
  target: document.getElementById("app")!,
  props: { model: createDashboard(new AuthApi(), new AdminApi(), url => window.location.replace(url)) },
});
