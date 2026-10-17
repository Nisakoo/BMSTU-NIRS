export const PERIODS = Object.freeze(["7", "30", "90"]);

// Dialog and message figures stay demonstrational; user figures and answer
// ratings come from the backend.
const METRIC_KEYS = Object.freeze([
  "dialogs",
  "messages",
]);

function deepFreeze(value) {
  if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
  for (const nested of Object.values(value)) deepFreeze(nested);
  return Object.freeze(value);
}

const DATASETS = deepFreeze({
  "7": {
    period: "7",
    periodLabel: "7 дней",
    metrics: {
      dialogs: 836,
      messages: 4198,
    },
    activity: [
      { label: "Пн", value: 82 },
      { label: "Вт", value: 104 },
      { label: "Ср", value: 96 },
      { label: "Чт", value: 138 },
      { label: "Пт", value: 126 },
      { label: "Сб", value: 158 },
      { label: "Вс", value: 132 },
    ],
  },
  "30": {
    period: "30",
    periodLabel: "30 дней",
    metrics: {
      dialogs: 3542,
      messages: 18240,
    },
    activity: [
      { label: "1–4", value: 284 },
      { label: "5–8", value: 368 },
      { label: "9–12", value: 402 },
      { label: "13–16", value: 388 },
      { label: "17–20", value: 516 },
      { label: "21–24", value: 574 },
      { label: "25–27", value: 492 },
      { label: "28–30", value: 518 },
    ],
  },
  "90": {
    period: "90",
    periodLabel: "90 дней",
    metrics: {
      dialogs: 11784,
      messages: 54832,
    },
    activity: [
      { label: "Нед. 1", value: 682 },
      { label: "Нед. 2", value: 744 },
      { label: "Нед. 3", value: 816 },
      { label: "Нед. 4", value: 798 },
      { label: "Нед. 5", value: 906 },
      { label: "Нед. 6", value: 988 },
      { label: "Нед. 7", value: 1042 },
      { label: "Нед. 8", value: 1136 },
      { label: "Нед. 9", value: 1098 },
      { label: "Нед. 10", value: 1184 },
      { label: "Нед. 11", value: 1126 },
      { label: "Нед. 12", value: 1264 },
    ],
  },
});

function isMetric(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

export function validateDashboardData(data) {
  if (!data || typeof data !== "object") return false;
  if (!PERIODS.includes(data.period) || typeof data.periodLabel !== "string") return false;
  if (!data.metrics || !METRIC_KEYS.every(key => isMetric(data.metrics[key]))) return false;
  if (!Array.isArray(data.activity) || data.activity.length === 0) return false;
  if (!data.activity.every(point => (
    typeof point?.label === "string"
    && Number.isInteger(point.value)
    && point.value >= 0
  ))) return false;
  const activityTotal = data.activity.reduce((total, point) => total + point.value, 0);
  return activityTotal === data.metrics.dialogs;
}

export function getDashboardData(period) {
  const data = DATASETS[period];
  return validateDashboardData(data) ? data : null;
}
