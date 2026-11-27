<script lang="ts">
  import { onDestroy, untrack } from "svelte";
  import { audioUrl } from "../../entities/dialog";
  import { createVoiceover, type VoiceRequests } from "./model";

  let { dialogId, id, voice, available, startAudio, getAudio, downloadAudio }:
    { dialogId: string; id: number; voice: string; available: string[] } & VoiceRequests = $props();
  const model = untrack(() => createVoiceover(id, { startAudio, getAudio, downloadAudio }));
  onDestroy(model.dispose);
  let blob = $derived($model.generated[voice]);
  let has = $derived(available.includes(voice) || !!blob);
  let audio: HTMLAudioElement;
  let time = $state(0);
  let duration = $state(0);
  let playing = $state(false);

  $effect(() => {
    const url = blob && URL.createObjectURL?.(blob);
    if (has) audio.src = url || audioUrl(dialogId, id, voice);
    return () => {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
      playing = false;
      time = duration = 0;
      if (url) URL.revokeObjectURL(url);
    };
  });

  function generate() {
    return model.generate(voice);
  }

  function download() {
    const selected = voice;
    return model.download(selected, data => {
      const url = URL.createObjectURL?.(data);
      if (!url) return false;
      const link = document.createElement("a");
      link.href = url;
      link.download = `smeshariki-${id}-${selected}.mp3`;
      document.body.append(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
      return true;
    });
  }

  function format(seconds: number) {
    const whole = Number.isFinite(seconds) && seconds > 0 ? Math.floor(seconds) : 0;
    return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
  }
</script>
<div class="sai-voice-line">
  <button class="sai-voice-button" type="button" disabled={has ? $model.downloading : $model.generating} onclick={has ? download : generate}>{has ? "Скачать" : $model.generating ? "Готовим озвучку…" : "Озвучить"}</button>
  <button class="sai-voice-refresh" type="button" aria-label="Озвучить заново" hidden={!has} disabled={$model.generating} onclick={generate}>↻</button>
  <span class="sai-voice-state" aria-live="polite">{$model.notice}</span>
  <div class="sai-player" hidden={!has}>
    <audio bind:this={audio} preload="none" hidden onplay={() => playing = true} onpause={() => playing = false}
      onloadedmetadata={() => duration = audio.duration} ontimeupdate={() => time = audio.currentTime}
      onended={() => { playing = false; audio.currentTime = time = 0; }}></audio>
    <button type="button" class="sai-player-toggle" aria-label={playing ? "Поставить на паузу" : "Слушать озвучку"}
      onclick={() => audio.paused ? audio.play().catch(() => {}) : audio.pause()}>{playing ? "❚❚" : "▶"}</button>
    <span class="sai-player-time">{format(time)}</span>
    <input type="range" class="sai-player-progress" min="0" max="100" aria-label="Позиция озвучки"
      value={duration > 0 ? 100 * time / duration : 0} oninput={e => { if (duration > 0) audio.currentTime = e.currentTarget.valueAsNumber * duration / 100; }} />
    <span class="sai-player-time">{format(duration)}</span>
  </div>
</div>
