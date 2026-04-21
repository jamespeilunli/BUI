# Path Editing Redesign Nice-to-Haves

This document holds deferred enhancements and optional follow-up work for the redesign.

These items are intentionally kept out of [tasks.md](/home/jamesli/git_repos/BLine-GUI/tasks.md) so the implementation plan stays focused on the smallest useful release.

## Deferred UX Features

- playback-driven timeline behavior beyond a simple inspection playhead
- estimated-time overlays or alternate time-based timeline views
- semantic trigger categories or multiple trigger lane families
- multi-selection and batch edits
- minimap or overview strip for dense projects
- advanced keyboard workflow beyond core delete and focus actions
- richer motion and visual polish
- structure reordering from the timeline

## Deferred Constraint Features

- split constraint spans
- merge adjacent compatible spans
- duplicate constraint spans
- more advanced snapping rules if the minimal version is not sufficient
- more advanced lane management if simple automatic stacking is not sufficient

## Deferred Timeline Polish

- zoom-to-selection
- zoom toward cursor
- more adaptive label density rules
- richer hover tooltips
- context menus beyond the minimal editing actions
- stronger dense-path readability refinements

## Deferred Cleanup Ideas

- retire more of the old sidebar structure UI once the timeline is proven
- fully remove the old constraint popout and compact segment-bar code paths
- consolidate reused timeline and sidebar helper logic if duplication appears during implementation

## Rule

Do not pull items from this document into active implementation unless the core workflow in `tasks.md` is already working and the added complexity is justified.
