<script lang="ts">
  import krosh from "../../static/characters/krosh.png";
  import { CopyMessage } from "../../features/copy-message";
  import AnswerActions from "./AnswerActions.svelte";
  import type { ChatMessage, MessageActions } from "./types";
  let { dialogId, messages, greeting, voice, actions, reportId, onreport }: {
    dialogId: string | null; messages: ChatMessage[]; greeting: boolean; voice: string;
    actions: MessageActions; reportId: number | null; onreport: (id: number | null) => void;
  } = $props();
  let container: HTMLDivElement;
  $effect(() => {
    if (messages.length) container.scrollTop = container.scrollHeight;
  });
</script>
<div class="sai-messages" id="saiMessages" aria-live="polite" bind:this={container}>
  {#if greeting}
    <div class="sai-krosh">
      <div class="sai-krosh-pic"><img src={krosh} alt="Крош" width="420" height="420" decoding="async" /></div>
      <p class="sai-krosh-say"><b>Ёлки-иголки, привет!</b> Я Крош. Давай сочиним что-нибудь такое, чтобы даже Кар-Карыч удивился! Кого берём в историю и куда отправимся?</p>
      <p class="sai-krosh-sub">Напиши идею или выбери тему ниже</p>
    </div>
  {/if}
  {#each messages as message}
    <div class="sai-row" class:user={message.role === "user"}>
      {#if message.role === "assistant"}<div class="sai-msg-icon">⭐</div>
      {:else}<CopyMessage text={message.content} onerror={() => actions.notify("Не удалось скопировать", "error")} />{/if}
      <div class="sai-bubble" class:sai-bubble-error={message.error}>{message.content}</div>
      {#if message.role === "assistant" && message.complete}
        <CopyMessage text={message.content} onerror={() => actions.notify("Не удалось скопировать", "error")} />
      {/if}
    </div>
    {#if dialogId && message.role === "assistant" && message.id !== undefined && message.complete}
      <AnswerActions {dialogId} id={message.id} {message} {actions} {voice} open={reportId === message.id} toggle={value => onreport(value ? message.id! : null)} />
    {/if}
  {/each}
</div>
