const INTEGER_FORMATTER = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
const TIME_FORMATTER = new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit" });
const DATE_FORMATTER = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short" });
const DATE_YEAR_FORMATTER = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

export function formatInteger(value: number) {
  return INTEGER_FORMATTER.format(value).replaceAll("\u00a0", " ");
}

function startOfDay(date: Date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

export function formatDay(timestamp: string, now = new Date()) {
  const date = new Date(timestamp);
  const days = Math.round((startOfDay(now) - startOfDay(date)) / 86_400_000);
  if (days === 0) return "сегодня";
  if (days === 1) return "вчера";
  const formatter = date.getFullYear() === now.getFullYear() ? DATE_FORMATTER : DATE_YEAR_FORMATTER;
  return formatter.format(date);
}

export function formatActivity(timestamp: string, now = new Date()) {
  return `${formatDay(timestamp, now)}, ${TIME_FORMATTER.format(new Date(timestamp))}`;
}
