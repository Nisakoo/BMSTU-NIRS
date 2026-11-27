<script lang="ts">
  import { onMount, tick } from "svelte";
  import { PasswordSettings } from "../../features/password";
  import { Transcript } from "../../widgets/chat-transcript";
  import type { createChat } from "./model/chat";
  import { busy } from "./model/state";
  import Composer from "./ui/Composer.svelte";
  import News from "./ui/News.svelte";
  import Sidebar from "./ui/Sidebar.svelte";

  import "./chat.css";

  let { model: chat }: { model: ReturnType<typeof createChat> } = $props();
  let store = $derived(chat.store);
  let locked = $derived(busy($store));
  let title = $derived($store.dialogs.find(d => d.dialogId === $store.dialogId)?.title || $store.title);
  let dialogId = $derived($store.dialogId);
  let actions = $derived(chat.actions(dialogId ?? ""));
  let sidebar = $state(false);
  let settings = $state(false);
  let settingsButton: HTMLButtonElement;
  let reportId = $state<number | null>(null);
  function openSettings(trigger: HTMLButtonElement) {
    settingsButton = trigger;
    reportId = null;
    settings = true;
  }
  async function closeSettings() {
    settings = false;
    await tick();
    settingsButton.focus();
  }
  function open(id: string) {
    reportId = null;
    void chat.open(id);
  }
  onMount(() => { void chat.start(); return chat.destroy; });
</script>
<svelte:window onbeforeunload={chat.destroy} />
<div class="sai" aria-label="Сервис генерации историй со Смешариками">
  <Sidebar chat={$store} {locked} open={sidebar} {settings} {openSettings} create={() => { reportId = null; void chat.create(); }}
    select={open} remove={chat.remove} reload={chat.list} logout={chat.logout} close={() => sidebar = false} />
  <button class="sai-backdrop" id="saiBackdrop" type="button" aria-label="Закрыть список историй" hidden={!sidebar} onclick={() => sidebar = false}></button>
  <PasswordSettings variant="chat" open={settings} onclose={closeSettings} changePassword={chat.changePassword} isUnloading={chat.isUnloading} />
  <main class="sai-main" aria-label="Чат с ИИ">
    <div class="sai-stars" aria-hidden="true"></div>
    <div class="sai-landscape" aria-hidden="true">
      <svg viewBox="0 0 1200 430" preserveAspectRatio="none">
        <defs>
          <linearGradient id="saiHillBack" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1d5a4c"/><stop offset="1" stop-color="#123b34"/></linearGradient>
          <linearGradient id="saiHillMid" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#246b55"/><stop offset="1" stop-color="#174738"/></linearGradient>
          <linearGradient id="saiGrass" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2d7a57"/><stop offset=".62" stop-color="#225e47"/><stop offset="1" stop-color="#153f34"/></linearGradient>
        </defs>
        <path d="M0 191 C118 132 224 137 338 189 C451 240 551 170 671 160 C815 149 901 229 1018 196 C1087 176 1143 153 1200 171 L1200 430 L0 430 Z" fill="url(#saiHillBack)"/>
        <path d="M0 244 C146 183 253 197 384 246 C523 299 609 216 752 211 C899 206 994 279 1200 221 L1200 430 L0 430 Z" fill="url(#saiHillMid)"/>
        <path d="M0 286 C198 243 340 266 503 301 C667 337 820 275 983 274 C1085 274 1148 289 1200 306 L1200 430 L0 430 Z" fill="url(#saiGrass)"/>
      </svg>
    </div>
    <header class="sai-chat-head">
      <button class="sai-history-toggle" id="saiHistoryToggle" type="button" aria-controls="saiSidebar" aria-expanded={sidebar} onclick={() => sidebar = true}>Истории</button>
      <div class="sai-heading">
        <h1 class="sai-title" id="saiTitle" {title}>{title}</h1>
      </div>
    </header>
    <News news={$store.news} dismiss={chat.dismissNews} {open} />
    {#key dialogId}
      <Transcript {dialogId} transcriptLoaded={$store.transcriptLoaded} messages={$store.messages} submitting={$store.submitting} processing={$store.processing} greeting={$store.greeting} voice={$store.voice} {actions} {reportId} onreport={id => reportId = id} />
    {/key}
    <div class="sai-notice" role="status" data-kind={$store.notice?.kind}>{$store.notice?.text ?? ""}</div>
    <Composer disabled={!$store.ready || !$store.user || $store.loggingOut || $store.hydrating || $store.switching || $store.deletingId !== null} waiting={$store.submitting || $store.processing} voice={$store.voice} {settings} chooseVoice={chat.chooseVoice} submit={chat.submit} />
  </main>
</div>
