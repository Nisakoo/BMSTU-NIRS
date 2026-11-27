<script lang="ts">
  import krosh from "../../static/characters/krosh.png";
  import { CopyMessage } from "../../features/copy-message";
  import StoryWaiting from "./StoryWaiting.svelte";
  import AnswerActions from "./AnswerActions.svelte";
  import type { ChatMessage, MessageActions } from "./types";
  let { dialogId, messages, greeting, submitting, processing, voice, actions, reportId, onreport }: {
    dialogId: string | null; messages: ChatMessage[]; greeting: boolean; submitting: boolean; processing: boolean; voice: string;
    actions: MessageActions; reportId: number | null; onreport: (id: number | null) => void;
  } = $props();
  let last = $derived(messages.at(-1));
  let waiting = $derived(submitting || (processing && (last?.role !== "assistant" || last.complete || !last.content.trim())));
</script>
<span class="sai-sr-only" role="status">{waiting ? "Смешарики сочиняют историю…" : ""}</span>
<div class="sai-messages" id="saiMessages" role="log" aria-label="Сообщения истории" aria-live="polite" aria-busy={processing || submitting}>
  {#if greeting && !waiting}
    <div class="sai-krosh">
      <div class="sai-krosh-pic"><img src={krosh} alt="Крош" width="420" height="420" decoding="async" /></div>
      <p class="sai-krosh-say"><b>Ёлки-иголки, привет!</b> Я Крош. Давай сочиним что-нибудь такое, чтобы даже Кар-Карыч удивился! Кого берём в историю и куда отправимся?</p>
      <p class="sai-krosh-sub">Напиши идею или выбери тему ниже</p>
    </div>
  {/if}
  {#each messages.filter(m => m.role === "user" || m.complete || m.content.trim()) as message}
    <div class="sai-row" class:user={message.role === "user"}>
      {#if message.role === "assistant"}<div class="sai-msg-icon" aria-hidden="true">⭐</div>
      {:else}<CopyMessage text={message.content} onerror={() => actions.notify("Не удалось скопировать", "error")} />{/if}
      <div class="sai-bubble" class:sai-bubble-error={message.error}>{message.content}</div>
      {#if message.role === "assistant" && message.complete}
        <CopyMessage text={message.content} onerror={() => actions.notify("Не удалось скопировать", "error")} />
      {:else if message.role === "assistant"}
        <span class="sai-copy-space" aria-hidden="true"></span>
      {/if}
    </div>
    {#if dialogId && message.role === "assistant" && message.id !== undefined && message.complete}
      <AnswerActions {dialogId} id={message.id} {message} {actions} {voice} open={reportId === message.id} toggle={value => onreport(value ? message.id! : null)} />
    {/if}
  {/each}
  {#if waiting}<StoryWaiting />{/if}
</div>
