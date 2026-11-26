// Companion's problem report server: takes a report from Companion (app/autoreport.py) and files
// it in a private GitHub repository, one commit per report:
//   reports/YYYY-MM-DD/<kind>/<report id>/report.json, frame.png (or frame.jpg + crops), last_ok.jpg
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
const NAME = /^[a-z0-9_]{1,40}\.(png|jpg)$/;
const KIND = /^[a-z_]{1,24}$/;
const ID = /^[0-9]{8}-[0-9]{6}-[a-z_]{1,24}-[0-9a-f]{6}$/;

function sameKey(a, b) {
  const x = Buffer.from(String(a || "")), y = Buffer.from(String(b || ""));
  return x.length === y.length && x.length > 0 && crypto.timingSafeEqual(x, y);
}

// what's wrong with the body, or null
function check(body) {
  if (!body || typeof body !== "object") return "no JSON body";
  const r = body.report, files = body.files || {};
  if (!r || typeof r !== "object") return "no report";
  if (!KIND.test(String(r.kind))) return "bad kind";
  if (!ID.test(String(r.id))) return "bad id";
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

// one commit with every file of the report; tries again if someone else's commit landed meanwhile
async function file(fetchFn, env, body) {
  const repo = env.REPORTS_REPO, branch = env.REPORTS_BRANCH || "main", token = env.GITHUB_TOKEN;
  const r = body.report;
  const day = String(r.id).slice(0, 4) + "-" + String(r.id).slice(4, 6) + "-" + String(r.id).slice(6, 8);
  const dir = `reports/${day}/${r.kind}/${r.id}`;
  const entries = [{ path: `${dir}/report.json`, content: JSON.stringify(r, null, 1) }];
  const blobs = [];
  for (const [name, b64] of Object.entries(body.files || {})) {
    const blob = await gh(fetchFn, token, "POST", `/repos/${repo}/git/blobs`, { content: b64, encoding: "base64" });
    blobs.push({ path: `${dir}/${name}`, mode: "100644", type: "blob", sha: blob.sha });
  }
  for (let attempt = 0; attempt < 3; attempt++) {
    const ref = await gh(fetchFn, token, "GET", `/repos/${repo}/git/ref/heads/${branch}`);
    const parent = ref.object.sha;
    const commit = await gh(fetchFn, token, "GET", `/repos/${repo}/git/commits/${parent}`);
    const tree = await gh(fetchFn, token, "POST", `/repos/${repo}/git/trees`, {
      base_tree: commit.tree.sha,
      tree: [...entries.map(e => ({ path: e.path, mode: "100644", type: "blob", content: e.content })), ...blobs],
    });
    const who = (r.profile && r.profile.name) || r.install || "?";
    const made = await gh(fetchFn, token, "POST", `/repos/${repo}/git/commits`, {
      message: `${r.kind}: ${String(r.why || "").slice(0, 120)}\n\n${who} · Companion ${r.version || "?"} · ${r.id}`,
      tree: tree.sha,
      parents: [parent],
    });
    try {
      await gh(fetchFn, token, "PATCH", `/repos/${repo}/git/refs/heads/${branch}`, { sha: made.sha, force: false });
      return dir;
    } catch (e) {
      if (e.status !== 422 || attempt === 2) throw e;      // 422: the branch moved; build on the new tip
    }
  }
}

async function handler(req, res, deps = {}) {
  const env = deps.env || process.env, fetchFn = deps.fetch || fetch;
  if (req.method !== "POST") return res.status(405).json({ error: "POST only" });
  if (!env.UPLOAD_KEY || !env.GITHUB_TOKEN || !env.REPORTS_REPO)
    return res.status(500).json({ error: "the server isn't set up" });
  if (!sameKey(req.headers["x-companion-key"], env.UPLOAD_KEY)) return res.status(401).json({ error: "bad key" });
  let body = req.body;
  if (typeof body === "string") {
    try { body = JSON.parse(body); } catch (e) { return res.status(400).json({ error: "bad JSON" }); }
  }
  const bad = check(body);
  if (bad) return res.status(400).json({ error: bad });
  try {
    const dir = await file(fetchFn, env, body);
    return res.status(201).json({ ok: true, path: dir });
  } catch (e) {
    console.error(e);
    return res.status(502).json({ error: "couldn't file the report" });
  }
}

module.exports = handler;
module.exports.check = check;
module.exports.handler = handler;
