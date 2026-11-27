// Companion's problem report server: takes reports from Companion (app/autoreport.py) and files
// them in a private GitHub repository.
//
// One problem (a report's "key": its kind and what was misread) is one entry in index.json at the
// repository's root: how many times, when first and last, at which versions, screen sizes and by
// whom. Only its first few reports keep their pictures (a few more for a screen size it hadn't been
// seen at); after that a report only adds to the count. So the repository grows with the number of
// different problems, not with how often they happen, and index.json is the list of what to fix.
//
//   reports/YYYY-MM-DD/<kind>/<report id>/report.json, frame.png (or frame.jpg + crops), last_ok.jpg
//
// Fixed: set "fixed": {"version": "1.4.7"} on an entry in index.json. Reports from older versions
// then only count; one from 1.4.7 or later means it's back: "back" is set and pictures are kept again.
//
//   GET  ?key=&version=&size=   {"want_files": bool}: whether to send this problem's pictures
//   POST {report, files}        files it (files dropped when not wanted); {"ok", "stored", "count"}
//
// Environment (Vercel → Project → Settings → Environment Variables; never in the code):
//   UPLOAD_KEY     the key built into Companion (reports.json). It can only add reports, nothing else
//   GITHUB_TOKEN   a fine-grained token with Contents: read and write on REPORTS_REPO only
//   REPORTS_REPO   owner/name of the private repository, e.g. Tura2/companion-reports
//   REPORTS_BRANCH optional, default main
//
// The request body is at most 4.5 MB (Vercel's limit): Companion keeps its files under about 3 MB.
"use strict";
const crypto = require("crypto");

const API = "https://api.github.com";
const MAX_FILES = 8;
const MAX_FILE_B64 = 4_400_000;
const SAMPLES = 3;          // reports of a problem kept with their pictures
const SAMPLES_MAX = 6;      // ...plus one per new screen size, up to this many
const SAMPLES_BACK = 3;     // ...and this many again once it's back after a fix
const KEEP_PATHS = 10;
const NAME = /^[a-z0-9_]{1,40}\.(png|jpg)$/;
const KIND = /^[a-z_]{1,24}$/;
const ID = /^[0-9]{8}-[0-9]{6}-[a-z_]{1,24}-[0-9a-f]{6}$/;
const KEY = /^[A-Za-z0-9_.:x-]{1,120}$/;

function sameKey(a, b) {
  const x = Buffer.from(String(a || "")), y = Buffer.from(String(b || ""));
  return x.length === y.length && x.length > 0 && crypto.timingSafeEqual(x, y);
}

function vtuple(v) {
  return String(v || "0").split(".").map(n => parseInt(n, 10) || 0);
}

function atLeast(v, w) {
  const a = vtuple(v), b = vtuple(w);
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    if ((a[i] || 0) !== (b[i] || 0)) return (a[i] || 0) > (b[i] || 0);
  }
  return true;
}

// whether a report of this problem, from this version at this screen size, should keep its pictures
function wantFiles(entry, version, size) {
  if (!entry) return true;
  if (entry.fixed && entry.fixed.version) {
    if (!atLeast(version, entry.fixed.version)) return false;       // an old build: known, fixed since
    return (entry.samples_back || 0) < SAMPLES_BACK;
  }
  const n = entry.samples || 0;
  if (n < SAMPLES) return true;
  return n < SAMPLES_MAX && !!size && !(entry.sample_sizes || []).includes(size);
}

const bump = (obj, k) => { if (k) obj[k] = (obj[k] || 0) + 1; return obj; };

// the index entry after this report
function record(entry, r, stored, dir) {
  const e = entry ? JSON.parse(JSON.stringify(entry)) : {
    kind: r.kind, count: 0, first: r.made, samples: 0, sample_sizes: [], versions: {}, sizes: {}, players: {}, paths: [],
  };
  const size = Array.isArray(r.frame_size) ? r.frame_size.join("x") : "";
  e.count += 1;
  e.last = r.made;
  e.why = String(r.why || "").slice(0, 300);
  bump(e.versions, r.version || "?");
  bump(e.sizes, size);
  bump(e.players, (r.profile && r.profile.name) || r.install || "?");
  if (e.fixed && e.fixed.version && atLeast(r.version, e.fixed.version)) e.back = r.made;
  if (stored) {
    if (e.fixed && e.fixed.version) e.samples_back = (e.samples_back || 0) + 1;
    else e.samples = (e.samples || 0) + 1;
    if (size && !e.sample_sizes.includes(size)) e.sample_sizes.push(size);
    e.paths = [...(e.paths || []), dir].slice(-KEEP_PATHS);
  }
  return e;
}

// what's wrong with the body, or null
function check(body) {
  if (!body || typeof body !== "object") return "no JSON body";
  const r = body.report, files = body.files || {};
  if (!r || typeof r !== "object") return "no report";
  if (!KIND.test(String(r.kind))) return "bad kind";
  if (!ID.test(String(r.id))) return "bad id";
  if (!KEY.test(String(r.key))) return "bad key";
  const names = Object.keys(files);
  if (names.length > MAX_FILES) return "too many files";
  for (const n of names) {
    if (!NAME.test(n)) return `bad file name ${n}`;
    if (typeof files[n] !== "string" || files[n].length > MAX_FILE_B64 || !/^[A-Za-z0-9+/=]*$/.test(files[n]))
      return `bad file ${n}`;
  }
  return null;
}

async function gh(fetchFn, token, method, path, body) {
  const res = await fetchFn(API + path, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "companion-reports",
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (e) { data = { message: text }; }
  if (!res.ok) {
    const err = new Error(`GitHub ${method} ${path.split("?")[0]}: ${res.status} ${(data && data.message) || ""}`);
    err.status = res.status;
    throw err;
  }
  return data;
}

function repoOf(env) {
  return { repo: env.REPORTS_REPO, branch: env.REPORTS_BRANCH || "main", token: env.GITHUB_TOKEN };
}

// index.json at a commit ({} before the first report)
async function readIndex(fetchFn, env, sha) {
  const { repo, token } = repoOf(env);
  try {
    const f = await gh(fetchFn, token, "GET", `/repos/${repo}/contents/index.json?ref=${sha}`);
    if (f.content) return JSON.parse(Buffer.from(f.content, "base64").toString("utf8"));
    const blob = await gh(fetchFn, token, "GET", `/repos/${repo}/git/blobs/${f.sha}`);    // over 1 MB
    return JSON.parse(Buffer.from(blob.content, "base64").toString("utf8"));
  } catch (e) {
    if (e.status === 404) return {};
    throw e;
  }
}

async function head(fetchFn, env) {
  const { repo, branch, token } = repoOf(env);
  const ref = await gh(fetchFn, token, "GET", `/repos/${repo}/git/ref/heads/${branch}`);
  return ref.object.sha;
}

// one commit with the index and, when wanted, every file of the report; tries again on a branch
// that moved meanwhile (another report landed), on the new index
async function file(fetchFn, env, body) {
  const { repo, branch, token } = repoOf(env);
  const r = body.report;
  const day = `${r.id.slice(0, 4)}-${r.id.slice(4, 6)}-${r.id.slice(6, 8)}`;
  const dir = `reports/${day}/${r.kind}/${r.id}`;
  const size = Array.isArray(r.frame_size) ? r.frame_size.join("x") : "";
  let blobs = null;
  for (let attempt = 0; attempt < 4; attempt++) {
    const parent = await head(fetchFn, env);
    const index = await readIndex(fetchFn, env, parent);
    const files = body.files || {};
    const stored = Object.keys(files).length > 0 && wantFiles(index[r.key], r.version, size);
    if (stored && !blobs) {
      blobs = [];
      for (const [name, b64] of Object.entries(files)) {
        const blob = await gh(fetchFn, token, "POST", `/repos/${repo}/git/blobs`, { content: b64, encoding: "base64" });
        blobs.push({ path: `${dir}/${name}`, mode: "100644", type: "blob", sha: blob.sha });
      }
    }
    index[r.key] = record(index[r.key], r, stored, dir);
    const tree = [{ path: "index.json", mode: "100644", type: "blob", content: JSON.stringify(index, null, 1) + "\n" }];
    if (stored) tree.push({ path: `${dir}/report.json`, mode: "100644", type: "blob", content: JSON.stringify(r, null, 1) }, ...blobs);
    const commit = await gh(fetchFn, token, "GET", `/repos/${repo}/git/commits/${parent}`);
    const t = await gh(fetchFn, token, "POST", `/repos/${repo}/git/trees`, { base_tree: commit.tree.sha, tree });
    const who = (r.profile && r.profile.name) || r.install || "?";
    const n = index[r.key].count;
    const made = await gh(fetchFn, token, "POST", `/repos/${repo}/git/commits`, {
      message: `${r.key} ×${n}${stored ? "" : " (counted)"}: ${String(r.why || "").slice(0, 100)}\n\n${who} · Companion ${r.version || "?"} · ${r.id}`,
      tree: t.sha,
      parents: [parent],
    });
    try {
      await gh(fetchFn, token, "PATCH", `/repos/${repo}/git/refs/heads/${branch}`, { sha: made.sha, force: false });
      return { dir: stored ? dir : null, stored, count: n };
    } catch (e) {
      if (e.status !== 422 || attempt === 3) throw e;      // 422: the branch moved; build on the new tip
    }
  }
}

async function handler(req, res, deps = {}) {
  const env = deps.env || process.env, fetchFn = deps.fetch || fetch;
  if (req.method !== "POST" && req.method !== "GET") return res.status(405).json({ error: "GET or POST" });
  if (!env.UPLOAD_KEY || !env.GITHUB_TOKEN || !env.REPORTS_REPO)
    return res.status(500).json({ error: "the server isn't set up" });
  if (!sameKey(req.headers["x-companion-key"], env.UPLOAD_KEY)) return res.status(401).json({ error: "bad key" });
  if (req.method === "GET") {
    const q = req.query || Object.fromEntries(new URL(req.url || "/", "http://x").searchParams);
    if (!KEY.test(String(q.key || ""))) return res.status(400).json({ error: "bad key" });
    try {
      const index = await readIndex(fetchFn, env, await head(fetchFn, env));
      return res.status(200).json({ want_files: wantFiles(index[q.key], q.version, String(q.size || "")) });
    } catch (e) {
      console.error(e);
      return res.status(200).json({ want_files: true });
    }
  }
  let body = req.body;
  if (typeof body === "string") {
    try { body = JSON.parse(body); } catch (e) { return res.status(400).json({ error: "bad JSON" }); }
  }
  const bad = check(body);
  if (bad) return res.status(400).json({ error: bad });
  try {
    const out = await file(fetchFn, env, body);
    return res.status(201).json({ ok: true, path: out.dir, stored: out.stored, count: out.count });
  } catch (e) {
    console.error(e);
    return res.status(502).json({ error: "couldn't file the report" });
  }
}

module.exports = handler;
module.exports.handler = handler;
module.exports.check = check;
module.exports.wantFiles = wantFiles;
module.exports.record = record;
