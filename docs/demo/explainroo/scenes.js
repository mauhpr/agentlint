// Illustrated operations and captured decisions; no writes or commands run.
// Every frame is deterministic; narration supplies the reveal cues.
const C = {
  paper: '#f5f2eb', white: '#fffef9', ink: '#1d3027', muted: '#5f6c63',
  line: '#dddcd2', tray: '#e8e6dc', green: '#2e654c', mint: '#e1ebdf',
  dark: '#1d3027', darkLine: '#415448', light: '#f5f2eb', soft: '#bccbbf',
  red: '#a44234', rose: '#f1dfd8', amber: '#886324', sand: '#efe5cf',
};
const clamp = (p) => Math.max(0, Math.min(1, p));
const settle = (p) => 1 - Math.pow(1 - clamp(p), 4);

function rr(ctx, x, y, w, h, r, color) {
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
  ctx.fill();
}

function line(ctx, points, color = C.line, width = 2) {
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.beginPath();
  points.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y));
  ctx.stroke();
}

function dot(ctx, x, y, r, fill) {
  ctx.fillStyle = fill;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fill();
}

function mark(ctx, x, y, size, color = C.green) {
  const k = size / 48;
  ctx.save();
  ctx.translate(x, y);
  ctx.scale(k, k);
  line(ctx, [[9, 6], [1, 6], [1, 42], [9, 42]], color, 3);
  line(ctx, [[39, 6], [47, 6], [47, 42], [39, 42]], color, 3);
  line(ctx, [[13, 25], [21, 33], [36, 15]], color, 4);
  ctx.restore();
}

function check(ctx, x, y, color, bg, size = 48) {
  dot(ctx, x, y, size / 2, bg);
  line(ctx, [[x - size * .20, y], [x - size * .04, y + size * .14],
    [x + size * .23, y - size * .16]], color, 3.5);
}

// A quiet, consistent frame: one surface, 2px inset, no shadow or OS chrome.
function panel(ctx, x, y, w, h, color = C.white, tray = C.tray) {
  rr(ctx, x, y, w, h, 22, tray);
  rr(ctx, x + 2, y + 2, w - 4, h - 4, 20, color);
}

// Every label is visible to ExplainRoo's checker. Width failures stop the
// render instead of silently truncating, wrapping, or squeezing a font.
function text(s, value, x, y, o = {}) {
  const { size = 40, weight = 400, font = 'Geist', color = C.ink,
    maxWidth, ...rest } = o;
  const width = s.ui.measure(value, size, weight, font, !!rest.italic, rest.tracking ?? 0);
  if (maxWidth && width > maxWidth + .5) {
    throw new Error(`Text exceeds its panel: ${JSON.stringify(value)} (${Math.ceil(width)} > ${maxWidth}px)`);
  }
  return s.ui.text(value, x, y, { size, weight, font, color, ...rest });
}

function mono(s, value, x, y, o = {}) {
  return text(s, value, x, y, { font: 'Geist Mono', ...o });
}

function reveal(s, at, fn, delay = 0, out) {
  const start = s.time(at) + delay;
  s.draw({ at: start, out, exit: 'none', enter: 'none', dur: .72, sfx: false }, (ctx) => {
    const p = settle((s.t - start) / .72);
    ctx.globalAlpha *= p;
    ctx.translate(0, (1 - p) * 22);
    fn(ctx);
  });
}

// Custom burned-in captions use ExplainRoo's aligned narration words. A fixed
// strip separates captions from content and uses the project's own font.
function captions(s) {
  const phrases = [];
  let words = [];
  let length = 0;
  for (const word of s.words) {
    const gap = words.length && word.start - words[words.length - 1].end > .55;
    if (words.length && (length + word.text.length > 100 || gap)) {
      phrases.push(words);
      words = [];
      length = 0;
    }
    words.push(word);
    length += word.text.length + 1;
    if (/[.!?;:,]["'’)]*$/.test(word.text) && words.length >= 4) {
      phrases.push(words);
      words = [];
      length = 0;
    }
  }
  if (words.length) phrases.push(words);
  const index = phrases.findIndex((p, i) => s.t >= p[0].start - .06 &&
    s.t < Math.min(phrases[i + 1]?.[0].start ?? Infinity, p[p.length - 1].end + .8));
  if (index < 0) return;
  const phrase = phrases[index];
  const rows = [''];
  for (const word of phrase) {
    const row = rows.length - 1;
    const next = rows[row] ? `${rows[row]} ${word.text}` : word.text;
    if (s.ui.measure(next, 42, 400, 'Geist') > 1440 && rows[row]) rows.push(word.text);
    else rows[row] = next;
  }
  if (rows.length > 2) throw new Error('Caption exceeds its two-line strip');
  rows.forEach((row, i) => text(s, row, 960, 944 + (i - (rows.length - 1) / 2) * 54,
    { size: 42, align: 'center', color: C.ink, maxWidth: 1440 }));
}

function stage(s) {
  s.ui.backdrop(C.paper);
  const ctx = s.ctx;
  mark(ctx, 90, 72, 46);
  text(s, 'AgentLint', 158, 96, { size: 44, weight: 600, tracking: -1 });
  // Panels end at y=824; all labels stay above y=850. Captions: y=876..1006.
  captions(s);
}

export default {
  intro(s) {
    stage(s);
    text(s, 'AgentLint', 960, 326,
      { size: 136, weight: 600, align: 'center', tracking: -4, maxWidth: 1680 });
    reveal(s, '#product', () => text(s, 'Guardrails for AI coding agents.', 960, 485,
      { size: 84, font: 'Instrument Serif', italic: true, weight: 400,
        align: 'center', color: C.green, tracking: -1, maxWidth: 1680 }));
    reveal(s, '#checks', () => text(s, 'File changes + shell commands', 960, 659,
      { size: 48, align: 'center', color: C.muted, maxWidth: 1680 }));
  },

  problem(s) {
    stage(s);
    text(s, 'Catch mistakes early.', 960, 278,
      { size: 88, weight: 600, align: 'center', tracking: -2, maxWidth: 1680 });
    reveal(s, '#risk', () => text(s, 'Credentials in source', 270, 451,
      { size: 64, color: C.red, weight: 500, maxWidth: 1380 }));
    reveal(s, '#delete', () => text(s, 'Destructive commands', 270, 575,
      { size: 64, color: C.red, weight: 500, maxWidth: 1380 }));
    reveal(s, '#boundary', (ctx) => {
      line(ctx, [[270, 671], [1650, 671]], C.line);
      text(s, 'Checked before execution', 270, 754,
        { size: 48, color: C.green, weight: 500, maxWidth: 1380 });
    });
  },

  block(s) {
    stage(s);
    panel(s.ctx, 180, 290, 1560, 278, C.dark);
    text(s, 'Proposed write · config.py', 246, 348,
      { size: 38, color: C.soft, maxWidth: 1428 });
    reveal(s, '#propose', () => {
      // Separate code tokens provide syntax emphasis; the value is masked.
      let x = 246;
      for (const [value, color] of [['api_key', C.light], [' = ', C.light], ['"<redacted>"', '#f0ae9c']]) {
        x += mono(s, value, x, 462, { size: 64, color, maxWidth: 1428 });
      }
    });
    reveal(s, '#deny', (ctx) => {
      dot(ctx, 208, 650, 28, C.rose);
      line(ctx, [[199, 641], [217, 659]], C.red, 4);
      line(ctx, [[199, 659], [217, 641]], C.red, 4);
      text(s, 'Write blocked', 266, 650,
        { size: 58, weight: 500, color: C.red, maxWidth: 1394 });
      text(s, 'Secret assignment detected: api_key=...', 266, 724,
        { size: 38, color: C.muted, maxWidth: 1394 });
    });
    reveal(s, '#guidance', () => text(s, 'Use environment variables instead of hard-coded secrets.', 266, 793,
      { size: 38, color: C.muted, maxWidth: 1394 }));
    s.sfx('error', '#deny', { gain: .10 });
  },

  recover(s) {
    stage(s);
    // One focal state at a time: corrected source, then the next tool call.
    reveal(s, -1, (ctx) => {
      panel(ctx, 180, 290, 1560, 340, C.dark);
      text(s, 'Corrected write · config.py', 246, 348,
        { size: 38, color: C.soft, maxWidth: 1428 });
    }, 0, '#continue');
    reveal(s, '#correct', () => {
      mono(s, 'import os', 246, 439, { size: 56, color: C.light, maxWidth: 1428 });
      mono(s, 'api_key = os.environ["PAYMENT_API_KEY"]', 246, 528,
        { size: 52, color: C.light, maxWidth: 1428 });
    }, 0, '#continue');
    reveal(s, '#allow', (ctx) => {
      check(ctx, 208, 710, C.green, C.mint, 56);
      text(s, 'Write allowed', 266, 710,
        { size: 58, weight: 500, color: C.green, maxWidth: 1394 });
      text(s, 'No blocking findings', 266, 784,
        { size: 40, color: C.muted, maxWidth: 1394 });
    }, 0, '#continue');
    reveal(s, '#continue', (ctx) => {
      text(s, 'Work continues.', 960, 275,
        { size: 88, weight: 600, align: 'center', tracking: -2, maxWidth: 1680 });
      panel(ctx, 180, 381, 1560, 232, C.dark);
      text(s, 'Next tool call', 246, 430, { size: 38, color: C.soft, maxWidth: 1428 });
      mono(s, 'pytest', 246, 510, { size: 64, color: C.light, maxWidth: 1428 });
      check(ctx, 208, 713, C.green, C.mint, 56);
      text(s, 'Tool call allowed', 266, 713,
        { size: 54, weight: 500, color: C.green, maxWidth: 1394 });
    });
    s.sfx('ding', '#allow', { gain: .08 });
  },

  features(s) {
    stage(s);
    text(s, 'Built for your workflow.', 960, 270,
      { size: 88, weight: 600, align: 'center', tracking: -2, maxWidth: 1680 });
    const rows = [
      { label: 'Runs locally', at: '#local', y: 413 },
      { label: 'Configurable rule packs', at: '#rules', y: 532 },
      { label: 'Hook and CI checks', at: '#ci', y: 651 },
    ];
    for (const row of rows) {
      reveal(s, row.at, (ctx) => {
        check(ctx, 260, row.y, C.green, C.mint, 48);
        text(s, row.label, 320, row.y,
          { size: 58, weight: 500, maxWidth: 1330 });
      });
    }
    reveal(s, '#agents', () => text(s, 'Claude Code · Codex · Cursor · more', 960, 803,
      { size: 44, color: C.green, align: 'center', maxWidth: 1680 }));
  },

  install(s) {
    stage(s);
    text(s, 'Start in your repo.', 960, 270,
      { size: 88, weight: 600, align: 'center', tracking: -2, maxWidth: 1680 });
    panel(s.ctx, 180, 366, 1560, 328, C.dark);
    const steps = [
      { number: '01', command: 'uv tool install agentlint', at: '#install', y: 439 },
      { number: '02', command: 'agentlint setup codex', at: '#connect', y: 529 },
      { number: '03', command: 'agentlint status', at: '#verify', y: 619 },
    ];
    for (const step of steps) {
      text(s, step.number, 230, step.y, { size: 36, color: C.soft });
      reveal(s, step.at, () => mono(s, step.command, 310, step.y,
        { size: 56, color: C.light, maxWidth: 1364 }));
    }
    reveal(s, '#link', () => text(s, 'github.com/mauhpr/agentlint', 960, 800,
      { size: 46, weight: 500, align: 'center', color: C.green, maxWidth: 1560 }));
  },
};
