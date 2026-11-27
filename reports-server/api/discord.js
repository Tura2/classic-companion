// Companion's Discord posts, through this server: the webhook never ships in the exe.
//
// A player proves who they are once (Connect Discord): the app hands the token Discord gave it to
// `link`, which asks Discord whose it is, drops it, and returns a card signed with CARD_SECRET. Each
// post carries that card, and the server builds the message itself from plain fields, so a post
// can tag only its sender and carries no text, link or mention of the sender's choosing.
//
//   GET                       {"client_id", "on"}: for the Connect page
//   POST {link: {token}}      {"id", "name", "card"}
//   POST {card, kind, data}   {"ok": true}; kind: sale | notice | grind | drop
//
// Environment (Vercel → Project → Settings → Environment Variables; never in the code):
//   UPLOAD_KEY         the same key as the reports (comma-separated keys all work)
//   DISCORD_WEBHOOK    the channel's webhook URL
//   DISCORD_CLIENT_ID  the Discord app's client ID (public: the Connect page shows it anyway)
//   CARD_SECRET        signs the cards; a new one means everyone presses Connect again
//   BLOCKED_IDS        optional, Discord IDs that can't post, comma-separated
//   DISCORD_MODE       on (default) | off (503: the app keeps its posts and tries later)
// One Discord ID posts at most 20 times in 10 minutes while the function's instance is warm.
"use strict";
const crypto = require("crypto");
const { keyOk, throttle, mode } = require("../lib/guard.js");

const API = "https://discord.com/api";
const IMG = "https://raw.githubusercontent.com/ohmi69/osms_datamine_dashboard/main/data/current/images/items/";
const ID_LIMIT = 20, ID_WINDOW = 10 * 60 * 1000;
const IDS = new Map();
const NOTICES = {
  connected: "connected Companion: what you share will show up here.",
  test: "this is a test from Companion.",
  soldout: "your shop sold out: time to restock.",
  closed: "your shop closed: the game left the Free Market (disconnected, or back at the login screen).",
};

// ---- the card: "v1.<id>.<issued>.<signature>"
const sign = (body, secret) => crypto.createHmac("sha256", secret).update(body).digest("base64url");

function makeCard(id, issued, secret) {
  const body = `v1.${id}.${issued}`;
  return `${body}.${sign(body, secret)}`;
}

function readCard(card, secret) {
  const p = String(card || "").split(".");
  if (p.length !== 4 || p[0] !== "v1" || !/^\d{1,25}$/.test(p[1]) || !/^\d{1,12}$/.test(p[2])) return null;
  const want = Buffer.from(sign(`v1.${p[1]}.${p[2]}`, secret)), got = Buffer.from(p[3]);
  return want.length === got.length && crypto.timingSafeEqual(want, got) ? p[1] : null;
}

// ---- plain fields only
const name = v => {
  const s = String(v == null ? "" : v).replace(/[^A-Za-z0-9 '().:-]/g, "").replace(/\s+/g, " ").trim().slice(0, 40);
  return s || null;
};
const username = v => String(v || "").replace(/[^A-Za-z0-9 ]/g, "").trim().slice(0, 12).trim() || "Companion";
const num = v => (typeof v === "number" && Number.isFinite(v) && v >= 0 ? v : null);
const fmt = n => Math.round(n).toLocaleString("en-US");
const img = id => (/^\d{1,8}$/.test(String(id == null ? "" : id)) ? `${IMG}${String(id).padStart(8, "0")}.png` : null);
const count = v => (num(v) && v >= 1 ? Math.floor(v) : 1);

function base(id, data, content, embeds) {
  const m = { content: `<@${id}> ${content}`, username: username(data.character), allowed_mentions: { parse: [], users: [id] } };
  if (embeds && embeds.length) m.embeds = embeds;
  return m;
}

function sale(data, id) {
  const sales = Array.isArray(data.sales) ? data.sales.slice(0, 10) : [];
  if (!sales.length) return null;
  const items = [];
  for (const s of sales) {
    const price = num(s && s.price);
    if (!price) return null;
    items.push({ item: name(s.item), count: count(s.count), price, median: num(s.median), img: img(s.item_id) });
  }
  const what = s => (s.item ? `${s.item} ×${s.count}` : "something");
  const content = items.length === 1
    ? (items[0].item ? `sold ${what(items[0])} for ${fmt(items[0].price)} mesos` : `sold something for +${fmt(items[0].price)} mesos`)
    : `sold ${items.length} things for ${fmt(items.reduce((a, s) => a + s.price, 0))} mesos`;
  const total = num(data.total_today);
  const embeds = items.map(s => {
    let desc = `${fmt(s.price)} mesos`;
    if (s.item && s.median) {
      const pct = Math.round((s.price / s.count - s.median) / s.median * 100);
      desc += pct ? ` · ${Math.abs(pct)}% ${pct >= 0 ? "above" : "below"} the market median` : " · at the market median";
    }
    const e = { title: s.item ? what(s) : "Sold something", description: desc };
    if (s.item && s.img) e.thumbnail = { url: s.img };
    if (total) e.footer = { text: `Shop total today: ${fmt(total)}` };
    return e;
  });
  return base(id, data, content, embeds);
}

function notice(data, id) {
  if (data.what === "correction") {
    const items = (Array.isArray(data.items) ? data.items.slice(0, 10) : [])
      .map(s => (name(s && s.item) ? `${name(s.item)} x${count(s.count)}` : "something"));
    if (!items.length) return null;
    return base(id, data, `correction: ${items.join(", ")} didn't sell after all, that post was wrong (your shop's Total Sales doesn't show it).`);
  }
  return Object.prototype.hasOwnProperty.call(NOTICES, data.what) ? base(id, data, NOTICES[data.what]) : null;
}

function grind(data, id) {
  const map = name(data.map), minutes = num(data.minutes), gained = num(data.exp_gained), a = num(data.level_start);
  if (!map || minutes == null || gained == null) return null;
  const h = Math.floor(minutes / 60), m = Math.round(minutes % 60);
  const time = h ? `${h}h ${m}m` : `${m}m`;
  const b = num(data.level_end);
  const fields = [{ name: "Time", value: time, inline: true }];
  if (num(data.exp_hr)) fields.push({ name: "EXP/hr", value: fmt(data.exp_hr), inline: true });
  fields.push({ name: "EXP gained", value: fmt(gained), inline: true });
  if (a != null) fields.push({ name: "Level", value: b != null && b !== a ? `${a} → ${b}` : `${a}`, inline: true });
  if (num(data.kills_total)) fields.push({ name: "Kills", value: fmt(data.kills_total), inline: true });
  fields.push({ name: "With", value: data.party === true ? "Party" : "Solo", inline: true });
  const loot = (Array.isArray(data.loot_top) ? data.loot_top.slice(0, 3) : [])
    .filter(x => x && name(x.name)).map(x => `${name(x.name)} ×${count(x.count)}`);
  if (loot.length) fields.push({ name: "Top pickups", value: loot.join("\n"), inline: false });
  if (num(data.mesos)) fields.push({ name: "Mesos", value: fmt(data.mesos), inline: true });
  const job = name(data.job);
  const e = { title: map, fields };
  if (job) e.footer = { text: job };
  return base(id, data, `grinded ${map} for ${time}`, [e]);
}

function drop(data, id) {
  const item = name(data.item), median = num(data.median);
  if (!item || !median) return null;
  const n = count(data.count), map = name(data.map), pic = img(data.item_id);
  const content = `picked up **${item}**${n > 1 ? ` ×${n}` : ""} (about ${fmt(median)} mesos each)${map ? ` on ${map}` : ""}`;
  return base(id, data, content, pic ? [{ title: item, thumbnail: { url: pic } }] : null);
}

const KINDS = { sale, notice, grind, drop };

// the webhook payload for a post, or null when its data isn't what the kind takes
function render(kind, data, id) {
  if (!Object.prototype.hasOwnProperty.call(KINDS, kind) || !data || typeof data !== "object") return null;
  return KINDS[kind](data, id);
}

const blocked = (env, id) => String(env.BLOCKED_IDS || "").split(",").map(s => s.trim()).includes(id);

async function handler(req, res, deps = {}) {
  const env = deps.env || process.env, fetchFn = deps.fetch || fetch, now = deps.now || Date.now();
  if (req.method !== "POST" && req.method !== "GET") return res.status(405).json({ error: "GET or POST" });
  if (!env.UPLOAD_KEY || !env.DISCORD_WEBHOOK || !env.DISCORD_CLIENT_ID || !env.CARD_SECRET)
    return res.status(500).json({ error: "the server isn't set up" });
  if (!keyOk(req.headers["x-companion-key"], env.UPLOAD_KEY)) return res.status(401).json({ error: "bad key" });
  const on = mode(env.DISCORD_MODE, ["on", "off"], "on") === "on";
  if (req.method === "GET") return res.status(200).json({ client_id: String(env.DISCORD_CLIENT_ID), on });
  if (!on) return res.status(503).json({ error: "Discord posts are paused" });
  let body = req.body;
  if (typeof body === "string") {
    try { body = JSON.parse(body); } catch (e) { return res.status(400).json({ error: "bad JSON" }); }
  }
  if (!body || typeof body !== "object") return res.status(400).json({ error: "no JSON body" });

  if (body.link) {
    const token = String(body.link.token || "");
    if (!token || token.length > 200) return res.status(400).json({ error: "no token" });
    let me;
    try {
      const r = await fetchFn(`${API}/users/@me`, { headers: { Authorization: `Bearer ${token}` } });
      if (r.status !== 200) return res.status(502).json({ error: `Discord said ${r.status}` });
      me = await r.json();
    } catch (e) {
      return res.status(502).json({ error: "couldn't reach Discord" });
    }
    const id = String((me && me.id) || "");
    if (!/^\d{1,25}$/.test(id)) return res.status(502).json({ error: "Discord sent no user ID" });
    if (blocked(env, id)) return res.status(403).json({ error: "this Discord account can't post" });
    const shown = String(me.global_name || me.username || "?").slice(0, 40);
    return res.status(200).json({ id, name: shown, card: makeCard(id, Math.floor(now / 1000), env.CARD_SECRET) });
  }

  const id = readCard(body.card, env.CARD_SECRET);
  if (!id) return res.status(401).json({ error: "bad card: connect Discord again" });
  if (blocked(env, id)) return res.status(403).json({ error: "this Discord account can't post" });
  const msg = render(body.kind, body.data, id);
  if (!msg) return res.status(400).json({ error: "bad post" });
  const slow = throttle(deps.idStore || IDS, id, ID_LIMIT, ID_WINDOW, now);
  if (!slow.ok) return res.status(429).json({ error: "too many posts", retry_after: slow.retry_after });
  try {
    const r = await fetchFn(`${env.DISCORD_WEBHOOK}${env.DISCORD_WEBHOOK.includes("?") ? "&" : "?"}wait=true`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(msg),
    });
    if (r.status >= 200 && r.status < 300) return res.status(200).json({ ok: true });
    if (r.status === 429) {
      let wait = 5;
      try { wait = Number((await r.json()).retry_after) || 5; } catch (e) { /* keep 5 */ }
      return res.status(429).json({ error: "Discord asked to slow down", retry_after: wait });
    }
    console.error(`webhook answered ${r.status}`);
    return res.status(502).json({ error: `Discord answered ${r.status}` });
  } catch (e) {
    console.error(e);
    return res.status(502).json({ error: "couldn't reach Discord" });
  }
}

module.exports = handler;
module.exports.handler = handler;
module.exports.makeCard = makeCard;
module.exports.readCard = readCard;
module.exports.render = render;
