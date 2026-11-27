import { mount } from "svelte";
import { AgentApi } from "../entities/dialog";
import { AuthApi } from "../entities/session";
import { ChatPage, createChat } from "../pages/chat";

mount(ChatPage, {
  target: document.getElementById("app")!,
  props: { model: createChat(new AgentApi(), new AuthApi(), url => window.location.replace(url)) },
});
