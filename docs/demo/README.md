# AgentLint demo video

The [53-second video](../media/agentlint-demo.mp4) introduces AgentLint as local
guardrails for coding agents, explains the risk of credential exposure and
destructive commands, then shows one everyday coding workflow. A proposed
credential write is blocked, the agent uses an environment variable instead,
and the corrected write and proposed test command have no blocking findings.
The closing feature summary covers local checks, configurable packs, CI support,
and supported agents, followed by a short Codex setup example.
The [silent README preview](../media/agentlint-demo-preview.gif) follows the
same complete story. A [poster](../media/agentlint-demo-poster.png) introduces
the product for sharing.

This is an illustrated hook demonstration, not a live editor or terminal
recording. The credential fixture is a known, non-functional synthetic marker.
The detector evaluates its assignment only in memory; the video masks the value
and the saved input replaces the entire assignment with a redaction marker.
The captured finding and denial are unmodified. Regenerate the original
synthetic input with the capture script, rather than replaying the redacted JSON.

All proposed operations are evaluated as data. No displayed file write or shell
command is executed, and the video shows permission to run tests, not a passing
test result. The decisions use AgentLint 2.9.1's `universal` and `quality` core
packs under standard severity. No opt-in pack or stricter policy is needed for
this example. No workspace policy, hook trust, or user settings are changed.
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
includes burned-in captions and quiet background music. ExplainRoo is credited
in these notes; the video has no watermark.
No paid image service or API key is used.

The [visual direction](explainroo/DESIGN.md) uses Geist for labels and body
copy, Instrument Serif for editorial accents, and Geist Mono for commands.
Font files and their licenses are bundled under `explainroo/assets/fonts/`.
Captions are drawn by the scenes; the renderer's default captions and
watermark are disabled. There are no chapter labels, feature badges, or
on-screen example disclaimers; provenance remains in these notes.

## Reproduce

From the AgentLint repository, capture decisions without executing the proposed
operations. The output stores a redaction marker instead of the fixture value:

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
node /tmp/explainroo-agentlint/bin/explainroo.js still docs/demo/explainroo intro@end problem@end block@7 recover@4.6 recover@7.8 features@end install@end
node /tmp/explainroo-agentlint/bin/explainroo.js sheet docs/demo/explainroo --every 1
node /tmp/explainroo-agentlint/bin/explainroo.js render docs/demo/explainroo --workers 2
node /tmp/explainroo-agentlint/bin/explainroo.js verify docs/demo/explainroo
```

Inspect the generated stills and contact sheet before publishing. Export the
verified video, product poster, and a silent preview of the complete story:

```bash
cp docs/demo/explainroo/out/video.mp4 docs/media/agentlint-demo.mp4
cp docs/demo/explainroo/out/stills/intro@end.png docs/media/agentlint-demo-poster.png
ffmpeg -y -i docs/media/agentlint-demo.mp4 \
  -filter_complex '[0:v]fps=10,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle' \
  -loop 0 docs/media/agentlint-demo-preview.gif
```

Build files and intermediate renders are ignored; the final assets live in
`docs/media/`.

## Verification

The final MP4 is 53.23 seconds, 1920×1080 at 30 fps, with H.264 video and
AAC stereo audio. ExplainRoo found no layout errors, warnings, or hints at an 854-pixel player width,
no black segments or silence, and no final verification issues. Measured audio
is −14 LUFS with a −1.5 dBFS true peak; final-mix speech recognition is 100%.

The 54-frame contact sheet, additional reveal frames, and seven frames extracted
from the final MP4 were visually inspected. No clipped or overflowing text was
found in the reviewed frames. Explicit label-width limits supplement the
renderer's automated check.
