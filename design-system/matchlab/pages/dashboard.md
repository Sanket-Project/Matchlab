# MatchLab dashboard — Astryx adaptation

User-selected design system: https://github.com/meta/astryx

The dashboard uses unmodified published CSS from @astryxdesign/theme-butter,
@astryxdesign/theme-neutral and @astryxdesign/theme-chocolate, pinned to 0.7.16.
These are combined in web/astryx.css. Native HTML components in dash.js use a
semantic-token adapter in dash.css; the application does not use Astryx React
components or require a React build. The older /lab page is unchanged.

Butter is the default: #fdfbe4 body, #f0df72 yellow hero, #225bff accent,
#1d1c11 primary text, #605f52 secondary text, white cards. Use Outfit for
headings and body (Sarina marketing display type is intentionally omitted in
this data dashboard). Neutral uses Figtree; Chocolate uses Fraunces headings
and Albert Sans body. Fonts are served locally, with system fallbacks.

Theme selector lives under Settings > Appearance, not in the header. Choices: Butter, Neutral, Chocolate. Persist under
matchlab-astryx-theme. Light mode is explicit. Tokens provide semantic
surfaces, accents, error/success colors, borders, typography and radii.
Chocolate secondary text is darkened with a local token override for readable
small data labels. The MIT and font OFL notices are retained in web/licenses.

Keep visible focus rings, native buttons, labelled search and theme controls,
pressed-state sport filters, 44px primary touch controls and reduced-motion
support. Summary counts use the full schedule; section counts reflect search
and sport filters. No decorative animation or external runtime assets.

Preserve model/source attribution and unavailable states. Never invent
confidence intervals, forecasts, or accuracy claims. UI checks use cached
fixture data; they do not validate prediction accuracy.
