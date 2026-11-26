"use strict";
const test = require("node:test");
const assert = require("node:assert");
const handler = require("./api/report.js");

const ENV = { UPLOAD_KEY: "k3y", GITHUB_TOKEN: "t", REPORTS_REPO: "o/r" };
const BODY = { report: { id: "20261126-101500-map_missed-a1b2c3", kind: "map_missed", why: "title read as 'Hennes'",
                         version: "1.4.6", profile: { name: "Me" } },
               files: { "frame.png": Buffer.from("png!").toString("base64") } };

function res() {
  const r = { code: 0, body: null };
  r.status = c => { r.code = c; return r; };
  r.json = b => { r.body = b; return r; };
  return r;
}

// a stand-in for GitHub's git API; moved: how many times the ref update says the branch moved
function github(moved = 0) {
  const calls = [];
  const fetch = async (url, opt) => {
    const path = url.replace("https://api.github.com", ""), body = opt.body ? JSON.parse(opt.body) : null;
    calls.push({ method: opt.method, path, body });
    const ok = data => ({ ok: true, status: 200, text: async () => JSON.stringify(data) });
    if (path.endsWith("/git/blobs")) return ok({ sha: "blob1" });
    if (path.includes("/git/ref/heads/")) return ok({ object: { sha: "head" + calls.length } });
    if (path.includes("/git/commits/")) return ok({ tree: { sha: "tree0" } });
    if (path.endsWith("/git/trees")) return ok({ sha: "tree1" });
    if (path.endsWith("/git/commits")) return ok({ sha: "commit1" });
    if (path.includes("/git/refs/heads/")) {
      if (moved-- > 0) return { ok: false, status: 422, text: async () => '{"message":"not a fast forward"}' };
      return ok({});
    }
    return { ok: false, status: 404, text: async () => "{}" };
  };
  return { fetch, calls };
}

test("a report is filed in one commit, under its day and kind", async () => {
  const g = github(), r = res();
  await handler({ method: "POST", headers: { "x-companion-key": "k3y" }, body: BODY }, r, { env: ENV, fetch: g.fetch });
  assert.equal(r.code, 201);
  assert.equal(r.body.path, "reports/2026-11-26/map_missed/20261126-101500-map_missed-a1b2c3");
  const tree = g.calls.find(c => c.path.endsWith("/git/trees")).body.tree.map(e => e.path);
  assert.deepEqual(tree.sort(), [r.body.path + "/frame.png", r.body.path + "/report.json"]);
  assert.equal(g.calls.filter(c => c.method === "PATCH").length, 1);
});

test("the branch moving meanwhile is built on, not lost", async () => {
  const g = github(1), r = res();
  await handler({ method: "POST", headers: { "x-companion-key": "k3y" }, body: BODY }, r, { env: ENV, fetch: g.fetch });
  assert.equal(r.code, 201);
  assert.equal(g.calls.filter(c => c.method === "PATCH").length, 2);
});

test("a wrong key, a bad name or a non-POST is refused before GitHub is asked", async () => {
  for (const [req, code] of [
    [{ method: "POST", headers: { "x-companion-key": "nope" }, body: BODY }, 401],
    [{ method: "POST", headers: {}, body: BODY }, 401],
    [{ method: "GET", headers: { "x-companion-key": "k3y" } }, 405],
    [{ method: "POST", headers: { "x-companion-key": "k3y" }, body: { ...BODY, files: { "../x.png": "AA==" } } }, 400],
    [{ method: "POST", headers: { "x-companion-key": "k3y" }, body: { ...BODY, report: { ...BODY.report, id: "../../x" } } }, 400],
  ]) {
    const g = github(), r = res();
    await handler(req, r, { env: ENV, fetch: g.fetch });
    assert.equal(r.code, code);
    assert.equal(g.calls.length, 0);
  }
});

test("without its settings the server says so", async () => {
  const r = res();
  await handler({ method: "POST", headers: { "x-companion-key": "k3y" }, body: BODY }, r, { env: {}, fetch: async () => { throw new Error(); } });
  assert.equal(r.code, 500);
});
