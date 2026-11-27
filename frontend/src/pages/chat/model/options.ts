export const VOICES = [
  ["aidar", "Айдар", "Мужской, спокойный"],
  ["baya", "Бая", "Женский, мягкий"],
  ["kseniya", "Ксения", "Женский, ясный"],
  ["xenia", "Ксения (второй тембр)", "Женский, светлый"],
  ["eugene", "Евгений", "Мужской, размеренный"],
] as const;
// Slider steps of the story length: minutes sent to the agent and the label.
export const LENGTH_STEPS = [
  [2, "2 мин"],
  [5, "5 мин"],
  [10, "10 мин"],
  [null, "Любая"],
] as const;

export const presets: Record<string, string> = {
  "Про дружбу": "Придумай историю про Кроша и Ёжика, которые поссорились из-за игры, но общее дело помогло им снова стать друзьями.",
  "Приключение": "Крош, Ёжик и Нюша находят старую карту и отправляются искать таинственное место. Придумай, что ждёт их в пути.",
  "Перед сном": "Расскажи короткую, спокойную и уютную историю перед сном про Бараша, который искал потерянную рифму.",
  "В космосе": "Крош и Ёжик построили ракету вместе с Пином и отправились к далёкой звезде. Придумай их космическое приключение.",
  "Про чувства": "Нюша расстроилась из-за неудачи, а друзья помогли ей понять свои чувства и снова поверить в себя. Расскажи эту историю.",
  "Поучительная": "Придумай весёлую историю, в которой Крош совершает ошибку, исправляет её и понимает, почему важно говорить правду.",
};

const voiceStorageKey = "smeshariki.voice";

export function readVoice(): string {
  try {
    const voice = localStorage.getItem(voiceStorageKey);
    return VOICES.find(([id]) => id === voice)?.[0] ?? "aidar";
  } catch {
    return "aidar";
  }
}

export function saveVoice(voice: string) {
  try {
    localStorage.setItem(voiceStorageKey, voice);
  } catch {
    // The in-memory choice still works when storage is unavailable.
  }
}
