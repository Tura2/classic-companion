"use strict";
const test = require("node:test");
const assert = require("node:assert");
const handler = require("./api/report.js");
const { wantFiles } = handler;

const ENV = { UPLOAD_KEY: "k3y", GITHUB_TOKEN: "t", REPORTS_REPO: "o/r" };
let n = 0;
const PNG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 1, 2, 3]).toString("base64");
const JPG = Buffer.from([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3]).toString("base64");
function body(over = {}, files = { "frame.png": PNG }) {
  const id = `20261126-1015${String(n++ % 60).padStart(2, "0")}-map_missed-a1b2c3`;
  return { report: { id, kind: "map_missed", key: "map_missed:henesys-hunting-ground-i", why: "title read as 'Hennes'",
                     version: "1.4.6", made: "2026-11-26 10:15:00", frame_size: [1920, 1080], profile: { name: "Me" }, ...over },
           files };
}

function res() {
  const r = { code: 0, body: null };
  r.status = c => { r.code = c; return r; };
  r.json = b => { r.body = b; return r; };
  return r;
}

// a stand-in for GitHub's git API that keeps index.json between commits. moved: how many ref
// updates say the branch moved
function github(moved = 0, index = null) {
  const calls = [];
  const repo = { index: index ? JSON.stringify(index) : null, files: [], pending: null };
  const fetch = async (url, opt) => {
    const path = url.replace("https://api.github.com", ""), b = opt.body ? JSON.parse(opt.body) : null;
    calls.push({ method: opt.method, path, body: b });
    const ok = data => ({ ok: true, status: 200, text: async () => JSON.stringify(data) });
    const no = (status, m) => ({ ok: false, status, text: async () => JSON.stringify({ message: m }) });
    if (path.includes("/contents/index.json"))
      return repo.index === null ? no(404, "Not Found") : ok({ content: Buffer.from(repo.index).toString("base64") });
    if (path.endsWith("/git/blobs")) return ok({ sha: "blob1" });
    if (path.includes("/git/ref/heads/")) return ok({ object: { sha: "head" } });
    if (path.includes("/git/commits/")) return ok({ tree: { sha: "tree0" } });
    if (path.endsWith("/git/trees")) { repo.pending = b.tree; return ok({ sha: "tree1" }); }
    if (path.endsWith("/git/commits")) return ok({ sha: "commit1" });
    if (path.includes("/git/refs/heads/")) {
      if (moved-- > 0) return no(422, "not a fast forward");
      for (const e of repo.pending) {
        if (e.path === "index.json") repo.index = e.content;
        else repo.files.push(e.path);
      }
      return ok({});
    }
    return no(404, "?");
  };
  return { fetch, calls, repo, index: () => JSON.parse(repo.index) };
}

// opt: env (added to ENV), now, ip, and the IP throttle's store (one per github() stand-in)
const send = (g, b, headers = { "x-companion-key": "k3y" }, opt = {}) => {
  const r = res();
  g.store = g.store || new Map();
  return handler({ method: "POST", headers, body: b }, r,
                 { env: { ...ENV, ...(opt.env || {}) }, fetch: g.fetch, now: opt.now, ip: opt.ip, ipStore: g.store }).then(() => r);
};
const ask = (g, query) => {
  const r = res();
  return handler({ method: "GET", headers: { "x-companion-key": "k3y" }, query }, r, { env: ENV, fetch: g.fetch }).then(() => r);
};

test("the first report of a problem is filed with its pictures, and the index counts it", async () => {
  const g = github();
  const r = await send(g, body());
  assert.equal(r.code, 201);
  assert.equal(r.body.stored, true);
  assert.match(r.body.path, /^reports\/2026-11-26\/map_missed\/20261126-1015\d\d-map_missed-a1b2c3$/);
  assert.deepEqual(g.repo.files.sort(), [r.body.path + "/frame.png", r.body.path + "/report.json"]);
  const e = g.index()["map_missed:henesys-hunting-ground-i"];
  assert.equal(e.count, 1);
  assert.deepEqual(e.sizes, { "1920x1080": 1 });
  assert.deepEqual(e.players, { Me: 1 });
});

test("after a few with pictures, the same problem only adds to its count", async () => {
  const g = github();
  for (let i = 0; i < 5; i++) await send(g, body());
  const e = g.index()["map_missed:henesys-hunting-ground-i"];
  assert.equal(e.count, 5);
  assert.equal(e.samples, 3);
  assert.equal(g.repo.files.filter(f => f.endsWith("frame.png")).length, 3);
  assert.equal((await ask(g, { key: "map_missed:henesys-hunting-ground-i", version: "1.4.6", size: "1920x1080" })).body.want_files, false);
  // a screen size it hasn't been seen at is still wanted
  assert.equal((await ask(g, { key: "map_missed:henesys-hunting-ground-i", version: "1.4.6", size: "2560x1440" })).body.want_files, true);
  assert.equal((await ask(g, { key: "exp_missed:1920x1080:1.0", version: "1.4.6", size: "1920x1080" })).body.want_files, true);
  // a count-only report (no files) is counted, nothing else written
  const r = await send(g, body({ count_only: true }, {}));
  assert.equal(r.body.stored, false);
  assert.equal(g.index()["map_missed:henesys-hunting-ground-i"].count, 6);
});

test("a fixed problem: old builds only count, a report from the fixed version on means it's back", async () => {
  const key = "map_missed:henesys-hunting-ground-i";
  const g = github(0, { [key]: { kind: "map_missed", count: 40, samples: 3, sample_sizes: ["1920x1080"], versions: {}, sizes: {},
                                 players: {}, paths: [], fixed: { version: "1.4.7" } } });
  let r = await send(g, body({ version: "1.4.6" }));
  assert.equal(r.body.stored, false);
  assert.equal(g.index()[key].back, undefined);
  r = await send(g, body({ version: "1.4.7" }));
  assert.equal(r.body.stored, true);
  assert.ok(g.index()[key].back);
  assert.equal(g.index()[key].samples_back, 1);
});

test("the branch moving meanwhile is built on, with the newer index", async () => {
  const g = github(1);
  const r = await send(g, body());
  assert.equal(r.code, 201);
  assert.equal(g.calls.filter(c => c.method === "PATCH").length, 2);
  assert.equal(g.calls.filter(c => c.path.endsWith("/git/blobs")).length, 1);   // the pictures uploaded once
});

test("a wrong key, a bad name or another method is refused before GitHub is asked", async () => {
  const cases = [
    [{ method: "POST", headers: { "x-companion-key": "nope" }, body: body() }, 401],
    [{ method: "POST", headers: {}, body: body() }, 401],
    [{ method: "PUT", headers: { "x-companion-key": "k3y" } }, 405],
    [{ method: "POST", headers: { "x-companion-key": "k3y" }, body: body({}, { "../x.png": "AA==" }) }, 400],
    [{ method: "POST", headers: { "x-companion-key": "k3y" }, body: body({ id: "../../x" }) }, 400],
    [{ method: "POST", headers: { "x-companion-key": "k3y" }, body: body({ key: "a/../b" }) }, 400],
    [{ method: "GET", headers: { "x-companion-key": "k3y" }, query: { key: "../x" } }, 400],
  ];
  for (const [req, code] of cases) {
    const g = github(), r = res();
    await handler(req, r, { env: ENV, fetch: g.fetch });
    assert.equal(r.code, code);
    assert.equal(g.calls.length, 0);
  }
});

test("without its settings the server says so", async () => {
  const r = res();
  await handler({ method: "POST", headers: { "x-companion-key": "k3y" }, body: body() }, r, { env: {}, fetch: async () => { throw new Error(); } });
  assert.equal(r.code, 500);
});

test("wantFiles: versions compare as numbers", () => {
  const e = { samples: 3, fixed: { version: "1.4.10" } };
  assert.equal(wantFiles(e, "1.4.9", ""), false);
  assert.equal(wantFiles(e, "1.4.10", ""), true);
  assert.equal(wantFiles(e, "1.5", ""), true);
});

// ---- hardening: day caps, real pictures, mode, several keys, the IP throttle

const DAY = Date.UTC(2026, 10, 27, 12, 0);
const key = i => `map_missed:map-${i}`;

test("pictures stop after DAY_STORED a day, reports still count", async () => {
  const g = github();
  const out = [];
  for (let i = 0; i < 3; i++) out.push(await send(g, body({ key: key(i) }), undefined, { env: { DAY_STORED: "2" }, now: DAY }));
  assert.deepEqual(out.map(r => r.code), [201, 201, 201]);
  assert.deepEqual(out.map(r => r.body.stored), [true, true, false]);
  assert.equal(g.index()["#day"].stored, 2);
  assert.equal(g.index()[key(2)].count, 1);
});

test("a new key over DAY_NEW_KEYS is refused, a known key still counts", async () => {
  const g = github();
  const opt = { env: { DAY_NEW_KEYS: "2" }, now: DAY };
  await send(g, body({ key: key(0) }), undefined, opt);
  await send(g, body({ key: key(1) }), undefined, opt);
  const r = await send(g, body({ key: key(2) }), undefined, opt);
  assert.equal(r.code, 429);
  assert.equal(g.index()[key(2)], undefined);
  assert.equal(g.calls.filter(c => c.path.endsWith("/git/blobs")).length, 2);     // nothing uploaded for it
  const again = await send(g, body({ key: key(0) }), undefined, opt);
  assert.equal(again.code, 201);
  assert.equal(g.index()[key(0)].count, 2);
});

test("DAY_PER_INSTALL: the 26th report from one install in a day is refused", async () => {
  const g = github();
  const opt = { now: DAY };
  for (let i = 0; i < 25; i++) assert.equal((await send(g, body({ install: "abc123" }), undefined, opt)).code, 201);
  assert.equal((await send(g, body({ install: "abc123" }), undefined, opt)).code, 429);
  assert.equal((await send(g, body({ install: "other1" }), undefined, opt)).code, 201);
});

test("a new UTC day resets the counters", async () => {
  const g = github();
  const opt = { env: { DAY_NEW_KEYS: "1", DAY_STORED: "1" }, now: DAY };
  await send(g, body({ key: key(0) }), undefined, opt);
  assert.equal((await send(g, body({ key: key(1) }), undefined, opt)).code, 429);
  const next = { ...opt, now: DAY + 24 * 3600 * 1000 };
  const r = await send(g, body({ key: key(1) }), undefined, next);
  assert.equal(r.code, 201);
  assert.equal(r.body.stored, true);
  assert.deepEqual(g.index()["#day"], { date: "2026-11-28", stored: 1, new_keys: 1, installs: {}, total: 1 });
});

test("a .png that isn't a PNG, or a .jpg that isn't a JPEG, is refused before GitHub is asked", async () => {
  for (const files of [{ "frame.png": Buffer.from("png!").toString("base64") }, { "frame.jpg": PNG }]) {
    const g = github();
    const r = await send(g, body({}, files));
    assert.equal(r.code, 400);
    assert.equal(g.calls.length, 0);
  }
  const g = github();
  assert.equal((await send(g, body({}, { "frame.jpg": JPG, "crop_map.png": PNG }))).code, 201);
});

test("REPORTS_MODE count stores no pictures; off answers 503 without asking GitHub", async () => {
  let g = github();
  let r = await send(g, body(), undefined, { env: { REPORTS_MODE: "count" } });
  assert.equal(r.code, 201);
  assert.equal(r.body.stored, false);
  assert.equal(g.calls.filter(c => c.path.endsWith("/git/blobs")).length, 0);
  g = github();
  r = await send(g, body(), undefined, { env: { REPORTS_MODE: "off" } });
  assert.equal(r.code, 503);
  assert.equal(g.calls.length, 0);
  const a = res();
  await handler({ method: "GET", headers: { "x-companion-key": "k3y" }, query: { key: key(0) } }, a,
                { env: { ...ENV, REPORTS_MODE: "count" }, fetch: github().fetch, ipStore: new Map() });
  assert.equal(a.body.want_files, false);
});

test("either of two upload keys is accepted", async () => {
  for (const k of ["old1", "new2"]) {
    const g = github();
    const r = await send(g, body(), { "x-companion-key": k }, { env: { UPLOAD_KEY: "old1,new2" } });
    assert.equal(r.code, 201);
  }
  assert.equal((await send(github(), body(), { "x-companion-key": "old1,new2" }, { env: { UPLOAD_KEY: "old1,new2" } })).code, 401);
});

test("31 requests from one IP in 10 minutes: the 31st is 429", async () => {
  const g = github();
  for (let i = 0; i < 30; i++) assert.equal((await send(g, body(), undefined, { ip: "9.9.9.9", now: DAY + i })).code, 201);
  const r = await send(g, body(), undefined, { ip: "9.9.9.9", now: DAY + 31 });
  assert.equal(r.code, 429);
  assert.ok(r.body.retry_after > 0);
  assert.equal((await send(g, body(), undefined, { ip: "8.8.8.8", now: DAY + 31 })).code, 201);
});
