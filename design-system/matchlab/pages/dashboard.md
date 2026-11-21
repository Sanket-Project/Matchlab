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

## World tab (#world)

Markets, AI briefing, model releases, AI news and sports headlines, in that
order. Reuses the Butter hero, `.panel`, `.chip`, `.tag` and `.note` patterns and
semantic tokens only; no hex colours. Price direction is shown with an arrow
and a +/- sign as well as colour, and the sparkline is an inline SVG with an
`aria-label` giving its start and end values. Filter chips are pressed-state
buttons with 44px targets that keep focus after filtering. Each panel has its
own loading, error (with Try again) and stale states. External links open in a
new tab with a visually hidden notice. Model dates are catalogue listing dates
("Newly listed"), never claimed as release dates. The AI briefing must cite
supplied items and states that AI can be wrong; it uses free OpenRouter models
only and is metered. See docs/superpowers/specs/2026-11-21-world-pulse-design.md.

Selects use `.select-wrap` (native control, token-drawn chevron) so keyboard,
touch and themes all work. Race pickers group Completed and Upcoming races.

## Motion & Micro-Animation Architecture

MatchLab implements a physically grounded, mathematically calibrated motion system designed around human perceptual thresholds:
- **Kinematic Easing Curves**:
  - `--ease-spring: cubic-bezier(0.34, 1.32, 0.64, 1)`: Damped harmonic spring ($\zeta \approx 0.82$, $\omega_n \approx 28\text{ rad/s}$) for tactile pop on chips, badges, and toggles.
  - `--ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1)`: High-velocity exponential decay touchdown for card elevation, view transitions, and probability bars.
  - `--ease-press: cubic-bezier(0.2, 0.8, 0.2, 1)`: Instantaneous mechanical actuation for button/card `:active` depressions.
- **Micro-Interactions**:
  - **Cards & Showcases**: Staggered waterfall cascade (`--motion-stagger-step: 28ms`, capped at 336ms), tactile lift ($\Delta y = -3.5\text{px}$), sub-pixel elevation shadows, thumbnail micro-scale ($1.08\times$), and diagonal arrow translation.
  - **Live Telemetry & Radar Ping**: Concentric double-harmonic ripple wave on `.tag.live` and `.live-pulse-dot` providing real-time match status without layout thrashing.
  - **Probability Meters & Forecasts**: Fluid width expansion via `--ease-out-expo` with specular algorithmic gradient sweep (`@keyframes bar-sweep`), accompanied by smooth numeric counter roll-ups.
  - **Financial Terminal & Charts**: SVG path stroke-dash progressive trace (`@keyframes chart-stroke-draw`) and area mountain fade-in.
  - **Strict Accessibility**: Zero motion latency override under `@media (prefers-reduced-motion: reduce)` guaranteeing safety for motion-sensitive users.

## Tennis: "Who wins and why" (#match/tennis-*)

Sits under the live score and above the win chance, on the local app and on the hosted copy. It shows the pick
and its chance (following the live score), each player's last 6 results as W/L badges with "won–lost · %", their
last 6 meetings as badges named by the winner (green when the pick won), then the reasons, each tagged For,
Against or Level. Every badge has a title and visually hidden text with the date, opponent and score. Built
server-side by `tennis_forecast.case()` from the model's own inputs, and saved with the locked forecast so the
hosted copy can show it. The hosted copy follows the score through `/api/tennis-live` (ESPN, free, cached 8 s)
every 10 s while live; the server recomputes the win chance from the saved serve-point model.

## Phones (≤760 px)

Nav, chips, search, ticker items, back links and table links are at least 44 px tall. Stat tiles sit two to a row
(a lone last tile spans the row). The Track record table becomes one stacked card per forecast with labelled
fields (`data-label`). Market range cards stack and the market stat tiles sit two to a row. Programmatic focus on
the page `h1` draws no outline. Checked at 375 px with Playwright: no horizontal scroll on any view.

## Extra feed panels (weather, OpenF1, AcesAPI)

`lazyPanel()` in dash.js renders a `.panel` from `state.extra` at once; on a miss it shows a loading state
(`aria-busy`), fetches once and swaps itself in by id, so live re-renders never refetch. "Weather at the start"
(cricket, tennis, F1) uses `.stats` tiles and a `.note` naming Open-Meteo and stating the model does not use it.
"Race weekend so far" (F1) lists sessions and puts each classification in a `details.more` with a `.scroll` table.
"Second view from AcesAPI" (tennis) spends credits only on a button press and says how many remain. All three are
hidden on the hosted copy. Each has an error state; weather has Try again.
