<script lang="ts">
  import { tick } from "svelte";
  import { LENGTH_STEPS, VOICES, presets } from "../model/options";

  let { disabled, ready, voice, chooseVoice, submit, settings }: {
    disabled: boolean; ready: boolean; voice: string; chooseVoice: (id: string) => void;
    submit: (text: string, minutes: number | null) => Promise<boolean>; settings: boolean;
  } = $props();
  let draft = $state("");
  let preset = $state("");
  let step = $state(0);
  let menu = $state<"length" | "voice" | null>(null);
  let length = $derived(LENGTH_STEPS[step] ?? LENGTH_STEPS[0]);
  let label = $derived(VOICES.find(([id]) => id === voice)?.[1] ?? "Айдар");
  let prompt: HTMLTextAreaElement;
  let form: HTMLFormElement;
  let slider: HTMLInputElement;
  let lengthButton: HTMLButtonElement;
  let lengthPanel: HTMLDivElement;
  let voiceButton: HTMLButtonElement;
  let voiceMenu: HTMLDivElement;
  $effect(() => { if (disabled || settings) menu = null; });
  $effect(() => { if (ready && !disabled && !settings) prompt.focus(); });
  let measuredDraft = "";
  $effect(() => {
    if (draft === measuredDraft) return;
    measuredDraft = draft;
    prompt.style.height = "auto";
    prompt.style.height = Math.min(prompt.scrollHeight, 132) + "px";
  });
  async function send(event: SubmitEvent) {
    event.preventDefault();
    if (await submit(draft, length[0])) { draft = ""; preset = ""; }
  }
  async function toggle(value: "length" | "voice") {
    menu = menu === value ? null : value;
    if (menu === null) return;
    await tick();
    if (value === "length") slider.focus();
    else voiceMenu.querySelector<HTMLButtonElement>('[aria-selected="true"]')?.focus();
  }
  function keys(e: KeyboardEvent) {
    if (e.key === "Escape" && menu) {
      e.preventDefault();
      (menu === "length" ? lengthButton : voiceButton).focus();
      menu = null;
      return;
    }
    if (menu !== "voice" || !voiceMenu.contains(e.target as Node)) return;
    const options = Array.from(voiceMenu.querySelectorAll("button"));
    const index = options.indexOf(document.activeElement as HTMLButtonElement);
    if (e.key === "ArrowUp" || e.key === "ArrowDown") {
      e.preventDefault();
      options[(index + (e.key === "ArrowUp" ? -1 : 1) + options.length) % options.length].focus();
    }
  }
  function outside(e: MouseEvent) {
    const node = e.target as Node;
    if (menu === "length" && !lengthPanel.contains(node) && !lengthButton.contains(node)) menu = null;
    if (menu === "voice" && !voiceMenu.contains(node) && !voiceButton.contains(node)) menu = null;
  }
</script>
<svelte:document onclick={outside} onkeydown={keys} />
<div class="sai-compose-wrap">
  <form class="sai-composer" id="saiForm" bind:this={form} onsubmit={send}>
    <textarea id="saiPrompt" rows="1" placeholder="Например: Крош и Ёжик строят ракету и отправляются смотреть звёзды…" aria-label="Идея для истории"
      {disabled} bind:this={prompt} bind:value={draft} onkeydown={e => {
        if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); }
      }}></textarea>
    <button class="sai-voice-picker" id="saiVoiceButton" type="button" aria-haspopup="listbox" aria-expanded={menu === "voice"} aria-controls="saiVoiceMenu"
      aria-label={`Выбрать голос рассказчика, сейчас ${label}`} {disabled} bind:this={voiceButton} onclick={() => toggle("voice")}>
      <span id="saiVoiceValue">{label}</span>
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m7 10 5 5 5-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </button>
    <div class="sai-voice-menu" id="saiVoiceMenu" role="listbox" aria-label="Голос рассказчика" hidden={menu !== "voice"} bind:this={voiceMenu}>
      {#each VOICES as [id, name, hint] (id)}
        <button type="button" class="sai-voice-option" role="option" data-voice={id} aria-selected={voice === id} class:is-selected={voice === id}
          onclick={() => { chooseVoice(id); menu = null; voiceButton.focus(); }}>
          <span class="sai-voice-option-label">{name}</span><span class="sai-voice-option-hint">{hint}</span>
        </button>
      {/each}
    </div>
    <button class="sai-length-button" id="saiLengthButton" type="button" aria-haspopup="dialog" aria-expanded={menu === "length"} aria-controls="saiLengthPanel"
      aria-label={`Длина истории: ${length[1]}`} {disabled} bind:this={lengthButton} onclick={() => toggle("length")}>
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2"/><path d="M12 7v5l3 2" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg><span id="saiLengthValue">{length[1]}</span>
    </button>
    <div class="sai-length-panel" id="saiLengthPanel" role="dialog" aria-label="Длина истории" hidden={menu !== "length"} bind:this={lengthPanel}>
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2"/><path d="M12 7v5l3 2" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <span class="sai-length-title">Длина истории <span id="saiLengthCurrent">({length[1].toLowerCase()})</span></span>
      <div class="sai-length-dots" id="saiLengthDots" data-step={step}>
        <i></i><i></i><i></i><i></i>
        <input type="range" id="saiLength" min="0" max="3" step="1" bind:value={step} bind:this={slider} aria-label="Длина истории" aria-valuetext={length[1]} {disabled}/>
      </div>
    </div>
    <button class="sai-send" type="submit" aria-label="Отправить" {disabled}>
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 12.4 20 5l-5.8 14-2.5-5.1L4 12.4Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="m11.7 13.9 3.5-4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
    </button>
  </form>
  <div class="sai-chips">
    {#each Object.entries(presets) as [name, value] (name)}
      <button class="sai-chip" class:is-selected={preset === name} type="button" aria-pressed={preset === name} {disabled}
        onclick={() => { draft = value; preset = name; prompt.focus(); }}>{name}</button>
    {/each}
  </div>
</div>
