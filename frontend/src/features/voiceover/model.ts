import type { AgentApi } from "../../entities/dialog";
import { createStore } from "../../shared/lib/store";

interface VoiceState {
  generated: Record<string, Blob>;
  generating: boolean;
  downloading: boolean;
  notice: string;
}

type Action =
  | { type: "generate" | "download" | "downloaded" }
  | { type: "ready"; voice: string; blob: Blob }
  | { type: "generationFailed" | "downloadFailed"; notice: string };

function reduce(state: VoiceState, action: Action): VoiceState {
  switch (action.type) {
    case "generate": return { ...state, generating: true, notice: "Готовим озвучку…" };
    case "ready": return { ...state, generating: false, generated: { ...state.generated, [action.voice]: action.blob }, notice: "" };
    case "generationFailed": return { ...state, generating: false, notice: action.notice };
    case "download": return { ...state, downloading: true, notice: "Скачиваем…" };
    case "downloaded": return { ...state, downloading: false, notice: state.generating ? "Готовим озвучку…" : "" };
    case "downloadFailed": return { ...state, downloading: false, notice: action.notice };
  }
}

export interface VoiceRequests {
  startAudio: (id: number, voice: string) => ReturnType<AgentApi["startAudio"]>;
  getAudio: (id: number, voice: string) => ReturnType<AgentApi["getAudio"]>;
  downloadAudio: (id: number, voice: string) => ReturnType<AgentApi["downloadAudio"]>;
}

function errorMessage(error: unknown, fallback: string) {
  return error !== null && typeof error === "object" && "code" in error && error.code === "audio_unavailable"
    ? "Озвучка недоступна" : fallback;
}

export function createVoiceover(id: number, api: VoiceRequests) {
  const store = createStore<VoiceState, Action>({ generated: {}, generating: false, downloading: false, notice: "" }, reduce);
  let disposed = false;
  let timer: number | undefined;

  function poll(voice: string) {
    timer = window.setTimeout(() => void load(voice), 1000);
  }

  async function load(voice: string) {
    try {
      const result = await api.getAudio(id, voice);
      if (disposed) return;
      if (result.status === "pending") poll(voice);
      else store.dispatch({ type: "ready", voice, blob: result.blob });
    } catch (error) {
      if (!disposed) store.dispatch({ type: "generationFailed", notice: errorMessage(error, "Не удалось озвучить") });
    }
  }

  async function generate(voice: string) {
    if (disposed || store.getState().generating) return;
    store.dispatch({ type: "generate" });
    try {
      const status = await api.startAudio(id, voice);
      if (disposed) return;
      if (status === "ready") await load(voice);
      else poll(voice);
    } catch (error) {
      if (!disposed) store.dispatch({ type: "generationFailed", notice: errorMessage(error, "Не удалось озвучить") });
    }
  }

  async function download(voice: string, save: (blob: Blob) => boolean) {
    const state = store.getState();
    if (disposed || state.downloading) return;
    store.dispatch({ type: "download" });
    try {
      const blob = state.generated[voice] ?? await api.downloadAudio(id, voice);
      if (disposed) return;
      store.dispatch(save(blob) ? { type: "downloaded" } : { type: "downloadFailed", notice: "Скачивание недоступно" });
    } catch (error) {
      if (!disposed) store.dispatch({ type: "downloadFailed", notice: errorMessage(error, "Не удалось скачать") });
    }
  }

  return {
    subscribe: store.subscribe, generate, download,
    dispose() {
      disposed = true;
      window.clearTimeout(timer);
    },
  };
}
