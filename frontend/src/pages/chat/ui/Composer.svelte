<script lang="ts">
  import { tick } from "svelte";
  import { LENGTH_STEPS, VOICES, presets } from "../model/options";

  let { disabled, waiting, voice, chooseVoice, submit, settings }: {
    disabled: boolean; waiting: boolean; voice: string; chooseVoice: (id: string) => void;
    submit: (text: string, minutes: number | null) => Promise<boolean>; settings: boolean;
  } = $props();
  let draft = $state("");
  let preset = $state("");
  let step = $state(LENGTH_STEPS.length - 1);
  let menu = $state<"length" | "voice" | null>(null);
  let length = $derived(LENGTH_STEPS[step]);
  let label = $derived(VOICES.find(([id]) => id === voice)?.[1] ?? "Айдар");
  let expanded = $state(false);
  let measure: HTMLSpanElement;
  let prompt: HTMLTextAreaElement;
  let form: HTMLFormElement;
  let slider: HTMLInputElement;
  let lengthButton: HTMLButtonElement;
  let lengthPanel: HTMLDivElement;
  let voiceButton: HTMLButtonElement;
  let voiceMenu: HTMLDivElement;
  $effect(() => { if (disabled || settings) menu = null; });
  let revision = 0;
  function edit(value: string, topic = "") {
    revision++;
    draft = value;
    preset = topic;
  }
  async function fit(value: string) {
    // The measuring span always occupies the compact column, even when the editor is wide.
    expanded = value.includes("\n") || measure.scrollWidth > measure.clientWidth;
    await tick();
    if (!prompt) return;
    if (!expanded) {
      prompt.style.removeProperty("height");
      return;
    }
    const scrollTop = prompt.scrollTop;
    prompt.style.height = "auto";
    prompt.style.height = prompt.scrollHeight + "px";
    prompt.scrollTop = scrollTop;
  }
  $effect(() => { void fit(draft); });
  async function send(event: SubmitEvent) {
    event.preventDefault();
    if (disabled || waiting || !draft.trim()) return;
    menu = null;
    const sentDraft = draft;
    const sentPreset = preset;
    edit("");
    const clearedRevision = revision;
    prompt.focus({ preventScroll: true });
    const accepted = await submit(sentDraft, length[0]);
    if (!accepted && revision === clearedRevision) edit(sentDraft, sentPreset);
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
<svelte:window onresize={() => void fit(draft)} />
<div class="sai-compose-wrap">
  <form class="sai-composer" class:is-expanded={expanded} id="saiForm" bind:this={form} onsubmit={send}>
    <span class="sai-composer-measure" aria-hidden="true" bind:this={measure}>{draft.includes("\n") ? "" : draft}</span>
    <textarea id="saiPrompt" rows="1" placeholder="Идея для сказки" aria-label="Идея для истории"
      {disabled} bind:this={prompt} bind:value={() => draft, edit} onkeydown={e => {
        if (e.key !== "Enter" || e.shiftKey || e.isComposing || e.keyCode === 229) return;
        e.preventDefault();
        if (!waiting && !disabled) form.requestSubmit();
      }}></textarea>
    <div class="sai-voice-control">
      <button class="sai-voice-picker" id="saiVoiceButton" type="button" aria-haspopup="listbox" aria-expanded={menu === "voice"} aria-controls="saiVoiceMenu"
        aria-label={`Выбрать голос рассказчика, сейчас ${label}`} {disabled} bind:this={voiceButton} onclick={() => toggle("voice")}>
        <svg class="sai-voice-symbol" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="9" y="3" width="6" height="12" rx="3" stroke="currentColor" stroke-width="2"/><path d="M5 11a7 7 0 0 0 14 0m-7 7v3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
        <span id="saiVoiceValue">{label}</span>
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m7 10 5 5 5-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
      <div class="sai-voice-menu" id="saiVoiceMenu" role="listbox" aria-label="Голос рассказчика" hidden={menu !== "voice"} bind:this={voiceMenu}>
        {#each VOICES as [id, name] (id)}
          <button type="button" class="sai-voice-option" role="option" data-voice={id} aria-selected={voice === id}
            onclick={() => { chooseVoice(id); menu = null; voiceButton.focus(); }}>
            {name}
            <svg viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="m3 8 3 3 7-7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
        {/each}
      </div>
    </div>
    <button class="sai-length-button" id="saiLengthButton" type="button" aria-haspopup="dialog" aria-expanded={menu === "length"} aria-controls="saiLengthPanel"
      aria-label={`Длина истории: ${length[1]}`} {disabled} bind:this={lengthButton} onclick={() => toggle("length")}>
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2"/><path d="M12 7v5l3 2" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg><span id="saiLengthValue">{length[1]}</span>
    </button>
    <div class="sai-length-panel" id="saiLengthPanel" role="dialog" aria-label="Длина истории" hidden={menu !== "length"} bind:this={lengthPanel}>
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2"/><path d="M12 7v5l3 2" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <span class="sai-length-title">Длина истории <span id="saiLengthCurrent">({length[1].toLowerCase()})</span></span>
      <div class="sai-length-dots" id="saiLengthDots" data-step={step} style:--progress={`${100 * step / (LENGTH_STEPS.length - 1)}%`}>
        <i></i><i></i><i></i><i></i>
        <input type="range" id="saiLength" min="0" max="3" step="1" bind:value={step} bind:this={slider} aria-label="Длина истории" aria-valuetext={length[1]} {disabled}/>
      </div>
    </div>
    <button class="sai-send" type="submit" aria-label="Отправить" disabled={disabled || waiting}>
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 12.4 20 5l-5.8 14-2.5-5.1L4 12.4Z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="m11.7 13.9 3.5-4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
    </button>
  </form>
  <div class="sai-chips">
    {#each Object.entries(presets) as [name, value] (name)}
      <button class="sai-chip" class:is-selected={preset === name} type="button" aria-pressed={preset === name} {disabled}
        onclick={() => { edit(value, name); prompt.focus(); }}>{name}</button>
    {/each}
  </div>
</div>
