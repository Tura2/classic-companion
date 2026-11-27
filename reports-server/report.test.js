"use strict";
const test = require("node:test");
const assert = require("node:assert");
const handler = require("./api/report.js");
const { wantFiles } = handler;

const ENV = { UPLOAD_KEY: "k3y", GITHUB_TOKEN: "t", REPORTS_REPO: "o/r" };
let n = 0;
function body(over = {}, files = { "frame.png": Buffer.from("png!").toString("base64") }) {
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

const send = (g, b, headers = { "x-companion-key": "k3y" }) => {
  const r = res();
  return handler({ method: "POST", headers, body: b }, r, { env: ENV, fetch: g.fetch }).then(() => r);
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
