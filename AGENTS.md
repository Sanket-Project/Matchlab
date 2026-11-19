# MatchLab workspace guidance

Use Meta's Astryx skill for every UI and UX change in this workspace, including
changes to the existing dashboard and legacy lab. Read the installed
`astryx/SKILL.md` or the upstream copy at
`artifacts/astryx-reference/plugins/astryx/skills/astryx/SKILL.md`.
Start with Astryx's CLI guidance for the affected pattern and read
`design-system/matchlab/pages/dashboard.md` for the local implementation.

MatchLab's current frontend uses native HTML with the Astryx 0.7.16 themes
and semantic tokens in `web/astryx.css` and `web/dash.css`. Extend those
patterns for existing pages. Check responsive layout, keyboard operation,
visible focus, and feed states affected by the change.
