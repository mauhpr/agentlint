# AgentLint demo video

The [49-second video](../media/agentlint-demo.mp4) shows a proposed force push
to `main` being blocked, followed by safe example commands with no blocking
findings. It also explains advisory warnings and shows a Codex setup example.
The [silent README preview](../media/agentlint-demo-preview.gif) covers the
blocked action and safe next steps. A [poster](../media/agentlint-demo-poster.png)
is available for sharing.

This is an illustrated hook demonstration, not a live terminal recording.
Every displayed Git command is inspected as data and is never executed.
The block message and decisions come from AgentLint 2.9.1's built-in rules,
with `universal`, `quality`, and the opt-in `security` pack under standard
severity. No workspace policy, hook trust, or user settings are changed.
Follow the [Quickstart](../quickstart.md) for each agent's restart and trust
instructions; the video does not claim that the illustrated setup is a live
installation.

## Sources

- [Captured decisions](decisions.json), generated with [capture.py](capture.py).
- [Narration](explainroo/script.md), [scenes](explainroo/scenes.js), and
  [video settings](explainroo/video.json).
- [ExplainRoo](https://www.explainroo.com/), renderer revision
  `94da0fb4a1e51bf82d8868d59540767d1856f50e`.
- AgentLint source revision `a504dd9c7523651a50860d5a71ce406b236057ae`.

The voice uses local Kokoro; Whisper checks speech and timing. The video
includes burned-in captions, quiet background music, and ExplainRoo attribution.
No paid image service or API key is used.

## Reproduce

From the AgentLint repository, capture the decisions without running commands:

```bash
uv run python docs/demo/capture.py > docs/demo/decisions.json
```

Install the pinned renderer in a separate checkout:

```bash
git clone https://github.com/vincentsch/explainroo.git /tmp/explainroo-agentlint
git -C /tmp/explainroo-agentlint checkout --detach 94da0fb4a1e51bf82d8868d59540767d1856f50e
npm --prefix /tmp/explainroo-agentlint ci
```

On macOS, the renderer's ONNX Runtime 1.21.0 has a native shutdown crash.
Before generating speech, install the fixed runtime in that separate checkout:

```bash
npm --prefix /tmp/explainroo-agentlint pkg set overrides.onnxruntime-node=1.24.3
npm --prefix /tmp/explainroo-agentlint install
```

The upstream fix is documented in
[ONNX Runtime PR 26445](https://github.com/microsoft/onnxruntime/pull/26445).
This override belongs to the rendering tool, not AgentLint's dependencies.

Run the renderer from the AgentLint repository:

```bash
node /tmp/explainroo-agentlint/bin/explainroo.js doctor --fetch
node /tmp/explainroo-agentlint/bin/explainroo.js voice docs/demo/explainroo
node /tmp/explainroo-agentlint/bin/explainroo.js check docs/demo/explainroo --view-width 854
node /tmp/explainroo-agentlint/bin/explainroo.js still docs/demo/explainroo
node /tmp/explainroo-agentlint/bin/explainroo.js sheet docs/demo/explainroo
node /tmp/explainroo-agentlint/bin/explainroo.js render docs/demo/explainroo --workers 2
node /tmp/explainroo-agentlint/bin/explainroo.js verify docs/demo/explainroo
```

Inspect the generated stills and contact sheet before publishing. Export the
verified video, poster, and a silent preview of the two command scenes:

```bash
cp docs/demo/explainroo/out/video.mp4 docs/media/agentlint-demo.mp4
cp docs/demo/explainroo/out/stills/block@end.png docs/media/agentlint-demo-poster.png
ffmpeg -y -ss 9 -t 17 -i docs/media/agentlint-demo.mp4 \
  -filter_complex '[0:v]fps=10,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle' \
  -loop 0 docs/media/agentlint-demo-preview.gif
```

Build files and intermediate renders are ignored; the final assets live in
`docs/media/`.

## Verification

The final MP4 is 48.53 seconds, 1920×1080 at 30 fps, with H.264 video and
AAC stereo audio. ExplainRoo found no layout issues at an 854-pixel player width,
no black segments or silence, and no final verification issues. Measured audio
is −14 LUFS with a −1.5 dBFS true peak; final-mix speech recognition is 99.1%.
