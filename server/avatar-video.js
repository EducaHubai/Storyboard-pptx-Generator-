/**
 * Avatar video pipeline — approved "epigrafe" plan → narrated mp4.
 *
 * For every slide with narration, asks HeyGen (API v3) for an avatar clip with
 * transparent background (webm + alpha), overlays it with ffmpeg on the PNG
 * screenshot of that slide (render_epigrafe/render.py <in> <out> <png_dir>),
 * and concatenates all slides into one mp4. Silent slides (titulo/cierre)
 * become a still image with silent audio so the final concat can stream-copy.
 *
 * Jobs run in the background (HeyGen takes minutes per clip, far beyond any
 * proxy timeout): POST starts one, GET polls progress, GET …/download streams.
 *
 * Env: HEYGEN_API_KEY (required), HEYGEN_AVATAR_ID / HEYGEN_VOICE_ID (defaults).
 */

const fs = require("fs");
const os = require("os");
const path = require("path");
const crypto = require("crypto");
const { execFile } = require("child_process");
const { promisify } = require("util");
const execFileAsync = promisify(execFile);

const HEYGEN_BASE = process.env.HEYGEN_API_BASE || "https://api.heygen.com";
const DEFAULT_AVATAR_ID = process.env.HEYGEN_AVATAR_ID || "Georgia_expressive_2024112701";
const CANVAS_W = 1920;
const CANVAS_H = 1080;
const FPS = 30;
const STATIC_SECONDS = 5;
const CLIP_CONCURRENCY = 3;
const JOB_TTL_MS = 60 * 60 * 1000;

// Avatar box as a fraction of the 1920x1080 canvas. The clip keeps its aspect
// ratio inside the box (bottom-centered). Sections not listed use `contenido`.
const AVATAR_ZONES = {
  inicio: { w: 0.28, h: 0.60, x: 0.72, y: 0.40 },
  resumen: { w: 0.15, h: 0.15, x: 0.83, y: 0.80, circle: true },
  cierre: { w: 0.16, h: 0.38, x: 0.82, y: 0.56 },
  contenido: { w: 0.20, h: 0.36, x: 0.78, y: 0.64 },
};

function zoneForSection(section) {
  return AVATAR_ZONES[section] || AVATAR_ZONES.contenido;
}

// ── HeyGen API ──────────────────────────────────────────────

class HeyGenClient {
  constructor(apiKey, { avatarId, voiceId }) {
    this.apiKey = apiKey;
    this.avatarId = avatarId;
    this.voiceId = voiceId;
  }

  _headers() {
    return { "x-api-key": this.apiKey, "Content-Type": "application/json" };
  }

  async listVoices() {
    const res = await fetch(`${HEYGEN_BASE}/v3/voices`, { headers: this._headers() });
    if (!res.ok) throw new Error(`HeyGen listVoices failed: ${res.status} ${await res.text()}`);
    return (await res.json()).data;
  }

  async createClip(script) {
    const res = await fetch(`${HEYGEN_BASE}/v3/videos`, {
      method: "POST",
      headers: this._headers(),
      body: JSON.stringify({
        type: "avatar",
        avatar_id: this.avatarId,
        script,
        voice_id: this.voiceId,
        resolution: "1080p",
        aspect_ratio: "1:1",
        output_format: "webm", // transparent background (alpha)
      }),
    });
    if (!res.ok) throw new Error(`HeyGen createClip failed: ${res.status} ${await res.text()}`);
    return (await res.json()).data.video_id;
  }

  async waitForClip(videoId, { intervalMs = 8000, timeoutMs = 15 * 60 * 1000 } = {}) {
    const start = Date.now();
    for (;;) {
      const res = await fetch(`${HEYGEN_BASE}/v3/videos/${videoId}`, { headers: this._headers() });
      if (!res.ok) throw new Error(`HeyGen getStatus failed: ${res.status} ${await res.text()}`);
      const data = (await res.json()).data;
      if (data.status === "completed") return data;
      if (data.status === "failed") {
        throw new Error(`HeyGen clip failed: ${data.failure_code} - ${data.failure_message}`);
      }
      if (Date.now() - start > timeoutMs) throw new Error(`Timeout waiting for HeyGen clip ${videoId}`);
      await new Promise((r) => setTimeout(r, intervalMs));
    }
  }
}

async function downloadFile(url, destPath) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Download failed: ${res.status}`);
  fs.writeFileSync(destPath, Buffer.from(await res.arrayBuffer()));
}

// ── ffmpeg ──────────────────────────────────────────────────

const ENCODE_ARGS = [
  "-r", String(FPS), "-pix_fmt", "yuv420p", "-c:v", "libx264",
  "-c:a", "aac", "-ar", "44100", "-ac", "2",
];

async function probeDuration(file) {
  const { stdout } = await execFileAsync("ffprobe", [
    "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", file,
  ]);
  const d = parseFloat(stdout);
  return Number.isFinite(d) ? d : null;
}

/** Still slide with silent audio (titulo/cierre or any slide without narration). */
async function renderStaticSlide({ slidePng, outputMp4, seconds = STATIC_SECONDS }) {
  await execFileAsync("ffmpeg", [
    "-y", "-loop", "1", "-i", slidePng,
    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
    "-vf", `scale=${CANVAS_W}:${CANVAS_H}`,
    "-t", String(seconds),
    ...ENCODE_ARGS, outputMp4,
  ]);
}

/** slidePng + avatar webm (alpha) → mp4 lasting exactly the clip duration. */
async function renderAvatarSlide({ slidePng, avatarWebm, section, durationSeconds, outputMp4 }) {
  const zone = zoneForSection(section);
  const ow = Math.round(CANVAS_W * zone.w);
  const oh = Math.round(CANVAS_H * zone.h);
  const ox = Math.round(CANVAS_W * zone.x);
  const oy = Math.round(CANVAS_H * zone.y);

  let avatarFilter;
  if (zone.circle) {
    const s = Math.min(ow, oh);
    const r = s / 2;
    avatarFilter =
      `scale=${s}:${s}:force_original_aspect_ratio=increase,crop=${s}:${s},format=rgba,` +
      `geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lte(pow(X-${r},2)+pow(Y-${r},2),${r * r}),alpha(X,Y),0)',` +
      `pad=${ow}:${oh}:(ow-iw)/2:(oh-ih)/2:color=black@0`;
  } else {
    avatarFilter =
      `scale=${ow}:${oh}:force_original_aspect_ratio=decrease,format=rgba,` +
      `pad=${ow}:${oh}:(ow-iw)/2:oh-ih:color=black@0`;
  }

  await execFileAsync("ffmpeg", [
    "-y",
    "-loop", "1", "-i", slidePng,
    // libvpx-vp9 decoder is required: ffmpeg's native VP9 decoder drops alpha.
    "-c:v", "libvpx-vp9", "-i", avatarWebm,
    "-filter_complex",
    `[1:v]${avatarFilter}[avatar];[0:v]scale=${CANVAS_W}:${CANVAS_H}[bg];[bg][avatar]overlay=${ox}:${oy}[v]`,
    "-map", "[v]", "-map", "1:a?",
    "-t", String(durationSeconds),
    ...ENCODE_ARGS, outputMp4,
  ]);
}

async function concatSlides(mp4Paths, outputPath, workDir) {
  const listPath = path.join(workDir, "concat_list.txt");
  fs.writeFileSync(listPath, mp4Paths.map((p) => `file '${p}'`).join("\n"));
  await execFileAsync("ffmpeg", [
    "-y", "-f", "concat", "-safe", "0", "-i", listPath, "-c", "copy", outputPath,
  ]);
}

// ── Plan helpers ────────────────────────────────────────────

/** Spoken text for HeyGen, or null for silent slides. */
function narrationFor(script) {
  const text = (script || "").trim();
  if (!text || /^\[no narration/i.test(text)) return null;
  // "[pause]" markers are for the human reader; HeyGen would read them aloud.
  return text.replace(/\s*\[pause\]\s*/gi, " … ").trim();
}

async function mapPool(items, limit, fn) {
  const results = new Array(items.length);
  let next = 0;
  const worker = async () => {
    while (next < items.length) {
      const i = next++;
      results[i] = await fn(items[i], i);
    }
  };
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return results;
}

// ── Jobs ────────────────────────────────────────────────────

const jobs = new Map();

async function runJob(job, { plan, scripts, client, renderScript, pythonBin }) {
  const slidesDir = path.join(job.dir, "png");
  try {
    // 1. Render slide PNGs (same Chromium renderer as the pptx).
    job.step = "Rendering slides";
    const inputPath = path.join(job.dir, "input.json");
    fs.writeFileSync(inputPath, JSON.stringify({ plan, scripts }));
    await execFileAsync(pythonBin, [renderScript, inputPath, path.join(job.dir, "deck.pptx"), slidesDir]);

    // 2. One HeyGen clip per narrated slide.
    const scriptByN = new Map(scripts.map((s) => [s.n, s.script]));
    const slides = plan.slides.map((slide, i) => ({
      i,
      section: slide.section,
      text: narrationFor(scriptByN.get(slide.n)),
    }));
    const narrated = slides.filter((s) => s.text);
    job.total = narrated.length;
    job.done = 0;
    job.step = "Generating avatar clips";

    const clips = new Map();
    await mapPool(narrated, CLIP_CONCURRENCY, async (s) => {
      const videoId = await client.createClip(s.text);
      const result = await client.waitForClip(videoId);
      const webm = path.join(job.dir, `avatar_${s.i}.webm`);
      await downloadFile(result.video_url, webm);
      clips.set(s.i, { webm, duration: result.duration });
      job.done += 1;
    });

    // 3. Composite + concat.
    job.step = "Compositing video";
    const mp4s = [];
    for (const s of slides) {
      const slidePng = path.join(slidesDir, `slide_${s.i}.png`);
      const outputMp4 = path.join(job.dir, `slide_${s.i}.mp4`);
      const clip = clips.get(s.i);
      if (clip) {
        const durationSeconds = (await probeDuration(clip.webm)) || clip.duration;
        await renderAvatarSlide({ slidePng, avatarWebm: clip.webm, section: s.section, durationSeconds, outputMp4 });
      } else {
        await renderStaticSlide({ slidePng, outputMp4 });
      }
      mp4s.push(outputMp4);
    }
    job.file = path.join(job.dir, "final.mp4");
    await concatSlides(mp4s, job.file, job.dir);
    job.status = "done";
    job.step = "Done";
  } catch (err) {
    console.error("avatar-video job failed:", err);
    job.status = "error";
    job.error = err.message;
  }
}

function publicJob(job) {
  return { status: job.status, step: job.step, done: job.done, total: job.total, error: job.error || null };
}

function cleanupJob(id) {
  const job = jobs.get(id);
  if (job) fs.rm(job.dir, { recursive: true, force: true }, () => {});
  jobs.delete(id);
}

// ── Routes ──────────────────────────────────────────────────

/**
 * @param app Express app
 * @param opts { renderScript, pythonBin, isEpigrafePlan(plan) }
 */
function registerAvatarVideoRoutes(app, { renderScript, pythonBin, isEpigrafePlan }) {
  let voicesCache = null;

  app.get("/api/heygen/config", (req, res) => {
    res.json({
      configured: Boolean(process.env.HEYGEN_API_KEY),
      defaultAvatarId: DEFAULT_AVATAR_ID,
      defaultVoiceId: process.env.HEYGEN_VOICE_ID || null,
    });
  });

  app.get("/api/heygen/voices", async (req, res) => {
    try {
      if (!process.env.HEYGEN_API_KEY) return res.status(500).json({ error: "Server is missing HEYGEN_API_KEY." });
      if (!voicesCache || Date.now() - voicesCache.at > 10 * 60 * 1000) {
        const client = new HeyGenClient(process.env.HEYGEN_API_KEY, {});
        const voices = await client.listVoices();
        voicesCache = {
          at: Date.now(),
          data: voices.map((v) => ({ id: v.voice_id, name: v.name, gender: v.gender, language: v.language })),
        };
      }
      res.json(voicesCache.data);
    } catch (err) {
      console.error("heygen voices error:", err);
      res.status(502).json({ error: "Failed to list HeyGen voices", detail: err.message });
    }
  });

  app.post("/api/avatar-video", (req, res) => {
    const { plan, scripts, avatarId, voiceId } = req.body || {};
    if (!process.env.HEYGEN_API_KEY) return res.status(500).json({ error: "Server is missing HEYGEN_API_KEY." });
    if (!plan || !Array.isArray(plan.slides) || !Array.isArray(scripts)) {
      return res.status(400).json({ error: "Missing 'plan' (with slides) or 'scripts' in request body." });
    }
    if (!isEpigrafePlan(plan)) {
      return res.status(400).json({ error: "Avatar video is only available for the epigrafe format." });
    }
    const voice = voiceId || process.env.HEYGEN_VOICE_ID;
    if (!voice) return res.status(400).json({ error: "Missing 'voiceId' (and no HEYGEN_VOICE_ID default is set)." });

    const id = crypto.randomUUID();
    const job = {
      id, status: "running", step: "Queued", done: 0, total: 0,
      dir: fs.mkdtempSync(path.join(os.tmpdir(), "avatar-video-")),
      file: null, error: null,
    };
    jobs.set(id, job);
    setTimeout(() => cleanupJob(id), JOB_TTL_MS).unref();

    const client = new HeyGenClient(process.env.HEYGEN_API_KEY, {
      avatarId: avatarId || DEFAULT_AVATAR_ID,
      voiceId: voice,
    });
    runJob(job, { plan, scripts, client, renderScript, pythonBin });
    res.status(202).json({ jobId: id });
  });

  app.get("/api/avatar-video/:id", (req, res) => {
    const job = jobs.get(req.params.id);
    if (!job) return res.status(404).json({ error: "Unknown or expired job." });
    res.json(publicJob(job));
  });

  app.get("/api/avatar-video/:id/download", (req, res) => {
    const job = jobs.get(req.params.id);
    if (!job || job.status !== "done") return res.status(404).json({ error: "Video not ready or expired." });
    res.download(job.file, req.query.name ? `${String(req.query.name).replace(/[^\w.-]+/g, "-")}.mp4` : "avatar-video.mp4");
  });
}

module.exports = {
  registerAvatarVideoRoutes,
  // exported for offline tests
  renderAvatarSlide, renderStaticSlide, concatSlides, narrationFor, AVATAR_ZONES,
};
