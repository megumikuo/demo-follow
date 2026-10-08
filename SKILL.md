---
name: demo-follow
description: Record real website walkthroughs with smooth zoom and pan, selectable cursor styles, click animations, adjustable pacing and framed backgrounds. Export MP4, WebM, poster and HTML. Use for browser demos, tutorials and style variants of an existing real capture.
---

# Demo Follow

Turn the user's intended website flow into a verified recording. Use the same
scripts from Codex or Claude Code; no model API or paid service is required.

1. Inspect the live page and build a JSON plan from observed selectors. Use
   [the BrainBloom example](examples/brainbloom-chess.json) and
   [the action reference](references/action-plan.md). Add assertions for the
   results that establish the requested flow. Keep fixture tests clearly labeled.
2. Set up the Python environment using [README.md](README.md). Run from this
   skill directory, or use absolute script and plan paths. Choose a fresh output
   directory for each recording.
3. Run `python scripts/record.py PLAN --out OUTPUT`. It records real Chromium
   video, actual pointer events, and synchronization pre-roll. Failed actions
   save diagnostics and stop; do not deliver a failed capture as the demo.
4. Run `python scripts/render.py OUTPUT/raw.webm OUTPUT/events.json --out-dir OUTPUT`.
   Keep meaningful framing stable across related clicks. Use `camera_selector`
   for a board or panel and `camera_after` for a region revealed by an action.
   Use a larger context shot for dialogs; lock the camera during scrolling.
   Add `camera_context_selectors` for necessary full controls and navigation.
   Inspect actual source bounds before recording: preserve complete outlines,
   shadows and a safe margin. Center the primary region horizontally and the
   full working composition vertically so the screen is not top-heavy. Reduce
   zoom to fit context rather than crop buttons; review entry and exit ramps.
   Choose `--preset studio`, `playful`, `punchy` or `classic` from the requested
   tone. Use cursor, click, color, size, speed and framing overrides in README.
   For an undecided user, deliver visibly different variants of one real capture.
   Use `--speed-segments` for deliberate tutorial pacing; all region times are
   source times. Keep reading pauses and meaningful results long enough to see.
   Copy the original `events.json` into each render's output directory so its
   assertions and validation stay attached. Reuse raw footage when restyling.
5. Run `python scripts/make_embed.py --out OUTPUT/embed.html` and
   `python scripts/validate_video.py OUTPUT`. Inspect the contact sheet and
   consecutive frames around transitions, scrolling and the final result.
   Report capture fps/resolution separately from output fps/resolution.
6. Return the MP4, WebM, poster, embed and validation report. Keep source video
   and events for correction. Publish or upload only to the destination the
   user authorized; creating a video does not authorize public repository creation.

## Camera invariants

Read [camera-and-validation.md](references/camera-and-validation.md) before
changing motion. Camera poses come from semantic actions, not pointer noise.
The camera holds between actions and releases only at explicit reset/end.
Adjacent ramps are continuous, and scrolling locks are exactly stationary.
Protected compositions stay balanced through the final hold; use an explicit
reset when the requested story needs a full-viewport ending.
Never integer-round crop rectangles. Keep video time and pointer time aligned.

## Boundaries

Do not manufacture a screen when the real site is unavailable. Report the
blocker or offer a clearly labeled local test. Use public or explicitly
authorized flows; keep accounts, payments and external communications within
the user's specified scope. The recorder starts a clean temporary browser
context and does not import the user's logged-in profile.

This version captures viewport-sized video. `capture_scale` controls browser
DPR and screenshot resolution; it does not promise a 2× raw video. The default
60 fps export smooths camera motion over the measured source cadence.

Skill compatibility is based on the common `SKILL.md` format. The installer
supports both tools; successful folder installation does not prove an
independent Claude Code run, which must be reported separately when tested.
