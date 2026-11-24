"use strict";

/**
 * AI Agent Factory — Code Execution Service.
 *
 * Receives agent-generated files from n8n, writes them into an isolated
 * per-project workspace, runs allowlisted npm steps (install/lint/test/
 * build) inside a throwaway Docker sandbox, and packages the source as a
 * ZIP. AI code is NEVER executed on the n8n host: in `docker` sandbox mode
 * every command runs in a resource-limited container with no secrets in
 * its environment; `local` mode exists only for development without
 * Docker and is clearly flagged as unsafe for untrusted code.
 */

const express = require("express");
const fs = require("fs");
const fsp = require("fs/promises");
const path = require("path");
const crypto = require("crypto");
const { execFile } = require("child_process");
const archiver = require("archiver");
const unzipper = require("unzipper");

const PORT = Number(process.env.PORT || 8080);
const DATA_DIR = process.env.DATA_DIR || "/data";
const WORKSPACES_DIR = path.join(DATA_DIR, "workspaces");
const ARCHIVES_DIR = path.join(DATA_DIR, "archives");
// Absolute path of WORKSPACES_DIR **on the Docker host** — required so the
// sandbox containers spawned through the host daemon mount the same files.
const HOST_WORKSPACES_DIR = process.env.HOST_WORKSPACES_DIR || "";
const SANDBOX_MODE = (process.env.SANDBOX_MODE || "docker").toLowerCase();
const SANDBOX_IMAGE = process.env.SANDBOX_IMAGE || "node:20-alpine";
const PUBLIC_BASE_URL = (process.env.PUBLIC_BASE_URL || `http://localhost:${PORT}`).replace(/\/$/, "");
const MONGODB_URI = process.env.MONGODB_URI || "mongodb://localhost:27017";
const MONGODB_DATABASE = process.env.MONGODB_DATABASE || "ai_factory";

const MAX_FILES_PER_REQUEST = 200;
const MAX_FILE_BYTES = 1_000_000;
const MAX_TOTAL_BYTES = 20_000_000;
const MAX_IMPORT_ENTRIES = 500;
const MAX_IMPORT_BYTES = 50_000_000;
const RUN_TIMEOUT_MS = 300_000;
const LOG_TAIL_CHARS = 8_000;

const PROJECT_ID_RE = /^[A-Za-z0-9-]{8,64}$/;
const ALLOWED_DOTFILES = new Set([".gitignore", ".env.example", ".npmrc", ".editorconfig"]);
const NEVER_PACKAGE = [/^node_modules\//, /^\.git\//, /(^|\/)\.env($|\.)(?!example)/, /\.log$/];

// MongoDB is connected lazily on first use: the service still starts and
// serves workspaces/builds even while the database container is booting.
let mongo = null;
let mongoConnecting = null;
async function db() {
  if (mongo) return mongo;
  if (!mongoConnecting) {
    mongoConnecting = (async () => {
      const { MongoClient, ObjectId } = require("mongodb");
      const client = new MongoClient(MONGODB_URI);
      await client.connect();
      const database = client.db(MONGODB_DATABASE);
      await database.collection("projects").createIndex({ id: 1 }, { unique: true });
      await database.collection("agent_runs").createIndex({ project_id: 1, created_at: 1 });
      await database.collection("tasks").createIndex({ project_id: 1 });
      await database.collection("qa_reviews").createIndex({ project_id: 1 });
      await database.collection("artifacts").createIndex({ project_id: 1 });
      mongo = { db: database, ObjectId };
      console.log("MongoDB connected:", MONGODB_URI.replace(/\/\/[^@]*@/, "//***@"), "database:", MONGODB_DATABASE);
      return mongo;
    })().catch((error) => { mongoConnecting = null; throw error; });
  }
  return mongoConnecting;
}

const app = express();
app.use(express.json({ limit: "30mb" }));
app.use(express.static(path.join(__dirname, "..", "public")));

function assertProjectId(req, res, next) {
  const id = req.params.id;
  if (!PROJECT_ID_RE.test(id || "")) {
    return res.status(400).json({ error: "invalid_project_id" });
  }
  req.projectDir = path.join(WORKSPACES_DIR, id);
  return next();
}

/** Normalise an agent-supplied relative path, or return null when unsafe. */
function safeRelativePath(raw) {
  if (typeof raw !== "string" || !raw.trim()) return null;
  const cleaned = raw.trim().replace(/\\/g, "/");
  if (cleaned.startsWith("/") || /^[A-Za-z]:/.test(cleaned)) return null;
  const segments = [];
  for (const segment of cleaned.split("/")) {
    if (segment === "" || segment === ".") continue;
    if (segment === "..") return null;
    if (segment.startsWith(".") && !ALLOWED_DOTFILES.has(segment)) return null;
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(segment) && !ALLOWED_DOTFILES.has(segment)) return null;
    segments.push(segment);
  }
  return segments.length ? segments.join("/") : null;
}

async function writeFiles(projectDir, files) {
  const written = [];
  const rejected = [];
  let total = 0;
  for (const file of files.slice(0, MAX_FILES_PER_REQUEST)) {
    const rel = safeRelativePath(file && file.path);
    if (!rel) {
      rejected.push({ path: String(file && file.path).slice(0, 120), reason: "unsafe_path" });
      continue;
    }
    const content = typeof file.content === "string" ? file.content : "";
    const bytes = Buffer.byteLength(content, "utf8");
    if (bytes > MAX_FILE_BYTES) {
      rejected.push({ path: rel, reason: "file_too_large" });
      continue;
    }
    total += bytes;
    if (total > MAX_TOTAL_BYTES) {
      rejected.push({ path: rel, reason: "total_too_large" });
      continue;
    }
    const target = path.join(projectDir, rel);
    await fsp.mkdir(path.dirname(target), { recursive: true });
    await fsp.writeFile(target, content, "utf8");
    written.push({ path: rel, size_bytes: bytes, sha256: crypto.createHash("sha256").update(content).digest("hex") });
  }
  return { written, rejected };
}

async function listTree(projectDir) {
  const out = [];
  async function walk(dir, prefix) {
    let entries;
    try {
      entries = await fsp.readdir(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      if (entry.name === "node_modules" || entry.name === ".git") continue;
      const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
      if (entry.isDirectory()) await walk(path.join(dir, entry.name), rel);
      else {
        const stat = await fsp.stat(path.join(dir, entry.name));
        out.push({ path: rel, size_bytes: stat.size });
      }
    }
  }
  await walk(projectDir, "");
  return out.sort((a, b) => a.path.localeCompare(b.path));
}

function runProcess(command, args, options, timeoutMs) {
  return new Promise((resolve) => {
    const child = execFile(command, args, { ...options, timeout: timeoutMs, maxBuffer: 16 * 1024 * 1024 }, (error, stdout, stderr) => {
      const log = `${stdout || ""}${stderr || ""}`;
      resolve({
        exit_code: error ? (typeof error.code === "number" ? error.code : 1) : 0,
        timed_out: Boolean(error && error.killed),
        log_tail: log.slice(-LOG_TAIL_CHARS),
      });
    });
    child.on("error", (error) => resolve({ exit_code: 1, timed_out: false, log_tail: String(error.message) }));
  });
}

/**
 * Run one npm step for a project. In docker mode the step executes in a
 * fresh sandbox container: resource-limited, no secrets, workspace mounted
 * read-write at /app, network only for the install step (npm registry).
 */
async function runStep(projectId, projectDir, step, scriptCommand) {
  if (SANDBOX_MODE === "local") {
    const result = await runProcess("npm", scriptCommand, { cwd: projectDir, env: { PATH: process.env.PATH } }, RUN_TIMEOUT_MS);
    return { step, mode: "local-unsafe", ...result };
  }
  if (!HOST_WORKSPACES_DIR) {
    return {
      step, mode: "docker", exit_code: 1, timed_out: false,
      log_tail: "HOST_WORKSPACES_DIR is not configured on the Code Execution Service, so the Docker sandbox cannot mount the workspace. Set it in .env (absolute host path of ./ces-data/workspaces) or use SANDBOX_MODE=local for development only.",
    };
  }
  const hostDir = path.join(HOST_WORKSPACES_DIR, projectId);
  const args = [
    "run", "--rm",
    "--memory", "1g", "--cpus", "2", "--pids-limit", "256",
    "-v", `${hostDir}:/app`, "-w", "/app",
  ];
  if (step !== "install") args.push("--network", "none");
  args.push(SANDBOX_IMAGE, "sh", "-c", `npm ${scriptCommand.join(" ")}`);
  const result = await runProcess("docker", args, {}, RUN_TIMEOUT_MS);
  return { step, mode: "docker", ...result };
}

app.get("/health", (_req, res) => {
  res.json({ status: "ok", sandbox_mode: SANDBOX_MODE, sandbox_image: SANDBOX_IMAGE });
});

app.post("/projects", async (req, res) => {
  const id = req.body && req.body.project_id;
  if (!PROJECT_ID_RE.test(id || "")) return res.status(400).json({ error: "invalid_project_id" });
  await fsp.mkdir(path.join(WORKSPACES_DIR, id), { recursive: true });
  return res.status(201).json({ project_id: id, workspace_ready: true });
});

app.post("/projects/:id/files", assertProjectId, async (req, res) => {
  const files = Array.isArray(req.body && req.body.files) ? req.body.files : null;
  if (!files) return res.status(400).json({ error: "files_array_required" });
  await fsp.mkdir(req.projectDir, { recursive: true });
  const result = await writeFiles(req.projectDir, files);
  return res.json({ project_id: req.params.id, ...result });
});

app.get("/projects/:id/files", assertProjectId, async (req, res) => {
  const files = await listTree(req.projectDir);
  return res.json({ project_id: req.params.id, files, total_bytes: files.reduce((sum, f) => sum + f.size_bytes, 0) });
});

app.post("/projects/:id/import", assertProjectId, async (req, res) => {
  const base64 = req.body && req.body.zip_base64;
  if (typeof base64 !== "string" || !base64) return res.status(400).json({ error: "zip_base64_required" });
  const buffer = Buffer.from(base64, "base64");
  if (buffer.length > MAX_IMPORT_BYTES) return res.status(413).json({ error: "zip_too_large" });
  await fsp.mkdir(req.projectDir, { recursive: true });
  const written = [];
  const rejected = [];
  let entries = 0;
  let total = 0;
  try {
    const directory = await unzipper.Open.buffer(buffer);
    for (const entry of directory.files) {
      entries += 1;
      if (entries > MAX_IMPORT_ENTRIES) { rejected.push({ path: entry.path, reason: "too_many_entries" }); break; }
      if (entry.type !== "File") continue;
      const rel = safeRelativePath(entry.path);
      if (!rel) { rejected.push({ path: entry.path.slice(0, 120), reason: "unsafe_path" }); continue; }
      const content = await entry.buffer();
      total += content.length;
      if (content.length > MAX_FILE_BYTES || total > MAX_IMPORT_BYTES) {
        rejected.push({ path: rel, reason: "file_too_large" });
        continue;
      }
      const target = path.join(req.projectDir, rel);
      await fsp.mkdir(path.dirname(target), { recursive: true });
      await fsp.writeFile(target, content);
      written.push({ path: rel, size_bytes: content.length });
    }
  } catch (error) {
    return res.status(400).json({ error: "invalid_zip", detail: String(error.message).slice(0, 200) });
  }
  return res.json({ project_id: req.params.id, written, rejected });
});

app.post("/projects/:id/run", assertProjectId, async (req, res) => {
  const requested = Array.isArray(req.body && req.body.steps) ? req.body.steps : ["install", "lint", "test", "build"];
  let scripts = {};
  try {
    const pkg = JSON.parse(await fsp.readFile(path.join(req.projectDir, "package.json"), "utf8"));
    scripts = pkg.scripts || {};
  } catch {
    return res.json({
      project_id: req.params.id,
      results: [{ step: "detect", exit_code: 1, log_tail: "No readable package.json in the workspace — nothing can be installed or built." }],
      build_ok: false,
    });
  }
  const stepCommands = {
    install: ["install", "--ignore-scripts", "--no-audit", "--no-fund"],
    lint: scripts.lint ? ["run", "lint"] : null,
    test: scripts.test ? ["run", "test", "--", "--watchAll=false"] : null,
    build: scripts.build ? ["run", "build"] : null,
  };
  const results = [];
  for (const step of ["install", "lint", "test", "build"]) {
    if (!requested.includes(step)) continue;
    const command = stepCommands[step];
    if (!command) {
      results.push({ step, exit_code: 0, skipped: true, log_tail: `No "${step}" script in package.json — skipped.` });
      continue;
    }
    const result = await runStep(req.params.id, req.projectDir, step, command);
    results.push(result);
    if (step === "install" && result.exit_code !== 0) break;
  }
  const build = results.find((r) => r.step === "build");
  return res.json({ project_id: req.params.id, results, build_ok: Boolean(build && build.exit_code === 0) });
});

app.post("/projects/:id/package", assertProjectId, async (req, res) => {
  const files = await listTree(req.projectDir);
  const included = files.filter((f) => !NEVER_PACKAGE.some((pattern) => pattern.test(f.path)));
  if (!included.length) return res.status(400).json({ error: "nothing_to_package" });
  await fsp.mkdir(ARCHIVES_DIR, { recursive: true });
  const zipPath = path.join(ARCHIVES_DIR, `${req.params.id}.zip`);
  await new Promise((resolve, reject) => {
    const output = fs.createWriteStream(zipPath);
    const archive = archiver("zip", { zlib: { level: 9 } });
    output.on("close", resolve);
    archive.on("error", reject);
    archive.pipe(output);
    for (const file of included) archive.file(path.join(req.projectDir, file.path), { name: file.path });
    archive.finalize();
  });
  const stat = await fsp.stat(zipPath);
  return res.json({
    project_id: req.params.id,
    file_count: included.length,
    size_bytes: stat.size,
    download_url: `${PUBLIC_BASE_URL}/projects/${req.params.id}/download`,
  });
});

app.get("/projects/:id/download", assertProjectId, async (req, res) => {
  const zipPath = path.join(ARCHIVES_DIR, `${req.params.id}.zip`);
  if (!fs.existsSync(zipPath)) return res.status(404).json({ error: "archive_not_found" });
  return res.download(zipPath, `${req.params.id}.zip`);
});

// --- Persistence API used by the n8n workflows (MongoDB backed) ---------
// The workflows never talk to the database directly: they POST documents
// here and this service stores them in MongoDB (collections: projects,
// tasks, agent_runs, qa_reviews, artifacts). Project ids are ObjectId hex
// strings, also stored on each project document as its `id` field.
function stripMongoId(doc) { if (doc) delete doc._id; return doc; }
function dbError(res, error) {
  return res.status(503).json({ error: "database_unavailable", detail: String(error.message).slice(0, 200) });
}

app.post("/db/projects", async (req, res) => {
  try {
    const { db: database, ObjectId } = await db();
    const _id = new ObjectId();
    const doc = { ...(req.body || {}), _id, id: _id.toHexString() };
    doc.created_at = doc.created_at || new Date().toISOString();
    await database.collection("projects").insertOne(doc);
    return res.json({ ok: true, id: doc.id, status: doc.status || "RUNNING",
      created_at: doc.created_at, mode: doc.mode || null, module_name: doc.module_name || null });
  } catch (error) { return dbError(res, error); }
});

app.post("/db/projects/update", async (req, res) => {
  try {
    const { db: database } = await db();
    const set = { ...((req.body && req.body.set) || {}), updated_at: new Date().toISOString() };
    const result = await database.collection("projects")
      .updateOne({ id: String((req.body && req.body.project_id) || "") }, { $set: set });
    return res.json({ ok: true, matched: result.matchedCount });
  } catch (error) { return dbError(res, error); }
});

app.post("/db/tasks", async (req, res) => {
  try {
    const { db: database } = await db();
    const docs = (req.body && Array.isArray(req.body.docs)) ? req.body.docs : [];
    if (docs.length) await database.collection("tasks").insertMany(docs);
    return res.json({ ok: true, inserted: docs.length });
  } catch (error) { return dbError(res, error); }
});

app.post("/db/runs", async (req, res) => {
  try {
    const { db: database } = await db();
    const result = await database.collection("agent_runs").insertOne({ ...(req.body || {}) });
    return res.json({ ok: true, id: result.insertedId.toHexString() });
  } catch (error) { return dbError(res, error); }
});

app.post("/db/runs/update", async (req, res) => {
  try {
    const { db: database, ObjectId } = await db();
    const body = req.body || {};
    const filter = (body.id && ObjectId.isValid(body.id)) ? { _id: new ObjectId(body.id) } : { task_id: body.task_id || "" };
    const result = await database.collection("agent_runs").updateOne(filter, { $set: body.set || {} });
    return res.json({ ok: true, matched: result.matchedCount });
  } catch (error) { return dbError(res, error); }
});

app.post("/db/reviews", async (req, res) => {
  try {
    const { db: database } = await db();
    const result = await database.collection("qa_reviews").insertOne({ ...(req.body || {}) });
    return res.json({ ok: true, id: result.insertedId.toHexString() });
  } catch (error) { return dbError(res, error); }
});

app.post("/db/artifacts", async (req, res) => {
  try {
    const { db: database } = await db();
    const docs = (req.body && Array.isArray(req.body.docs)) ? req.body.docs : [];
    if (docs.length) await database.collection("artifacts").insertMany(docs);
    return res.json({ ok: true, inserted: docs.length });
  } catch (error) { return dbError(res, error); }
});

// Receipts for MindFlow -> n8n events (e.g. agent.created). Upserted by
// (agent_id, event) so webhook retries stay idempotent.
app.post("/db/agent-events", async (req, res) => {
  try {
    const { db: database } = await db();
    const body = req.body || {};
    const doc = { ...body, received_at: body.received_at || new Date().toISOString() };
    const result = await database.collection("agent_events").updateOne(
      { agent_id: String(body.agent_id || ""), event: String(body.event || "") },
      { $set: doc },
      { upsert: true }
    );
    return res.json({ ok: true, upserted: result.upsertedCount, matched: result.matchedCount });
  } catch (error) { return dbError(res, error); }
});

// --- Read-only status API for the dashboard (MongoDB backed) -------------
app.get("/api/projects", async (_req, res) => {
  try {
    const { db: database } = await db();
    const rows = await database.collection("projects").find({}).sort({ created_at: -1 }).limit(100).toArray();
    return res.json({ projects: rows.map(stripMongoId) });
  } catch (error) { return dbError(res, error); }
});

app.get("/api/projects/:id", assertProjectId, async (req, res) => {
  try {
    const { db: database } = await db();
    const project = await database.collection("projects").findOne({ id: req.params.id });
    if (!project) return res.status(404).json({ error: "project_not_found" });
    const runs = await database.collection("agent_runs").find({ project_id: req.params.id }).sort({ created_at: 1 }).toArray();
    const tasks = await database.collection("tasks").find({ project_id: req.params.id }).sort({ created_at: 1 }).toArray();
    const qa = await database.collection("qa_reviews").find({ project_id: req.params.id }).sort({ created_at: 1 }).toArray();
    return res.json({ project: stripMongoId(project), agent_runs: runs.map(stripMongoId), tasks: tasks.map(stripMongoId), qa_reviews: qa.map(stripMongoId) });
  } catch (error) { return dbError(res, error); }
});

async function start() {
  await fsp.mkdir(WORKSPACES_DIR, { recursive: true });
  await fsp.mkdir(ARCHIVES_DIR, { recursive: true });
  app.listen(PORT, () => {
    console.log(`Code Execution Service listening on :${PORT} (sandbox=${SANDBOX_MODE})`);
    if (SANDBOX_MODE === "local") {
      console.warn("WARNING: SANDBOX_MODE=local executes agent code without Docker isolation. Development only.");
    }
  });
}

start().catch((error) => {
  console.error(error);
  process.exit(1);
});
