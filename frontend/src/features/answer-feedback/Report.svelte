<script lang="ts">
  import { tick, untrack } from "svelte";
  import { createReport } from "./model";
  let { initial, open, toggle, send, notify }: {
    initial: "sent" | "reviewed" | null; open: boolean; toggle: (value: boolean) => void;
    send: (reason: string, comment: string) => Promise<void>; notify: (text: string, kind?: "error") => void;
  } = $props();
  const reasons = [["scary","Страшно"],["rude","Грубо или обидно"],["wrong","Неправильно или непонятно"],["other","Другое"]];
  const model = untrack(() => createReport(initial, send));
  let status = $derived($model.status);
  let label = $derived(status === "sent" ? "Жалоба отправлена" : status === "reviewed" ? "Взрослые посмотрели — спасибо!" : "Пожаловаться");
  let reason = $state("");
  let comment = $state("");
  let pending = $derived($model.pending);
  let flag: HTMLButtonElement;
  let choices = $state<HTMLDivElement>();
  let disabled = $derived(pending || !reason || (reason === "other" && !comment.trim()));
  async function togglePanel() {
    if (open) { toggle(false); return; }
    reason = comment = "";
    toggle(true);
    await tick();
    choices?.querySelector("button")?.focus();
  }
  function close() { toggle(false); flag.focus(); }
  async function report() {
    if (disabled) return;
    try {
      await model.send(reason, comment.trim());
      if (open) toggle(false);
      notify("Спасибо! Взрослые посмотрят");
    } catch {
      notify("Не удалось отправить жалобу", "error");
    }
  }
</script>
<svelte:document onkeydown={e => { if (open && e.key === "Escape") { e.preventDefault(); close(); } }} />
<div class="sai-report-line">
  <button type="button" class="sai-report" class:is-sent={status === "sent"} class:is-reviewed={status === "reviewed"}
    aria-label={status ? label : "Пожаловаться на историю"} aria-expanded={open} disabled={!!status}
    bind:this={flag} onclick={togglePanel}>{label}</button>
</div>
{#if open}
<div class="sai-report-panel" role="dialog" aria-label="Что не так с историей?">
  <div class="sai-report-title">Что не так с историей?</div>
  <div class="sai-report-reasons" bind:this={choices}>
    {#each reasons as [value, name] (value)}
      <button type="button" class="sai-report-reason" class:is-selected={reason === value} data-reason={value}
        aria-pressed={reason === value} disabled={pending} onclick={() => reason = value}>{name}</button>
    {/each}
  </div>
  <textarea class="sai-report-comment" maxlength="500" rows="2" aria-label="Комментарий к жалобе" aria-required={reason === "other"}
    placeholder={`Расскажи, что не так (${reason === "other" ? "обязательно" : "необязательно"})`} disabled={pending} bind:value={comment}></textarea>
  <div class="sai-report-actions">
    <button type="button" class="sai-report-send" {disabled} onclick={report}>Отправить</button>
    <button type="button" class="sai-report-cancel" disabled={pending} onclick={close}>Отмена</button>
  </div>
</div>
{/if}
