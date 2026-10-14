export const PERIODS = Object.freeze(["7", "30", "90"]);

const METRIC_KEYS = Object.freeze([
  "usersTotal",
  "activeUsers",
  "dialogs",
  "messages",
  "successRate",
  "averageResponseSeconds",
]);

function deepFreeze(value) {
  if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
  for (const nested of Object.values(value)) deepFreeze(nested);
  return Object.freeze(value);
}

function user(id, name, lastActive, dialogs, status) {
  return { id, name, lastActive, dialogs, status };
}

const DATASETS = deepFreeze({
  "7": {
    period: "7",
    periodLabel: "7 дней",
    comparison: "+12% к прошлой неделе",
    metrics: {
      usersTotal: 1284,
      activeUsers: 462,
      dialogs: 836,
      messages: 4198,
      successRate: 96.8,
      averageResponseSeconds: 2.4,
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
    recentUsers: [
      user("demo-u-1048", "Алёна С.", "сегодня, 12:48", 14, "active"),
      user("demo-u-1047", "Марк Т.", "сегодня, 11:32", 3, "new"),
      user("demo-u-1046", "Лиза К.", "сегодня, 10:06", 8, "active"),
      user("demo-u-1045", "Илья Н.", "вчера, 21:17", 6, "inactive"),
      user("demo-u-1044", "Соня Р.", "вчера, 18:42", 11, "active"),
    ],
  },
  "30": {
    period: "30",
    periodLabel: "30 дней",
    comparison: "+18% к прошлому периоду",
    metrics: {
      usersTotal: 1548,
      activeUsers: 972,
      dialogs: 3542,
      messages: 18240,
      successRate: 97.2,
      averageResponseSeconds: 2.2,
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
    recentUsers: [
      user("demo-u-1284", "Маша В.", "2 минуты назад", 17, "active"),
      user("demo-u-1283", "Антон П.", "18 минут назад", 1, "new"),
      user("demo-u-1282", "Варя Л.", "сегодня, 12:02", 9, "active"),
      user("demo-u-1281", "Денис М.", "сегодня, 09:45", 5, "inactive"),
      user("demo-u-1280", "Полина А.", "вчера, 22:19", 12, "active"),
    ],
  },
  "90": {
    period: "90",
    periodLabel: "90 дней",
    comparison: "+31% к прошлому кварталу",
    metrics: {
      usersTotal: 2384,
      activeUsers: 1690,
      dialogs: 11784,
      messages: 54832,
      successRate: 96.9,
      averageResponseSeconds: 2.5,
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
    recentUsers: [
      user("demo-u-1548", "Кирилл Б.", "сегодня, 13:04", 21, "active"),
      user("demo-u-1547", "Алиса Д.", "сегодня, 12:51", 2, "new"),
      user("demo-u-1546", "Тимур Ж.", "сегодня, 11:46", 13, "active"),
      user("demo-u-1545", "Вика О.", "сегодня, 10:28", 7, "inactive"),
      user("demo-u-1544", "Роман Е.", "вчера, 23:11", 18, "active"),
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
  if (data.metrics.successRate > 100 || data.metrics.activeUsers > data.metrics.usersTotal) return false;
  if (!Array.isArray(data.activity) || data.activity.length === 0) return false;
  if (!data.activity.every(point => (
    typeof point?.label === "string"
    && Number.isInteger(point.value)
    && point.value >= 0
  ))) return false;
  const activityTotal = data.activity.reduce((total, point) => total + point.value, 0);
  if (activityTotal !== data.metrics.dialogs) return false;
  if (!Array.isArray(data.recentUsers) || data.recentUsers.length === 0) return false;
  return data.recentUsers.every(entry => (
    typeof entry?.id === "string"
    && entry.id.startsWith("demo-")
    && typeof entry.name === "string"
    && typeof entry.lastActive === "string"
    && Number.isInteger(entry.dialogs)
    && entry.dialogs >= 0
    && ["active", "new", "inactive"].includes(entry.status)
  ));
}

export function getDashboardData(period) {
  const data = DATASETS[period];
  return validateDashboardData(data) ? data : null;
}
