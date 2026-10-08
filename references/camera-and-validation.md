# Motion and validation

V5's `shot_target` only eased into the first isolated shot. With two focus events
at 1 and 5 seconds, the target stayed at `(1,640,360)` at t=4.999 and jumped to
`(1.55,1000,400)` at t=5.0. Subsequent low-pass filtering could soften but not
remove the target discontinuity or mistaken movement rhythm.

V6 compiles semantic events into nonoverlapping quintic transitions. Each ramp
has zero first and second derivatives at its endpoints. It holds between
meaningful actions, coalesces densely spaced targets, folds a newly opened
dialog into its triggering click, and resets only on explicit reset/end.

The pose contains zoom and output-space translation. Fitting happens at the
target, before interpolation. Interpolating valid affine poses keeps the source
inside the viewport without frame-by-frame crop clamping. Subpixel Lanczos
sampling from the recovered renderer remains in use. Lock intervals are exact
holds; no pointer noise or scroll position feeds back into the camera.

The recorder's sync marker calibrates the raw video's pre-roll. Pointer events
use the browser's time origin plus monotonic performance time, with listeners
installed in every document and collected outside the page. Navigation cannot
erase the previous document's telemetry. The marker quantizes alignment to one
source frame; it does not establish subframe synchronization.

`validate_video.py` decodes every MP4 frame and checks the expected frame count.
It samples every camera transform, counts direction reversals inside ramps,
measures frame displacement/acceleration at all four corners, and verifies no
motion during locks. These are camera regression checks, not a universal
perceptual quality score. Compression, page animation and 25 fps capture cadence
can still produce artifacts. Review consecutive frames during each transition,
pointer clicks, rules scrolling and the final board state.

Keep raw footage and telemetry unchanged when tuning camera policy. A metadata
camera hint may be adjusted if documented; do not rewrite evidence to claim an
action happened. The first live run failed on the Close selector and remains a
failed run; the successful re-record is a distinct output directory.

V8 records required context rectangles, fits all necessary controls before
planning and balances the complete vertical composition. No per-frame clamp
is added. The validator projects each applicable rectangle through every
output transform, rejects clipping at the video-card boundary and reports
clearance and steady vertical center error. It does not infer changing source
DOM bounds between samples; inspect dynamic layouts or add new framing events.
The v8 BrainBloom delivery is a fresh actual-site recording with measured Leave
game, Rules and Undo bounds, including the navigation row omitted in v7.
