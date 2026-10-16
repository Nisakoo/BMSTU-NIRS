import assert from "node:assert/strict";
import test from "node:test";

import { getDashboardData } from "../src/admin/demo-data.js";
import { mountAdminNavigation, mountDashboard } from "../src/admin/admin.js";

class FakeElement {
  constructor(tagName = "div") {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.listeners = new Map();
    this.attributes = new Map();
    this.dataset = {};
    this.hidden = false;
    this._textContent = "";
    this.className = "";
    this.style = {};
  }

  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) ?? [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  click() {
    for (const listener of this.listeners.get("click") ?? []) listener();
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = children;
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    return this.attributes.get(name) ?? null;
  }

  removeAttribute(name) {
    this.attributes.delete(name);
  }

  set textContent(value) {
    this._textContent = String(value);
    this.children = [];
  }

  get textContent() {
    return this._textContent + this.children.map(child => child.textContent).join("");
  }

  set innerHTML(_value) {
    throw new Error("dynamic innerHTML is forbidden");
  }
}

class FakeWindow {
  constructor(hash = "") {
    this.location = { hash };
    this.listeners = new Map();
  }

  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) ?? [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  dispatch(type) {
    for (const listener of this.listeners.get(type) ?? []) listener();
  }
}

function createNavigationHarness(hash = "") {
  const links = [
    ["#overview", "Обзор"],
    ["#activity", "Активность"],
    ["#users", "Пользователи"],
  ].map(([href, label]) => {
    const link = new FakeElement("a");
    link.setAttribute("href", href);
    link.textContent = label;
    return link;
  });
  const documentRef = {
    querySelectorAll: selector => selector === "[data-admin-nav]" ? links : [],
  };
  return { documentRef, links, windowRef: new FakeWindow(hash) };
}

function activeNavigationLabels(links) {
  return links
    .filter(link => link.getAttribute("aria-current") === "location")
    .map(link => link.textContent);
}

function createHarness() {
  const ids = [
    "#adminContent",
    "#adminError",
    "#adminPeriodLabel",
    "#adminComparison",
    "#adminMetrics",
    "#adminActivity",
    "#adminChartDescription",
    "#adminQuality",
    "#adminUsers",
  ];
  const elements = Object.fromEntries(ids.map(id => [id, new FakeElement()]));
  const buttons = ["7", "30", "90"].map(period => {
    const button = new FakeElement("button");
    button.dataset.period = period;
    button.setAttribute("aria-pressed", "false");
    return button;
  });
  const documentRef = {
    querySelector: selector => elements[selector] ?? null,
    querySelectorAll: selector => selector === "[data-period]" ? buttons : [],
    createElement: tagName => new FakeElement(tagName),
  };
  return { documentRef, elements, buttons };
}

test("dashboard renders the 30 day dataset by default", () => {
  const ui = createHarness();
  mountDashboard(ui.documentRef);

  assert.equal(ui.elements["#adminContent"].hidden, false);
  assert.equal(ui.elements["#adminError"].hidden, true);
  assert.equal(ui.elements["#adminPeriodLabel"].textContent, "30 дней");
  assert.match(ui.elements["#adminComparison"].textContent, /18%/);
  assert.equal(ui.elements["#adminMetrics"].children.length, 4);
  assert.equal(ui.elements["#adminActivity"].children.length, 8);
  assert.equal(ui.elements["#adminUsers"].children.length, 5);
  assert.match(ui.elements["#adminMetrics"].children[0].textContent, /1 548/);
  assert.match(ui.elements["#adminChartDescription"].textContent, /1–4: 284/);
  assert.match(ui.elements["#adminQuality"].textContent, /97,2%/);
  assert.equal(ui.buttons[1].getAttribute("aria-pressed"), "true");
});

test("period buttons update metrics, chart, users, and accessible state together", () => {
  const ui = createHarness();
  mountDashboard(ui.documentRef);
  ui.buttons[2].click();

  assert.equal(ui.elements["#adminPeriodLabel"].textContent, "90 дней");
  assert.match(ui.elements["#adminMetrics"].children[0].textContent, /2 384/);
  assert.equal(ui.elements["#adminActivity"].children.length, 12);
  assert.match(ui.elements["#adminUsers"].children[0].textContent, /Кирилл Б\./);
  assert.equal(ui.buttons[1].getAttribute("aria-pressed"), "false");
  assert.equal(ui.buttons[2].getAttribute("aria-pressed"), "true");
});

test("missing data replaces figures with a safe error state", () => {
  const ui = createHarness();
  mountDashboard(ui.documentRef, { getData: () => null });

  assert.equal(ui.elements["#adminContent"].hidden, true);
  assert.equal(ui.elements["#adminError"].hidden, false);
  assert.match(ui.elements["#adminError"].textContent, /не удалось загрузить/i);
  assert.equal(ui.elements["#adminMetrics"].children.length, 0);
});

test("rendered text matches the selected deterministic dataset", () => {
  const ui = createHarness();
  mountDashboard(ui.documentRef, { initialPeriod: "7", getData: getDashboardData });
  const expected = getDashboardData("7");

  assert.equal(ui.elements["#adminPeriodLabel"].textContent, expected.periodLabel);
  assert.match(ui.elements["#adminMetrics"].children[2].textContent, /836/);
  assert.match(ui.elements["#adminUsers"].children[1].textContent, /Марк Т\./);
  assert.equal(ui.buttons[0].getAttribute("aria-pressed"), "true");
});

test("navigation activates overview by default and moves state to the clicked section", () => {
  const ui = createNavigationHarness();

  assert.equal(mountAdminNavigation(ui.documentRef, ui.windowRef), true);
  assert.deepEqual(activeNavigationLabels(ui.links), ["Обзор"]);

  ui.links[1].click();

  assert.deepEqual(activeNavigationLabels(ui.links), ["Активность"]);
  assert.equal(ui.links[0].getAttribute("aria-current"), null);
});

test("navigation follows direct and browser-driven hash changes with a safe fallback", () => {
  const ui = createNavigationHarness("#users");
  mountAdminNavigation(ui.documentRef, ui.windowRef);

  assert.deepEqual(activeNavigationLabels(ui.links), ["Пользователи"]);

  ui.windowRef.location.hash = "#activity";
  ui.windowRef.dispatch("hashchange");
  assert.deepEqual(activeNavigationLabels(ui.links), ["Активность"]);

  ui.windowRef.location.hash = "#missing";
  ui.windowRef.dispatch("hashchange");
  assert.deepEqual(activeNavigationLabels(ui.links), ["Обзор"]);
});
