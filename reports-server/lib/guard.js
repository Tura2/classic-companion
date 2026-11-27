// What both endpoints check before doing anything: the upload key, how often a caller comes, the
// mode switches, and today's date (UTC) for the day counters.
"use strict";
const crypto = require("crypto");

// the key Companion sent against UPLOAD_KEY, which may hold several keys, comma-separated, so a new
// key can ship in a release while the old one still works
function keyOk(given, keys) {
  const x = Buffer.from(String(given || ""));
  if (!x.length) return false;
  let ok = false;
  for (const k of String(keys || "").split(",").map(s => s.trim()).filter(Boolean)) {
    const y = Buffer.from(k);
    if (y.length === x.length && crypto.timingSafeEqual(x, y)) ok = true;
  }
  return ok;
}

// a sliding window per caller: at most `limit` in `windowMs`. It lives only while the function's
// instance is warm, so it's a speed bump, not the guard (the day caps are)
function throttle(store, who, limit, windowMs, now) {
  if (store.size > 5000) store.clear();
  const times = (store.get(who) || []).filter(t => t > now - windowMs);
  if (times.length >= limit) {
    store.set(who, times);
    return { ok: false, retry_after: Math.max(1, Math.ceil((times[0] + windowMs - now) / 1000)) };
  }
  times.push(now);
  store.set(who, times);
  return { ok: true, retry_after: 0 };
}

function mode(value, allowed, dflt) {
  const v = String(value || "").trim().toLowerCase();
  return allowed.includes(v) ? v : dflt;
}

function today(now = Date.now()) {
  return new Date(now).toISOString().slice(0, 10);
}

const num = (v, dflt) => {
  const n = parseInt(v, 10);
  return Number.isFinite(n) && n >= 0 ? n : dflt;
};

module.exports = { keyOk, throttle, mode, today, num };
