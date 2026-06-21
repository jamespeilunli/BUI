# Upstream Sync Notes

This file tracks review and porting status for changes from the original
BLine-GUI repository. Update it every time upstream changes are reviewed,
ported, skipped, or otherwise considered.

## Current Checkpoint

- Original upstream repo: `edanliahovetsky/BLine-GUI`
- Last upstream commit considered: `1192ca2` (`upstream/main`, "Compress cone demo GIF")
- Future upstream comparisons should start after `1192ca2`.

## Sync Policy

- Do not merge `upstream/main` wholesale into BUI without careful review.
- Upstream is still the legacy GUI line and can overwrite or delete BUI timeline redesign files, redesign docs, tests, and BUI packaging/branding.
- Prefer targeted ports of functional fixes that still apply to BUI.
- Preserve BUI timeline redesign behavior and local branding unless the user explicitly asks otherwise.

## Review Through `1192ca2`

Necessary functional upstream fixes through `1192ca2` were reviewed:

- `3a5a2ce` ("Fix ranged constraint overlap corruption") was ported/adapted.
  - Ranged constraint remapping no longer expands disjoint ranges after deletes or type changes.
  - Legacy/corrupted overlapping ranged constraints are repaired during path deserialization.
- `26fe355` ("Fix lingering ranged constraint ghosting, bump to v0.5.0-beta.7 !release") was ported/adapted.
  - Sidebar segment-bar rebuilds now clean up dynamic widgets and stale label filters.
- `b4c194e` ("Fix simulation endpoint time blow-up") was tested against BUI.
  - The upstream regression already passed in BUI, so no production simulation change was needed.

The remaining upstream-only commits at this checkpoint were release, docs,
media, or legacy-branding changes and were intentionally not ported.
