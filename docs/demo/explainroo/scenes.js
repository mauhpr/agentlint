// Illustrated commands and hook decisions, not a screen recording.
// Exact block text is captured by ../capture.py. No displayed command runs.
const C = { ink: '#f0f6fc', muted: '#b5c2ce', green: '#63e6be', red: '#ff8b87', yellow: '#f3ce75' };

function stage(s, title, label = 'ILLUSTRATED HOOK DEMO') {
  s.ui.backdrop();
  s.text('AgentLint', { x: 180, y: 104, size: 48, font: 'body', bold: true, align: 'left', at: -1, enter: 'none', color: C.green, sfx: false });
  s.text(label, { x: 1740, y: 104, size: 36, font: 'body', align: 'right', at: -1, enter: 'none', color: C.muted, sfx: false });
  s.text(title, { y: 244, size: 82, font: 'body', bold: true, at: -1, enter: 'none', color: C.ink, sfx: false });
}

function terminal(s, lines, at, out, title = 'Proposed tool call · illustrated') {
  return s.terminal(lines, { x: s.cx, y: 510, w: 1540, size: 48, rows: 4, title, cps: 34, at, out, sfx: false });
}

export default {
  hook(s) {
    stage(s, 'Check before the action');
    s.box('Coding agent', { id: 'agent', x: 380, y: 526, w: 360, h: 180, size: 50, font: 'body', icon: 'terminal', color: 'blue', textColor: C.ink, at: '#agent', sfx: false });
    s.box('AgentLint', { id: 'guard', x: 960, y: 526, w: 360, h: 180, size: 50, font: 'body', icon: 'shield-check', color: 'green', textColor: C.ink, at: '#check', sfx: false });
    s.box('Repository', { id: 'repo', x: 1540, y: 526, w: 360, h: 180, size: 50, font: 'body', icon: 'folder-git-2', color: 'blue', textColor: C.ink, at: '#check', sfx: false });
    s.arrow('agent', 'guard', { at: '#check', color: C.green, width: 5, sfx: false });
    s.arrow('guard', 'repo', { at: 'repository', color: C.green, width: 5, sfx: false });
    s.text('Local checks for proposed tool calls', { y: 766, size: 46, color: C.muted, at: '#check', sfx: false });
  },

  block(s) {
    stage(s, 'Force push blocked');
    terminal(s, [
      { cmd: 'git push --force origin main', at: '#command' },
      { out: '[no-force-push]', at: '#deny', color: C.red },
      { out: "Force push to 'main' is blocked", at: '#reason', color: C.ink },
    ], '#command');
    s.text('Push to a feature branch instead.', { y: 782, size: 48, color: C.green, at: '#reason', sfx: false });
    s.sfx('error', '#deny', { gain: 0.16 });
  },

  recover(s) {
    stage(s, 'Safe next steps');
    terminal(s, [{ cmd: 'git diff --stat', at: '#inspect' }], '#inspect', '#push');
    terminal(s, [{ cmd: 'git push origin feature/demo', at: '#push' }], '#push');
    s.text('No blocking findings', { y: 782, size: 48, color: C.green, at: '#allow', sfx: false });
    s.sfx('ding', '#allow', { gain: 0.12 });
  },

  policy(s) {
    stage(s, 'Clear policy feedback');
    s.box('ERROR → block', { x: 560, y: 450, w: 620, h: 160, size: 52, font: 'body', color: 'red', textColor: C.ink, at: '#errors', sfx: false });
    s.box('WARNING → advice', { x: 1360, y: 450, w: 620, h: 160, size: 52, font: 'body', color: 'orange', textColor: C.ink, at: '#warnings', sfx: false });
    s.text('Configure the rules for your project', { y: 654, size: 50, color: C.ink, at: '#review', sfx: false });
    s.text('Keep code review and CI in your workflow', { y: 768, size: 44, color: C.muted, at: 'continuous integration', sfx: false });
  },

  install(s) {
    stage(s, 'Try it in your repo', 'SETUP EXAMPLE · CODEX');
    terminal(s, [
      { cmd: 'uv tool install agentlint', at: '#install' },
      { cmd: 'agentlint setup codex', at: '#connect' },
      { cmd: 'agentlint status', at: '#verify' },
    ], '#install', undefined, 'Setup commands · illustrated');
    s.text('github.com/mauhpr/agentlint', { id: 'repo-url', y: 782, size: 46, font: 'mono', color: C.green, at: '#link', sfx: false });
    s.annotate('repo-url', { type: 'underline', color: C.green, at: 'Claude Code', sfx: false });
  },
};
