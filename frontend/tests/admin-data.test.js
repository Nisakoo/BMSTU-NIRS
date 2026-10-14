import assert from "node:assert/strict";
import test from "node:test";

import {
  PERIODS,
  getDashboardData,
  validateDashboardData,
} from "../src/admin/demo-data.js";

const METRIC_KEYS = [
  "usersTotal",
  "activeUsers",
  "dialogs",
  "messages",
  "successRate",
  "averageResponseSeconds",
];

test("dashboard provides deterministic valid data for every supported period", () => {
  assert.deepEqual(PERIODS, ["7", "30", "90"]);

  for (const period of PERIODS) {
    const first = getDashboardData(period);
    const second = getDashboardData(period);

    assert.equal(first, second);
    assert.equal(validateDashboardData(first), true, period);
    assert.equal(first.period, period);
    assert.ok(first.periodLabel.length > 0);
    assert.ok(Object.isFrozen(first));
    assert.ok(Object.isFrozen(first.metrics));

    for (const key of METRIC_KEYS) {
      assert.equal(typeof first.metrics[key], "number", `${period}:${key}`);
      assert.ok(first.metrics[key] >= 0, `${period}:${key}`);
    }

    assert.ok(first.activity.length >= 7);
    for (const point of first.activity) {
      assert.equal(typeof point.label, "string");
      assert.ok(Number.isInteger(point.value));
      assert.ok(point.value >= 0);
    }
    assert.equal(
      first.activity.reduce((total, point) => total + point.value, 0),
      first.metrics.dialogs,
      `${period}: activity total must match dialogs`,
    );

    assert.ok(first.recentUsers.length >= 4);
    for (const user of first.recentUsers) {
      assert.match(user.id, /^demo-/);
      assert.equal(typeof user.name, "string");
      assert.equal(typeof user.lastActive, "string");
      assert.ok(Number.isInteger(user.dialogs));
      assert.ok(["active", "new", "inactive"].includes(user.status));
    }
  }
});

test("unknown periods and malformed data are rejected safely", () => {
  assert.equal(getDashboardData("365"), null);
  assert.equal(getDashboardData(), null);
  assert.equal(validateDashboardData(null), false);
  assert.equal(validateDashboardData({ period: "7" }), false);
  assert.equal(validateDashboardData({
    period: "7",
    periodLabel: "7 дней",
    metrics: {},
    activity: [],
    recentUsers: [],
  }), false);

  const valid = getDashboardData("7");
  assert.equal(validateDashboardData({
    ...valid,
    metrics: { ...valid.metrics, dialogs: valid.metrics.dialogs + 1 },
  }), false);
});
