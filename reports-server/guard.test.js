"use strict";
const test = require("node:test");
const assert = require("node:assert");
const { keyOk, throttle, mode, today } = require("./lib/guard.js");

test("keyOk: any of the comma-separated keys, exactly", () => {
  assert.strictEqual(keyOk("b", "a,b"), true);
  assert.strictEqual(keyOk("a", "a"), true);
  assert.strictEqual(keyOk("", "a"), false);
  assert.strictEqual(keyOk("a ", "a"), false);
  assert.strictEqual(keyOk(undefined, "a"), false);
  assert.strictEqual(keyOk("a", ""), false);
  assert.strictEqual(keyOk("a", undefined), false);
});

test("throttle: limit within the window, then free again after it", () => {
  const store = new Map(), win = 10 * 60 * 1000;
  for (let i = 0; i < 30; i++) assert.strictEqual(throttle(store, "1.2.3.4", 30, win, 1000 + i).ok, true);
  const no = throttle(store, "1.2.3.4", 30, win, 2000);
  assert.strictEqual(no.ok, false);
  assert.ok(no.retry_after > 0 && no.retry_after <= 600);
  assert.strictEqual(throttle(store, "5.6.7.8", 30, win, 2000).ok, true);     // someone else
  assert.strictEqual(throttle(store, "1.2.3.4", 30, win, 1000 + win + 31).ok, true);
});

test("mode: a known value, else the default", () => {
  assert.strictEqual(mode("count", ["on", "count", "off"], "on"), "count");
  assert.strictEqual(mode(" OFF ", ["on", "count", "off"], "on"), "off");
  assert.strictEqual(mode("weird", ["on", "off"], "on"), "on");
  assert.strictEqual(mode(undefined, ["on", "off"], "on"), "on");
});

test("today: the UTC date", () => {
  assert.strictEqual(today(Date.UTC(2026, 10, 27, 23, 59)), "2026-11-27");
  assert.strictEqual(today(Date.UTC(2026, 10, 28, 0, 0)), "2026-11-28");
});
