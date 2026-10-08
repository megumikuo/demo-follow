# Action plans

The top-level object has `url` (a real site) or `html_file` (explicit local test),
`viewport` with even width/height, `capture_scale` for DPR, `settle_ms`,
`intro_ms`, `tail_ms`, and `actions`. Paths are resolved relative to the plan.
Keep `tail_ms` at least 1200 so the final camera release can finish.

Each action can have a human-readable `label`, `after_ms`, and `assert`.
Selectors use Playwright syntax. A selector must resolve to exactly one visible
element; `selectors` is an ordered fallback list. If two Close buttons exist,
scope to the header or deliberately select the first matching button. Avoid
coordinates and guessed selectors. Hidden/offscreen targets fail unless an
explicit `allow_scroll: true` is supplied.

| Type | Fields and behavior |
|---|---|
| `wait` | `ms`; holds the page |
| `click` | `selector` or `selectors`; real mouse movement and click |
| `hover` | same targeting; moves pointer without clicking |
| `fill` | selector and `text`; locks camera during text entry |
| `scroll` | scroll-container selector, `dy`, `scroll_ms`; paced real wheel input with fixed framing |
| `key` | `key`; only Escape or explicit `shot: reset` resets camera |
| `drag` | `from_selector`/`to_selector` or fallback plural fields; `drag_ms`, optional `zoom` |

For click/hover/fill, `move_ms` defaults to 650 and `pre_ms` to 300. Pointer
movement is paced in the actual browser and recorded as pointer telemetry.

For semantic framing, set `camera_selector` to the containing board/panel,
`shot` to `context` or `focus`, and optional `zoom` (clamped to a maximum of 2
and further limited to fit the requested region). Reuse the same board region
for a select-and-move pair so the camera doesn't chase two squares.
Set `camera_after: true` when the region becomes visible after clicking, such
as a board revealed by closing Rules. Its transition starts at the click, with
no anticipatory crop of the disappearing panel. A newly opened native dialog
automatically replaces the triggering button's brief focus shot.

Use `camera_context_selectors` (an array of unique visible selectors) for full
controls that must stay in the shot. `safe_margin` defaults to 12 viewport px.
These controls are measured before the action, or after it when `camera_after`
is true, and saved as `context_bounds` with the sampling time. Missing/clipped
required controls fail capture. The primary stays horizontally centered;
primary plus required controls form the vertically balanced composition.
Do not omit navigation merely to force a larger zoom. Near-source-edge controls
may limit the requested margin; record a better source layout when that matters.

Assertions fail the recording, save diagnostics and prevent rendering:

```json
{"assert":{"selector":"button[aria-label='e4, White pawn']","state":"visible"}}
```

`state` accepts Playwright's visible/hidden/attached/detached states. `text`
asserts contained text. `scroll_min` checks a scroll container's actual
`scrollTop`. Assertions and action screenshots are evidence of results, not
just evidence that a click command ran.

Use fresh output paths. `events.json.status` must be `complete` and include a
verified `video_offset`; the renderer rejects older unsynchronized metadata.
