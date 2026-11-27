import type { AgentApi } from "../../entities/dialog";

export interface ChatMessage {
  role: "assistant" | "user";
  content: string;
  complete: boolean;
  error?: boolean;
  id?: number;
  feedback?: number | null;
  report?: "reviewed" | "sent" | null;
  audioVoices?: string[];
}

export interface MessageActions {
  rate(id: number, score: number | null): Promise<void>;
  report(id: number, reason: string, comment: string): Promise<void>;
  startAudio(id: number, voice: string): ReturnType<AgentApi["startAudio"]>;
  getAudio(id: number, voice: string): ReturnType<AgentApi["getAudio"]>;
  downloadAudio(id: number, voice: string): ReturnType<AgentApi["downloadAudio"]>;
  notify(text: string, kind?: "info" | "error"): void;
}
