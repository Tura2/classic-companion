"use strict";
const test = require("node:test");
const assert = require("node:assert");
const handler = require("./api/discord.js");
const { makeCard, readCard, render } = handler;

const ENV = { UPLOAD_KEY: "k3y", DISCORD_WEBHOOK: "https://discord.example/api/webhooks/1/abc", DISCORD_CLIENT_ID: "999",
              CARD_SECRET: "s".repeat(40) };
const NOW = Date.UTC(2026, 10, 27, 12, 0);
const IMG = "https://raw.githubusercontent.com/ohmi69/osms_datamine_dashboard/main/data/current/images/items/04000000.png";

function res() {
  const r = { code: 0, body: null };
  r.status = c => { r.code = c; return r; };
  r.json = b => { r.body = b; return r; };
  return r;
}

// Discord's /users/@me and the webhook: answers from a script, records what was posted
function discord({ me = { id: "123", global_name: "Tura" }, meCode = 200, hook = [] } = {}) {
  const calls = [], answers = [...hook];
  const fetch = async (url, opt = {}) => {
    calls.push({ url, opt, body: opt.body ? JSON.parse(opt.body) : null });
    if (url.endsWith("/users/@me")) return { ok: meCode === 200, status: meCode, json: async () => me, text: async () => JSON.stringify(me) };
    const a = answers.shift() || { status: 200, body: { id: "m1" } };
    return { ok: a.status < 300, status: a.status, json: async () => a.body, text: async () => JSON.stringify(a.body) };
  };
  return { fetch, calls, posts: () => calls.filter(c => c.url.startsWith(ENV.DISCORD_WEBHOOK)) };
}

const call = (d, method, body, opt = {}) => {
  const r = res();
  d.store = d.store || new Map();
  return handler({ method, headers: { "x-companion-key": opt.key || "k3y" }, body },
                 r, { env: { ...ENV, ...(opt.env || {}) }, fetch: d.fetch, now: opt.now || NOW, idStore: d.store }).then(() => r);
};
const card = (id = "123") => makeCard(id, 1764240000, ENV.CARD_SECRET);
const post = (d, kind, data, opt = {}) => call(d, "POST", { card: "card" in opt ? opt.card : card(), kind, data }, opt);

test("GET tells the Connect page the app's client ID", async () => {
  const r = await call(discord(), "GET");
  assert.deepEqual(r.body, { client_id: "999", on: true });
  assert.equal((await call(discord(), "GET", null, { env: { DISCORD_MODE: "off" } })).body.on, false);
});

test("link asks Discord who the token is and returns a card that reads back to that ID", async () => {
  const d = discord();
  const r = await call(d, "POST", { link: { token: "tok-abc" } });
  assert.equal(r.code, 200);
  assert.equal(r.body.id, "123");
  assert.equal(r.body.name, "Tura");
  assert.equal(readCard(r.body.card, ENV.CARD_SECRET), "123");
  assert.ok(!JSON.stringify(r.body).includes("tok-abc"));
  assert.equal(d.calls[0].opt.headers.Authorization, "Bearer tok-abc");
  const bad = await call(discord({ meCode: 401 }), "POST", { link: { token: "tok" } });
  assert.equal(bad.code, 502);
});

test("a changed card, or one signed with another secret, is refused", async () => {
  const c = card();
  const parts = c.split(".");
  for (const k of [[parts[0], "124", parts[2], parts[3]].join("."), makeCard("123", 1764240000, "other".repeat(8)), "v1.123", ""]) {
    const d = discord();
    const r = await post(d, "notice", { what: "test" }, { card: k });
    assert.equal(r.code, 401);
    assert.equal(d.posts().length, 0);
  }
  assert.equal(readCard(c, ENV.CARD_SECRET), "123");
});

test("a blocked ID is refused, at link and at post", async () => {
  const env = { BLOCKED_IDS: "1, 123" };
  assert.equal((await post(discord(), "notice", { what: "test" }, { env })).code, 403);
  assert.equal((await call(discord(), "POST", { link: { token: "t" } }, { env })).code, 403);
  assert.equal((await post(discord(), "notice", { what: "test" }, { card: card("12") , env })).code, 200);
});

test("every post mentions only the sender", async () => {
  const kinds = [
    ["sale", { sales: [{ item: "Bazlud", count: 1, price: 24999 }] }],
    ["notice", { what: "soldout" }],
    ["grind", { map: "Ant Tunnel I", minutes: 12, exp_gained: 30000, level_start: 40, level_end: 40, party: false, loot_top: [] }],
    ["drop", { item: "Work Gloves", count: 1, median: 120000 }],
  ];
  for (const [kind, data] of kinds) {
    const d = discord();
    assert.equal((await post(d, kind, { ...data, character: "Tura1" })).code, 200, kind);
    const m = d.posts()[0].body;
    assert.deepEqual(m.allowed_mentions, { parse: [], users: ["123"] }, kind);
    assert.ok(m.content.startsWith("<@123> "), kind);
    assert.equal(m.username, "Tura1");
    assert.ok(d.posts()[0].url.endsWith("?wait=true"));
  }
});

test("sale renders like before: the item, the price against the median, its picture, the day's total", () => {
  const m = render("sale", { sales: [{ item: "Bazlud", item_id: 4000000, count: 1, price: 24999, median: 20000 }], total_today: 24999 }, "123");
  assert.ok(m.content.startsWith("<@123> sold Bazlud ×1 for 24,999 mesos"));
  assert.ok(m.embeds[0].description.includes("25% above the market median"));
  assert.equal(m.embeds[0].thumbnail.url, IMG);
  assert.equal(m.embeds[0].footer.text, "Shop total today: 24,999");
  assert.equal(render("sale", { sales: [{ count: 1, price: 777 }] }, "123").content, "<@123> sold something for +777 mesos");
  const two = render("sale", { sales: [{ item: "A", count: 1, price: 100 }, { item: "B", count: 2, price: 50 }] }, "123");
  assert.equal(two.content, "<@123> sold 2 things for 150 mesos");
  assert.equal(two.embeds.length, 2);
  assert.equal(render("sale", { sales: [] }, "123"), null);
  assert.equal(render("sale", { sales: [{ item: "A", count: 1, price: -5 }] }, "123"), null);
});

test("notice sends only its fixed sentences", () => {
  assert.equal(render("notice", { what: "soldout" }, "123").content, "<@123> your shop sold out: time to restock.");
  assert.equal(render("notice", { what: "test" }, "123").content, "<@123> this is a test from Companion.");
  assert.equal(render("notice", { what: "correction", items: [{ item: "Bazlud", count: 2 }, { count: 1 }] }, "123").content,
               "<@123> correction: Bazlud x2, something didn't sell after all, that post was wrong (your shop's Total Sales doesn't show it).");
  assert.equal(render("notice", { what: "@everyone hi" }, "123"), null);
  assert.equal(render("nope", {}, "123"), null);
});

test("grind renders the map, time, EXP/hr, levels, kills, party and top pickups", () => {
  const m = render("grind", { map: "Ant Tunnel I", minutes: 83, exp_gained: 150000, exp_hr: 108433, level_start: 40, level_end: 41,
                              kills_total: 512, party: true, mesos: 21500, job: "Hunter",
                              loot_top: [{ name: "Horny Mushroom Cap", count: 40 }, { name: "Mesos Bag", count: 3 }] }, "123");
  assert.equal(m.embeds[0].title, "Ant Tunnel I");
  const f = Object.fromEntries(m.embeds[0].fields.map(x => [x.name, x.value]));
  assert.equal(f.Time, "1h 23m");
  assert.equal(f["EXP/hr"], "108,433");
  assert.equal(f["EXP gained"], "150,000");
  assert.equal(f.Level, "40 → 41");
  assert.equal(f.Kills, "512");
  assert.equal(f.With, "Party");
  assert.equal(f["Top pickups"], "Horny Mushroom Cap ×40\nMesos Bag ×3");
  assert.equal(f.Mesos, "21,500");
  const solo = render("grind", { map: "Ant Tunnel I", minutes: 10, exp_gained: 1, level_start: 40, level_end: 40, party: false, loot_top: [] }, "123");
  const g = Object.fromEntries(solo.embeds[0].fields.map(x => [x.name, x.value]));
  assert.equal(g.Time, "10m");
  assert.equal(g.Level, "40");
  assert.equal(g.With, "Solo");
  assert.equal(g.Kills, undefined);
  assert.equal(render("grind", { minutes: 10 }, "123"), null);       // no map
});

test("drop renders the item, its price each and its picture", () => {
  const m = render("drop", { item: "Work Gloves", item_id: 4000000, count: 1, median: 120000, map: "Ant Tunnel I" }, "123");
  assert.equal(m.content, "<@123> picked up **Work Gloves** (about 120,000 mesos each) on Ant Tunnel I");
  assert.equal(m.embeds[0].thumbnail.url, IMG);
  assert.equal(render("drop", { item: "Work Gloves", count: 2, median: 90000 }, "123").content,
               "<@123> picked up **Work Gloves** ×2 (about 90,000 mesos each)");
  assert.equal(render("drop", { item: "Work Gloves", count: 1 }, "123"), null);
});

test("names with @, <, or links are cleaned; usernames kept to 12 letters", () => {
  const m = render("drop", { item: "<@&1> @everyone https://x.y/z", count: 1, median: 90000, character: "Tura1<script>LongName" }, "123");
  assert.ok(!/[<>@\/]/.test(m.content.slice("<@123> ".length)), m.content);
  assert.ok(!m.content.includes("://"), m.content);
  assert.equal(m.username, "Tura1scriptL");
  assert.equal(render("drop", { item: "Work Gloves", count: 1, median: 90000, character: "@@" }, "123").username, "Companion");
  assert.equal(render("drop", { item: "Work Gloves", count: 1, median: 90000, item_id: "../x" }, "123").embeds, undefined);
});

test("21 posts in 10 minutes from one ID: the 21st is 429 with retry_after", async () => {
  const d = discord();
  for (let i = 0; i < 20; i++) assert.equal((await post(d, "notice", { what: "test" }, { now: NOW + i })).code, 200);
  const r = await post(d, "notice", { what: "test" }, { now: NOW + 21 });
  assert.equal(r.code, 429);
  assert.ok(r.body.retry_after > 0);
  assert.equal(d.posts().length, 20);
});

test("Discord's 429 is passed back with its retry_after", async () => {
  const d = discord({ hook: [{ status: 429, body: { retry_after: 7.5 } }] });
  const r = await post(d, "notice", { what: "test" });
  assert.equal(r.code, 429);
  assert.equal(r.body.retry_after, 7.5);
  const e = await post(discord({ hook: [{ status: 500, body: {} }] }), "notice", { what: "test" });
  assert.equal(e.code, 502);
});

test("DISCORD_MODE off is 503, a wrong upload key is 401, an unknown kind is 400", async () => {
  assert.equal((await post(discord(), "notice", { what: "test" }, { env: { DISCORD_MODE: "off" } })).code, 503);
  assert.equal((await post(discord(), "notice", { what: "test" }, { key: "nope" })).code, 401);
  assert.equal((await post(discord(), "nope", {})).code, 400);
  const r = res();
  await handler({ method: "POST", headers: { "x-companion-key": "k3y" }, body: {} }, r, { env: { UPLOAD_KEY: "k3y" }, fetch: async () => {} });
  assert.equal(r.code, 500);
});
