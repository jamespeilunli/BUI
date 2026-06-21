# Path Editing Redesign Nice-to-Haves

This document holds deferred enhancements and optional follow-up work for the redesign.

These items are intentionally kept out of [tasks.md](tasks.md) so the implementation plan stays focused on the smallest useful release.

## Deferred UX Features

- alternate distance/progress timeline views layered on top of the default time axis
- semantic trigger categories or multiple trigger lane families
- multi-selection and batch edits
- minimap or overview strip for dense projects
- advanced keyboard workflow beyond core delete and focus actions
- richer motion and visual polish

## Wontfix For Current Rewrite Wave

- split constraint spans
- merge adjacent compatible spans
- duplicate constraint spans
- duplicate event triggers

These are not required for current parity work. Revisit only after path structure authoring, structure reordering, flat path constraints, and timeline delete parity are complete.

## Deferred Constraint Polish

- more advanced snapping rules if the minimal version is not sufficient
- more advanced combined-row lane management if simple automatic stacking is not sufficient

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
