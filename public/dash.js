"use strict";
// MatchLab dashboard. All text from feeds is inserted with textContent, never as HTML.
const view = document.getElementById("view");
const state = { token: "", schedule: null, filter: "all", timer: null, request: 0, players: {}, keyStatus: null, refreshing: false, aiBusy: null, aiTried: {}, aiError: {} };
const SPORTS = { cricket: "Cricket", tennis: "Tennis", f1: "Formula 1" };
state.search = "";
const THEMES = { butter: "Butter", neutral: "Neutral", chocolate: "Chocolate" };
state.theme = "butter";
try {
  const saved = localStorage.getItem("matchlab-astryx-theme");
  if (Object.hasOwn(THEMES, saved)) state.theme = saved;
} catch (_) { /* Storage may be disabled. */ }
document.documentElement.dataset.astryxTheme = state.theme;

function changeTheme(theme) {
  if (!Object.hasOwn(THEMES, theme)) return;
  state.theme = theme;
  document.documentElement.dataset.astryxTheme = theme;
  try { localStorage.setItem("matchlab-astryx-theme", theme); } catch (_) { /* Keep this session's palette. */ }
}

function h(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === false || value == null) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}
const show = (...nodes) => view.replaceChildren(...nodes.flat().filter((n) => n != null && n !== false));
const pct = (p) => `${Math.round(p * 100)}%`;
const time = (iso) => iso ? new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "";
const day = (iso) => iso ? new Date(iso).toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" }) : "";

async function api(path, body) {
  const options = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json", "X-MatchLab-Token": state.token }, body: JSON.stringify(body),
  };
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({ error: "The local server sent an unreadable reply." }));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function showBudgets(budget) {
  const box = document.getElementById("budgets");
  box.replaceChildren();
  if (!budget) return;
  for (const [key, label] of [["cricketdata", "CricketData"], ["openrouter", "AI checks"]]) {
    const item = budget[key];
    if (!item) continue;
    box.append(h("span", { class: `budget num${item.remaining <= 15 ? " low" : ""}`, title: `${item.used} of ${item.limit} requests used today. Resets at midnight UTC.` },
      `${label}: ${item.remaining} of ${item.limit} left`));
  }
}

function countdown(iso) {
  const minutes = Math.round((new Date(iso) - Date.now()) / 60000);
  if (minutes < -1) return "start time passed";
  if (minutes <= 1) return "starting now";
  if (minutes < 60) return `starts in ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `starts in ${hours} h ${minutes % 60} min`;
}

function modelled(match) {
  if (match.sport === "tennis") return !/^(tbd|bye)$/i.test(match.team || "tbd") && !/^(tbd|bye)$/i.test(match.opponent || "tbd");
  if (match.sport !== "cricket") return null;
  const kind = `${match.detail || ""} ${match.espn_class || ""}`.toLowerCase();
  if (/test|first-class|first class|\bfc\b/.test(kind)) return false;
  return /t20|twenty20|t10|odi|list a|one-day|one day/.test(`${kind} ${(match.tournament || "").toLowerCase()}`);
}

function card(match) {
  const live = match.state === "in";
  const ready = modelled(match);
  const tagText = live ? "Live" : match.state === "post" ? "Finished" : time(match.start);
  const badge = match.sport === "f1" ? h("span", { class: "tag ok" }, "Explore F1")
    : ready ? h("span", { class: "tag ok" }, "Forecast ready")
      : h("span", { class: "tag off" }, match.sport === "tennis" ? "Players not decided" : "Not modelled yet");
  return h("button", { class: `card match-card${live ? " is-live" : ""}`, type: "button", onclick: () => { location.hash = `match/${encodeURIComponent(match.id)}`; } },
    h("div", { class: "meta" }, h("span", {}, `${SPORTS[match.sport]}${match.detail ? " · " + match.detail : ""}`),
      h("span", { class: `tag${live ? " live" : ""}` }, tagText)),
    h("div", { class: "teams" },
      h("span", {}, h("span", { class: "team-name" }, match.team), h("b", {}, match.team_score || "")),
      match.opponent ? h("span", {}, h("span", { class: "team-name" }, match.opponent), h("b", {}, match.opponent_score || "")) : null),
    h("div", { class: "tour" }, [match.tournament, match.venue].filter(Boolean).join(" · ")),
    h("div", { class: "foot2" }, h("span", {}, live || match.state === "post" ? (match.status || "") : `${day(match.start)} · ${countdown(match.start)}`), badge),
    h("div", { class: "card-action" }, "Explore match", h("span", { "aria-hidden": "true" }, "↗")));
}

function renderMatches() {
  const data = state.schedule;
  const all = Object.entries((data && data.sports) || {}).flatMap(([sport, rows]) => SPORTS[sport] ? rows.map((row) => ({ ...row, sport })) : []);
  const shown = all.filter((m) => (state.filter === "all" || m.sport === state.filter) &&
    [m.team, m.opponent, m.tournament, m.venue].filter(Boolean).join(" ").toLowerCase().includes(state.search.toLowerCase().trim()));
  const rank = (m) => (m.sport !== "f1" && !modelled(m) ? 1 : 0);
  const by = (s) => shown.filter((m) => m.state === s).sort((a, b) => rank(a) - rank(b) || (a.start || "").localeCompare(b.start || ""));
  const live = by("in"), soon = by("pre"), done = by("post");
  const filters = h("div", { class: "row", role: "group", "aria-label": "Sport" },
    ["all", ...Object.keys(SPORTS)].map((key) => h("button", { class: "chip", type: "button", "aria-pressed": String(state.filter === key),
      onclick: () => { state.filter = key; renderMatches(); } }, key === "all" ? "All sports" : SPORTS[key])));
  const refresh = h("button", { class: "btn", type: "button", disabled: state.refreshing, onclick: refreshSchedule },
    state.refreshing ? "Checking..." : "Refresh");
  const section = (title, rows, empty) => h("section", { class: "section" },
    h("h2", {}, title, h("span", { class: "count" }, rows.length ? `${rows.length}` : "")),
    rows.length ? h("div", { class: "cards" }, rows.map(card)) : h("p", { class: "note" }, empty));
  const search = h("input", { type: "search", class: "match-search", value: state.search, placeholder: "Search teams, leagues or venues", "aria-label": "Search teams, leagues or venues",
    oninput: (event) => { const position = event.target.selectionStart; state.search = event.target.value; renderMatches(); const field = view.querySelector(".match-search"); field.focus(); if (position != null) field.setSelectionRange(position, position); } });
  show(
    h("section", { class: "matchday-hero", "aria-label": "Matchday overview" },
      h("div", { class: "hero-copy" }, h("p", { class: "eyebrow" }, "THE MATCHDAY EDIT"), h("h1", {}, "Every match.", h("br"), h("span", {}, "A clearer picture.")),
        h("p", {}, "Your daily view of live scores, upcoming fixtures and the numbers behind the game."),
        h("span", { class: "hero-date" }, new Date().toLocaleDateString([], { weekday: "long", day: "numeric", month: "long" }))),
      h("div", { class: "hero-stats" }, [["Live now", "in"], ["Coming up", "pre"], ["Finished", "post"]].map(([label, status]) =>
        h("div", {}, h("span", {}, label), h("strong", { class: "num" }, data ? all.filter((m) => m.state === status).length : "—"))))),
    h("div", { class: "head matches-heading" }, h("div", {}, h("p", { class: "eyebrow" }, "YOUR MATCH CENTRE"), h("h2", {}, "On the schedule"),
      h("p", { class: "sub" }, data && data.last_updated ? `Last checked ${time(data.last_updated)} · Open a match to explore its forecast.` : "Loading fixtures…")), refresh),
    h("div", { class: "filter-bar" }, filters, search),
    data && data.refresh_error ? h("p", { class: "note error" }, data.refresh_error) : null,
    data && (data.sources || []).filter((s) => s.error).map((s) => h("p", { class: "note warn" }, `${s.name}: ${s.error}`)),
    section("Live now", live, state.search ? "No live matches match your search. Try another team or league." : "A quiet moment. No matches are in play for this sport right now."),
    section("Coming up", soon, state.search ? "No upcoming matches match your search." : "No upcoming fixtures for this selection in the next day."),
    done.length ? h("details", { class: "section more" }, h("summary", {}, `Finished today (${done.length})`), h("div", { class: "cards", style: "margin-top:10px" }, done.map(card))) : null);
}

async function refreshSchedule() {
  if (state.refreshing) return;
  state.refreshing = true;
  if (!location.hash || location.hash === "#matches") renderMatches();
  try {
    state.schedule = await api("/api/refresh-today-matches", {});
    showBudgets(state.schedule.budget);
  } catch (error) {
    if (state.schedule) state.schedule.refresh_error = error.message;
  }
  state.refreshing = false;
  if (!location.hash || location.hash === "#matches") renderMatches();
}

// ---- match page -----------------------------------------------------------------------
function findMatch(id) {
  for (const [sport, rows] of Object.entries((state.schedule && state.schedule.sports) || {})) {
    const match = rows.find((row) => row.id === id);
    if (match) return { ...match, sport };
  }
  return null;
}

function stat(label, value, detail) {
  return h("div", { class: "stat" }, h("div", { class: "k" }, label),
    h("div", { class: "v" }, value), detail ? h("div", { class: "s" }, detail) : null);
}

function inningsStat(label, innings, detail) {
  return stat(label, `${innings.mean} runs`, detail || `80% range ${innings.low}–${innings.high} · ${innings.wickets ?? innings.wickets_lost} wickets`);
}

function playerPicker(rows, key, display) {
  if (!rows.length) return h("p", { class: "sub" }, "Named player projections are waiting for a usable lineup.");
  const names = rows.map((row) => row.name);
  const selected = names.includes(state.players[key]) ? state.players[key] : names[0];
  const metrics = h("div", { class: "player-forecast" });
  const choose = (name) => {
    state.players[key] = name;
    metrics.replaceChildren(...display(rows[names.indexOf(name)]));
  };
  const select = h("select", { onchange: (event) => choose(event.target.value) },
    names.map((name) => h("option", { value: name, selected: name === selected }, name)));
  choose(selected);
  return h("div", { class: "players", "data-key": key }, h("label", { class: "player-select" }, h("span", {}, "Player"), select), metrics);
}

function teamPanel(team, pre, index, id) {
  const order = pre.toss?.bats_first;
  const chasing = order != null && order !== index && team.chase;
  const innings = chasing ? team.chase : team.first_innings;
  const heading = chasing ? "Projected chase finish" : order == null ? "Projected total if batting first" : "Projected first innings";
  const roster = team.batters.filter((row) => !/^Player \d+$/.test(row.name)).map((bat) =>
    ({ name: bat.name, bat, bowl: team.bowlers.find((row) => row.name === bat.name) }));
  return h("article", { class: "panel team" },
    h("h3", {}, team.name),
    h("div", { class: "stats forecast-stats" },
      inningsStat(heading, innings),
      stat("Expected wickets taken", team.wickets_taken.toFixed(1)),
      order == null && team.chase ? inningsStat("Projected total if chasing", team.chase) : null),
    h("details", { class: "more", "data-key": `score-${index}` }, h("summary", {}, "Why this total"),
      h("ul", { class: "why" }, (team.reasons || []).map((reason) => h("li", {}, reason)),
        chasing || order == null && team.chase ? h("li", {}, "In each simulation, the chase ends when the target is reached, the overs run out, or the side is bowled out.") : null)),
    h("p", { class: "sub lineup" }, team.lineup_source || "Lineup details were unavailable when this forecast was saved."),
    playerPicker(roster, `${id}-pre-${index}`, ({ bat, bowl }) => [
      h("div", { class: "stats forecast-stats" }, stat("Expected runs", bat.runs.toFixed(1)),
        stat("Expected wickets", bowl ? bowl.wickets.toFixed(2) : "—")),
      (bat.reasons || bowl?.reasons) ? h("details", { class: "more", "data-key": `pre-player-${index}` },
        h("summary", {}, "Why this player projection"),
        h("ul", { class: "why" }, [...(bat.reasons || []), ...(bowl?.reasons || [])].map((reason) => h("li", {}, reason)))) : null,
    ].filter(Boolean)));
}

function matchScoreboard(board) {
  if (!board) return null;
  const title = board.state === "post" ? "Final score" : "Current score";
  const status = board.state === "in" ? "Live" : board.state === "post" ? "Finished" : "Upcoming";
  const winner = board.teams.find((team) => team.winner);
  return h("section", { class: "scoreboard", "aria-label": title },
    h("div", { class: "section-head" }, h("h2", {}, title), h("span", { class: `tag${board.state === 'in' ? ' live' : ''}` }, status)),
    h("div", { class: "score-sides" }, board.teams.map((team) => h("div", { class: "score-side" },
      h("span", {}, team.name), h("strong", { class: "num" }, team.score || (board.state === "pre" ? "Yet to start" : "—"))))),
    h("p", { class: "score-status" }, [winner && !board.status?.includes(winner.name) ? `${winner.name} won` : "", board.status, board.stale ? "Latest feed check failed" : "",
      board.checked_at ? `${board.source} checked at ${time(board.checked_at)}` : board.source].filter(Boolean).join(" · ")));
}

function winOutlook(teams, win, reasons) {
  const favourite = win[0] >= win[1] ? 0 : 1;
  const even = pct(win[0]) === pct(win[1]);
  return h("div", { class: "outlook" },
    h("div", { class: "outlook-head" }, h("h3", {}, even ? "Too close to call" : `${teams[favourite].name} favoured to win`),
      h("span", { class: "tag" }, "Model forecast")),
    h("div", { class: "probabilities" }, teams.map((team, i) => h("div", {},
      h("strong", { class: "num" }, pct(win[i])), h("span", {}, team.name)))),
    h("div", { class: "probability-bar", "aria-hidden": "true" }, h("div", { style: `width:${win[0] * 100}%` })),
    reasons.length ? h("ul", { class: "why" }, reasons.map((reason) => h("li", {}, reason))) : null);
}

function preMatchPanel(f, id) {
  const recorded = f.saved?.pre;
  const pre = recorded?.saved_before_start ? recorded : null;
  const start = f.fixture.start;
  const scheduleTime = Number.isFinite(Date.parse(start)) ? new Date(Date.parse(start) - 15 * 60000).toISOString() : "";
  const timeToStart = Date.parse(start) - Date.now();
  const beforeStart = f.scoreboard.state === "pre" && timeToStart > 0;
  const early = beforeStart && timeToStart > 15 * 60000;
  const displayed = pre || (beforeStart ? f : null);
  const caption = pre?.at_checkpoint ? `Saved at ${time(pre.saved_at)} and locked for this match.`
    : displayed && early ? `The pre-match forecast locks around ${time(scheduleTime)}.`
      : pre ? `Last forecast saved before play at ${time(pre.saved_at)}. The 15-minute checkpoint was missed.`
        : "The app has no saved forecast from before this match started.";
  return h("section", { class: "forecast-section", "aria-labelledby": "pre-title" },
    h("div", { class: "section-head" }, h("h2", { id: "pre-title" }, "Pre-match forecast"),
      h("span", { class: "tag" }, pre?.at_checkpoint ? "T−15 snapshot" : displayed && early ? "Early estimate" : pre ? "Saved forecast" : "Unavailable")),
    h("p", { class: "sub" }, caption),
    displayed ? h("div", { class: "panel forecast-overview" },
      winOutlook(displayed.teams, displayed.teams.map((team) => team.win),
        (displayed.teams[displayed.teams[1].win > displayed.teams[0].win ? 1 : 0].reasons || []).slice(0, 3)),
      displayed.toss ? h("p", { class: "sub" }, displayed.toss.text) :
        h("p", { class: "sub" }, displayed.toss === null ? "Toss pending at forecast time. The model weighs both batting orders equally." : ""),
      displayed.venue?.notes?.length ? h("details", { class: "more", "data-key": "pre-venue" }, h("summary", {}, "Ground history"),
        h("ul", { class: "why" }, displayed.venue.notes.map((reason) => h("li", {}, reason)))) : null) : null,
    displayed ? h("div", { class: "grid2" }, displayed.teams.map((team, i) => teamPanel(team, displayed, i, id))) : null);
}

function analysisPanel(f) {
  const a = f.analysis, bt = a.backtest;
  return h("details", { class: "panel more", "data-key": "cricket-model" },
    h("summary", {}, "Model and track record"),
    h("p", { class: "sub" }, a.data),
    h("p", { class: "sub" }, `${a.machine_learning.name}. ${a.machine_learning.detail}`),
    bt ? h("p", { class: "note", style: "margin-top:12px" },
      `Tested on ${bt.matches} matches the model had never seen (${bt.window[0]} to ${bt.window[1]}): it picked the winner ${pct((bt.blend ? bt.blend.blend : bt.winner).accuracy)} of the time${bt.blend ? ` (simulation alone: ${pct(bt.winner.accuracy)})` : ""}, ` +
      `its first-innings score was off by ${Math.round(bt.first_innings_mae.simulator)} runs on average (venue average: ${Math.round(bt.first_innings_mae.venue_average)}), ` +
      `its top-scorer pick was right ${pct(bt.top_scorer.simulator_pick)} of the time and its top wicket-taker pick ${pct(bt.top_wicket_taker.simulator_pick)}. ` +
      `Player picks are the least reliable numbers here.`) : null);
}

function livePanel(f, id) {
  const live = f.live;
  const board = f.scoreboard;
  const baseline = f.saved?.pre?.saved_before_start ? f.saved.pre : null;
  const timeline = f.saved?.timeline || [];
  const title = board.state === "post" ? "Live analysis recap" : "Live analysis";
  const heading = h("div", { class: "section-head" }, h("h2", {}, title),
    h("span", { class: `tag${board.state === 'in' ? ' live' : ''}` }, board.state === "in" ? "In play" : board.state === "post" ? "Finished" : "Awaiting play"));
  const history = timeline.length ? h("details", { class: "more", "data-key": "live-history" },
    h("summary", {}, `Over-by-over analysis (${timeline.length} ${timeline.length === 1 ? "update" : "updates"})`),
    h("p", { class: "sub" }, "Updates are captured while this match is open. The feed can skip score checkpoints."),
    h("ul", { class: "timeline" }, timeline.slice().reverse().map((entry) =>
      h("li", {}, h("time", { datetime: entry.at }, time(entry.at)), h("span", {},
        h("strong", {}, `Innings ${entry.position[0]} · ${entry.batting} ${entry.score}`),
        entry.projected == null ? null : ` · Projected ${entry.projected}`,
        entry.win_by_team ? ` · ${f.teams.map((team, i) => `${team.name} ${pct(entry.win_by_team[i])}`).join(' / ')}`
          : ` · ${pct(entry.win)} to win`,
        h("span", { class: "sub timeline-note" }, entry.note)))))) : null;
  if (!live) {
    const message = board.state === "pre" ? "The live model starts once the first innings score is available."
      : board.state === "post" ? (timeline.length ? "" : "No live forecast updates were captured for this match.")
        : f.live_unavailable || "Waiting for a current score with runs, wickets and overs.";
    return h("section", { class: "panel live-analysis" }, heading, message ? h("p", { class: "sub" }, message) : null, history);
  }

  const current = live.batting_index;
  const other = f.teams[1 - current].name;
  const difference = baseline ? Math.round(100 * (live.win[current] - baseline.teams[current].win)) : null;
  const reasons = [...live.changes];
  if (difference != null) {
    reasons.push(`${live.batting} ${difference === 0 ? 'are level with their saved pre-match win chance.' : `moved ${Math.abs(difference)} percentage points ${difference > 0 ? 'above' : 'below'} their saved pre-match win chance.`}`);
  }
  const scenarioCard = (row) => {
    const chances = f.teams.map((team, i) => h("div", {}, h("dt", {}, team.name), h("dd", { class: "num" }, pct(row.win[i]))));
    return h("div", { class: "scenario" }, h("h4", {}, row.label), h("dl", {}, chances));
  };
  const scenario = live.scenarios?.length ? h("div", { class: "live-scenarios" },
    h("h3", {}, "What could change the odds?"),
    h("p", { class: "sub" }, `Win chances if ${live.batting} reach these scores or lose these wickets by ${live.scenario_over} overs. Simulations that finish earlier use the final score.`),
    h("div", { class: "scenario-grid" }, live.scenarios.map(scenarioCard))) : null;
  const players = (live.players || []).filter((row) => !/^Player \d+$/.test(row.name));
  const picker = (team, i) => playerPicker(players.filter((row) => row.team === team.name), `${id}-live-${i}`, (row) => [
    h("div", { class: "stats forecast-stats" },
      row.final_runs == null ? stat("Final runs", row.runs ?? "—") : stat("Projected runs", row.final_runs.toFixed(1), `${row.runs} so far`),
      row.final_wickets == null ? stat("Final wickets", row.wickets ?? "—") : stat("Projected wickets", row.final_wickets.toFixed(2), `${row.wickets} so far`)),
  ]);
  return h("section", { class: "panel live-analysis" }, heading,
    h("p", { class: "sub" }, `${live.batting} · ${live.score}${live.target ? ` · Target ${live.target}` : ''}`),
    winOutlook(f.teams, live.win, reasons),
    h("div", { class: "stats forecast-stats" },
      inningsStat(`${live.batting} projected finish`, live.projected),
      live.chase ? inningsStat(`${other} projected chase`, live.chase) :
        live.first_innings ? inningsStat(`${other} first innings`, live.first_innings, `Actual score · ${live.first_innings.wickets} wickets`) : null),
    scenario,
    h("div", { class: "live-players" }, h("h3", {}, "Live player projections"),
      players.length ? h("div", { class: "grid2" }, f.teams.map((team, i) => h("div", {}, h("h4", {}, team.name), picker(team, i)))) :
        h("p", { class: "sub" }, "Waiting for a player scorecard that matches the innings score.")),
    history);
}

function resultPanel(result) {
  const lines = [];
  if (result.winner_pick) lines.push(h("li", { class: result.winner_pick.correct ? "good" : "bad" },
    `Winner: picked ${result.winner_pick.pick} at ${pct(result.winner_pick.probability)}. ${result.winner} won. ${result.winner_pick.correct ? "Correct." : "Wrong."}`));
  if (result.first_innings) lines.push(h("li", { class: result.first_innings.in_range ? "good" : "bad" },
    `First innings: ${result.first_innings.team} made ${result.first_innings.actual}; forecast ${result.first_innings.predicted} (range ${result.first_innings.low}-${result.first_innings.high}). ${result.first_innings.in_range ? "Inside the range." : "Outside the range."}`));
  if (result.ai_pick) lines.push(h("li", { class: result.ai_pick.correct ? "good" : "bad" },
    `With the AI check: ${result.ai_pick.pick} at ${pct(result.ai_pick.probability)} (${result.ai_pick.shift > 0 ? "+" : ""}${result.ai_pick.shift} points for the first-named side). ${result.ai_pick.correct ? "Correct." : "Wrong."}`));
  if (result.set_score) lines.push(h("li", { class: result.set_score.correct ? "good" : "bad" },
    `Set score: most likely was ${result.set_score.pick_winner} ${result.set_score.pick}; it finished ${result.set_score.actual}. ${result.set_score.correct ? "Correct." : "Missed."}`));
  for (const pick of result.picks || []) lines.push(h("li", { class: pick.correct ? "good" : "bad" },
    `${pick.team} ${pick.kind === "top_batter" ? "top scorer" : "top wicket-taker"}: picked ${pick.pick}; actual ${pick.actual.join(", ")} (${pick.value}). ${pick.correct ? "Correct." : pick.in_top3 ? "In our top three." : "Missed."}`));
  return h("section", { class: "panel" }, h("h2", {}, "How the forecast did"),
    result.saved_before_start ? null : h("p", { class: "note warn" }, "This forecast was first made after the match started, so it does not count toward the track record."),
    h("ul", { class: "why" }, lines.length ? lines : h("li", {}, result.status || "Result not available yet.")));
}

// The win chance in force: the model's number, moved by the AI check for this stage when there is one.
function nowWin(f) { return f.ai ? f.ai.win : (f.live ? f.live.win : f.teams.map((t) => t.win)); }
function winCaption(f, plain) { return f.ai && f.ai.check ? (f.ai.check.shift ? "model + AI check" : "model, AI check agrees") : plain; }
const aiKey = (id, f) => `${id}|${f.ai ? f.ai.checkpoint : ""}`;

async function askAi(id, sport, f) {
  const key = aiKey(id, f);
  if (state.aiBusy) return;
  state.aiBusy = id;
  state.aiTried[key] = true;
  delete state.aiError[id];
  const box = document.getElementById("ai-box");
  if (box) box.replaceChildren(h("p", { class: "note" }, h("span", { class: "spinner" }), "Asking the AI to check the latest numbers and score. This takes up to a minute."));
  let result;
  try {
    result = await api("/api/ai-check", { match_id: id, sport });
    showBudgets(result.budget);
  } catch (error) { state.aiError[id] = error.message; }
  state.aiBusy = null;
  if (location.hash === `#match/${encodeURIComponent(id)}`) {
    const panel = document.getElementById("ai-box")?.closest("section");
    if (panel?.dataset.checkpoint === f.ai.checkpoint && (!result || result.ai.checkpoint === f.ai.checkpoint)) {
      panel.replaceWith(aiPanel({ ...f, ai: result?.ai || f.ai }, id, sport));
    }
    state.autoRefreshed = true;
    openMatch(id, true);
  }
}

function aiPanel(f, id, sport) {
  const ai = f.ai;
  if (!ai) return null;
  const names = f.teams.map((t) => t.name), check = ai.check, old = ai.earlier;
  const body = [];
  const describe = (c) => [
    c.headline ? h("p", { class: "headline" }, c.headline) : null,
    h("ul", { class: "why" }, (c.reasons || []).map((r) => h("li", {}, r)), c.watch ? h("li", {}, `Watch: ${c.watch}`) : null)];
  if (check) {
    const moved = check.shift ? `The AI check moves ${names[0]} from ${pct(ai.model_win[0])} to ${pct(ai.win[0])} (${check.shift > 0 ? "+" : ""}${check.shift} points).`
      : `The AI check agrees with the model: ${names[0]} ${pct(ai.model_win[0])}, no change.`;
    body.push(...describe(check), h("p", { class: "note", style: "margin-top:10px" }, moved),
      h("p", { class: "sub" }, `Checked by ${check.model} at ${time(check.at)}${check.score ? `, with the score at ${check.score}` : ""}.`));
  } else {
    if (state.aiBusy === id) body.push(h("p", { class: "note" }, h("span", { class: "spinner" }), "Asking the AI to check the latest numbers and score. This takes up to a minute."));
    else if (state.aiError[id]) body.push(h("p", { class: "note error" }, state.aiError[id]));
    else if (ai.note) body.push(h("p", { class: "note" }, ai.note));
    else if (sport === "cricket") body.push(h("p", { class: "note" }, "Request a second opinion on the current match forecast."));
    else if (!ai.due) body.push(h("p", { class: "note" }, `AI checks start by themselves ${ai.checkpoint && ai.checkpoint.startsWith("live") ? "at the next stage of the match" : "45 minutes before the start"}. You can also ask now.`));
    if (ai.can_ask && state.aiBusy !== id) body.push(h("button", { class: "btn", type: "button", style: "margin-top:10px", onclick: () => askAi(id, sport, f) },
      `Ask the AI now (${ai.requests_left} requests left today)`));
    if (old) body.push(h("h3", { style: "margin-top:14px" }, `Earlier check${old.score ? ` at ${old.score}` : ""} (${time(old.at)})`), ...describe(old));
  }
  return h("section", { class: "panel ai", "data-checkpoint": ai.checkpoint || "" }, h("h2", {}, "AI check"),
    h("div", { id: "ai-box" }, body),
    h("p", { class: "sub", style: "margin-top:10px" }, `The model's numbers come first. At each stage (before the toss or start, then as the score moves) a free AI model reads those numbers and the live score and may move the win chance by at most ${ai.max_shift} points, with reasons. ${ai.used} of ${ai.limit} checks used for this match. Its picks are graded in Track record.`));
}

function winPanel(f, title) {
  const [a, b] = f.teams, win = f.live ? [a.win, b.win] : nowWin(f);
  return h("section", { class: "panel" },
    h("h2", {}, title),
    h("div", { class: "winbar", role: "img", "aria-label": `${a.name} ${pct(win[0])}, ${b.name} ${100 - Math.round(win[0] * 100)}%` },
      h("div", { class: "a", style: `width:${Math.max(8, win[0] * 100)}%` }, pct(win[0])), h("div", { class: "b", style: `width:${Math.max(8, win[1] * 100)}%` }, `${100 - Math.round(win[0] * 100)}%`)),
    h("div", { class: "winlabels" }, h("span", {}, a.name), h("span", {}, b.name)),
    !f.live && f.ai && f.ai.check && f.ai.check.shift ? h("p", { class: "sub" }, `Model alone: ${a.name} ${pct(f.ai.model_win[0])}. The AI check moved it ${f.ai.check.shift > 0 ? "+" : ""}${f.ai.check.shift} points.`) : null,
    a.win_model != null ? h("p", { class: "sub" }, `Corrected from past results: the model alone said ${a.name} ${pct(a.win_model)}. Across ${f.calibration.graded} graded forecasts its favourites were given ${pct(f.calibration.favourite_expected)} on average and won ${pct(f.calibration.favourite_won)}, so its chances are ${f.calibration.factor < 1 ? "pulled toward" : "pushed away from"} 50%.`) : null,
    a.win_parts ? h("p", { class: "sub" }, `What goes into the model's number: player-by-player simulation ${pct(a.win_parts.simulation)} for ${a.name}, team results rating ${pct(a.win_parts.rating)}.`) : null);
}

// ---- tennis match page ----------------------------------------------------------------
function setRows(rows) {
  return rows.map((row) => h("div", { class: "setrow" }, h("span", {}, `${row.winner} ${row.score.split("-").sort().reverse().join("-")}`),
    h("div", { class: "track" }, h("div", { class: "fill", style: `width:${Math.round(row.chance * 100)}%` })), h("span", { class: "num" }, pct(row.chance))));
}

function tennisPlayer(t) {
  const r = t.rating;
  return h("section", { class: "panel team" },
    h("h2", {}, t.name),
    h("p", { class: "sub" }, t.found ? `${r.matches} matches on record${t.last_played ? ` · last recorded week ${day(t.last_played)}` : ""}` : "Not in the results archive"),
    h("div", { class: "stats" },
      h("div", { class: "stat" }, h("div", { class: "k" }, "Rating"), h("div", { class: "v" }, r.blended), h("div", { class: "s" }, r.overall == null ? "from ranking" : `overall ${r.overall} · surface ${r.surface}`)),
      h("div", { class: "stat" }, h("div", { class: "k" }, "Holds serve"), h("div", { class: "v" }, pct(t.hold)), h("div", { class: "s" }, `wins ${pct(t.serve_points_won)} of serve points`)),
      h("div", { class: "stat" }, h("div", { class: "k" }, "Wins first set"), h("div", { class: "v" }, pct(t.first_set)), h("div", { class: "s" }, "before the match"))),
    h("h3", {}, "Why"),
    h("ul", { class: "why" }, t.reasons.map((x) => h("li", {}, x))),
    t.recent.length ? h("details", { class: "more" }, h("summary", {}, "Recent recorded matches"),
      h("ul", { class: "why" }, t.recent.map((m) => h("li", {}, `${day(m.date)} · ${m.won ? "beat" : "lost to"} ${m.opponent} ${m.score} · ${m.event} (${m.surface})`)))) : null);
}

function tennisLive(f) {
  const live = f.live, timeline = (f.saved && f.saved.timeline) || [], names = f.teams.map((t) => t.name), win = nowWin(f);
  return h("section", { class: "panel live" },
    h("h2", {}, h("span", { class: "tag live" }, "Live"), ` ${live.score}`),
    h("div", { class: "stats" },
      h("div", { class: "stat" }, h("div", { class: "k" }, `${names[0]} win chance`), h("div", { class: "v" }, pct(win[0])), h("div", { class: "s" }, winCaption(f, "right now"))),
      h("div", { class: "stat" }, h("div", { class: "k" }, `${names[1]} win chance`), h("div", { class: "v" }, `${100 - Math.round(win[0] * 100)}%`), h("div", { class: "s" }, `sets ${live.sets[0]}-${live.sets[1]}`)),
      h("div", { class: "stat" }, h("div", { class: "k" }, `Set ${live.set_number}`), h("div", { class: "v" }, `${live.games[0]}-${live.games[1]}`), h("div", { class: "s" }, `${names[0]} wins it ${pct(live.current_set)}`))),
    h("h3", {}, "What has changed"),
    h("ul", { class: "why" }, live.changes.map((c) => h("li", {}, c))),
    h("h3", {}, "Likely finish from here"), setRows(live.set_scores),
    timeline.length > 1 ? h("ul", { class: "timeline" }, timeline.slice().reverse().slice(0, 12).map((t) =>
      h("li", {}, h("time", {}, time(t.at)), h("span", {}, `${t.score}. ${t.note}`)))) : null);
}

function renderTennis(f, id) {
  const [a, b] = f.teams, fx = f.fixture, bt = f.analysis.backtest;
  show(
    h("a", { class: "back", href: "#matches" }, "← All matches"),
    h("div", { class: "head" },
      h("div", {}, h("h1", {}, `${a.name} v ${b.name}`),
        h("p", { class: "sub" }, [fx.tournament, fx.detail, f.format, `${f.surface.name} court`, `${day(fx.start)} ${time(fx.start)}`, f.intel.state === "pre" ? countdown(fx.start) : f.intel.status].filter(Boolean).join(" · "))),
      h("button", { id: "refresh-match", class: "btn primary", type: "button", onclick: () => openMatch(id, true, true) }, "Refresh now")),
    h("p", { id: "match-refresh-error", class: "note", role: "status", hidden: true }),
    f.intel.available ? null : h("p", { class: "note warn" }, "The live score feed could not be read just now, so this is the pre-match forecast."),
    f.result ? resultPanel(f.result) : null,
    f.live ? tennisLive(f) : null,
    winPanel(f, f.live ? "Pre-match win chance" : "Win chance"),
    aiPanel(f, id, "tennis"),
    h("section", { class: "panel" }, h("h2", {}, "Why this forecast"),
      h("ul", { class: "why" }, f.notes.map((n) => h("li", {}, n)), h("li", {}, f.surface.note)),
      f.h2h.last.length ? h("details", { class: "more", style: "margin-top:8px" }, h("summary", {}, "Their recorded meetings"),
        h("ul", { class: "why" }, f.h2h.last.map((m) => h("li", {}, `${day(m.date)} · ${m.winner} won ${m.score} · ${m.event} (${m.surface})`)))) : null),
    h("section", { class: "panel" }, h("h2", {}, "Set score chances (before the match)"), setRows(f.set_scores),
      h("div", { class: "stats", style: "margin-top:12px" },
        h("div", { class: "stat" }, h("div", { class: "k" }, "Goes to a deciding set"), h("div", { class: "v" }, pct(f.deciding_set)), h("div", { class: "s" }, f.format.toLowerCase())),
        h("div", { class: "stat" }, h("div", { class: "k" }, "Expected games"), h("div", { class: "v" }, f.expected_games.toFixed(1)), h("div", { class: "s" }, "a tiebreak counts as one")))),
    h("div", { class: "grid2" }, tennisPlayer(a), tennisPlayer(b)),
    h("section", { class: "panel" }, h("h2", {}, "How this match was analysed"),
      h("ul", { class: "why" }, h("li", {}, `Data: ${f.analysis.data}`), h("li", {}, `${f.analysis.machine_learning.name}. ${f.analysis.machine_learning.detail}`),
        h("li", {}, `Deep learning: ${f.analysis.deep_learning.detail}`)),
      bt ? h("p", { class: "note", style: "margin-top:12px" },
        `Tested on ${bt.matches} tour-level ${f.tour} matches the ratings had never seen (${bt.window[0]} to ${bt.window[1]}): they picked the winner ${pct(bt.accuracy)} of the time. Simply picking the better-ranked player was right ${pct(bt.better_ranked_wins)} of the time.`) : null));
}

function renderForecast(f, id) {
  const fx = f.fixture;
  const supported = f.supported;
  const start = fx.start ? `${day(fx.start)} · ${time(fx.start)}` : "";
  show(
    h("a", { class: "back", href: "#matches" }, "← All matches"),
    h("div", { class: "head" },
      h("div", {}, h("h1", {}, `${fx.team} vs ${fx.opponent}`),
        h("p", { class: "sub" }, [fx.tournament, supported ? `${f.category}’s ${f.format}` : fx.detail,
          fx.venue, start].filter(Boolean).join(" · "))),
      h("button", { id: "refresh-match", class: "btn primary", type: "button", onclick: () => openMatch(id, true, true) }, "Refresh now")),
    h("p", { id: "match-refresh-error", class: "note warn", role: "status", hidden: true }),
    matchScoreboard(f.scoreboard),
    supported ? preMatchPanel(f, id) : h("section", { class: "panel" }, h("h2", {}, "Forecast unavailable"), h("p", { class: "sub" }, f.reason)),
    supported ? livePanel(f, id) : h("section", { class: "panel" }, h("h2", {}, "Live analysis"), h("p", { class: "sub" }, f.reason)),
    f.result && f.result.saved_before_start ? resultPanel(f.result) : null,
    supported && f.ai ? aiPanel(f, id, "cricket") : null,
    supported ? analysisPanel(f) : null);
}

async function openMatch(id, manual, forceRefresh = false) {
  if (state.matchLoading === id) return;
  state.matchLoading = id;
  clearTimeout(state.timer);
  const request = ++state.request;
  const isCurrent = () => request === state.request && location.hash === `#match/${encodeURIComponent(id)}`;
  const match = findMatch(id);
  if (!manual) {
    show(h("a", { class: "back", href: "#matches" }, "← All matches"),
      h("h1", {}, match ? `${match.team}${match.opponent ? " v " + match.opponent : ""}` : "Match"),
      match?.sport === "cricket" ? matchScoreboard({ state: match.state, status: match.status, source: "Fixture scoreboard",
        checked_at: state.schedule?.last_updated, teams: [{ name: match.team, score: match.team_score },
          { name: match.opponent, score: match.opponent_score }] }) : null,
      h("p", { class: "note", style: "margin-top:14px" }, h("span", { class: "spinner" }), match && match.sport === "tennis"
        ? "Reading the live score and rating both players from every recorded match. The first tennis forecast after a restart takes a few seconds."
        : "Gathering the toss, playing XIs and venue, then simulating the match 3,000 times. The first forecast of the day takes up to a minute while the model is fitted."));
  }
  const sport = id.startsWith("tennis-") ? "tennis" : "cricket";
  if (match && match.sport === "f1") {
    state.matchLoading = null;
    return renderF1();
  }
  const refreshButton = document.getElementById("refresh-match");
  if (refreshButton) { refreshButton.disabled = true; refreshButton.textContent = "Refreshing…"; }
  const refreshStatus = document.getElementById("match-refresh-error");
  if (refreshStatus) { refreshStatus.hidden = false; refreshStatus.className = "note"; refreshStatus.textContent = "Checking the latest score and forecast…"; }
  try {
    const forecast = await api(`/api/${sport}-forecast`, { match_id: id, refresh: forceRefresh, live: state.liveMatch === id });
    if (!isCurrent()) return;
    showBudgets(forecast.budget);
    if (!forecast.supported && sport === "tennis") {
      show(h("a", { class: "back", href: "#matches" }, "← All matches"),
        h("h1", {}, match ? `${match.team} v ${match.opponent}` : "Match"), h("p", { class: "note warn", style: "margin-top:14px" }, forecast.reason));
      return;
    }
    forecast.has_feed = sport === "tennis" ? true : forecast.has_feed;
    const open = [...view.querySelectorAll("details")].map((d, i) => d.open ? d.dataset.key || i : null);
    const focused = view.contains(document.activeElement) ? document.activeElement : null;
    const focusKey = focused?.closest("[data-key]")?.dataset.key;
    const scroll = window.scrollY;
    (sport === "tennis" ? renderTennis : renderForecast)(forecast, id);
    const statusMessage = document.getElementById("match-refresh-error");
    if (statusMessage) {
      statusMessage.hidden = false;
      statusMessage.className = forecast.refresh_error ? "note warn" : "note";
      statusMessage.textContent = forecast.refresh_error || `Updated at ${new Date().toLocaleTimeString()}. Scores and predictions may stay the same until the feed reports a change.`;
    }
    if (forecast.ai && forecast.ai.due && sport === "tennis" && !state.aiBusy && !state.aiTried[aiKey(id, forecast)]) askAi(id, sport, forecast);
    if (manual || state.autoRefreshed) {
      view.querySelectorAll("details").forEach((d, i) => { d.open = open.includes(d.dataset.key || i); });
      if (focused?.id) document.getElementById(focused.id)?.focus({ preventScroll: true });
      else if (focusKey) {
        const match = [...view.querySelectorAll("[data-key]")].find((node) => node.dataset.key === focusKey);
        match?.querySelector(focused.tagName.toLowerCase())?.focus({ preventScroll: true });
      }
      window.scrollTo(0, scroll);
    }
    const startsIn = Date.parse(forecast.fixture.start) - Date.now();
    const status = forecast.intel?.state || forecast.scoreboard?.state;
    state.liveMatch = status === "in" ? id : null;
    if (status === "in" || status === "pre" && (sport === "cricket" || startsIn < 75 * 60000)) {
      const delay = sport === "cricket" && status === "in" ? 12000 : 60000;
      if (forecast.has_feed || sport === "cricket") {
        state.timer = setTimeout(async () => {
          if (sport === "cricket" && !forecast.has_feed) await refreshSchedule();
          if (!isCurrent()) return;
          state.autoRefreshed = true;
          openMatch(id, true);
        }, sport === "cricket" && !forecast.has_feed ? 5 * 60000 : delay);
      }
    }
  } catch (error) {
    if (!isCurrent()) return;
    const refreshError = document.getElementById("match-refresh-error");
    if (refreshError) {
      refreshError.hidden = false;
      refreshError.className = "note warn";
      refreshError.textContent = `Could not refresh the match. Showing the last available update. ${error.message}`;
      state.timer = setTimeout(() => { if (isCurrent()) openMatch(id, true); }, 60000);
      return;
    }
    show(h("a", { class: "back", href: "#matches" }, "← All matches"), h("p", { class: "note error", style: "margin-top:14px" }, error.message),
      h("button", { class: "btn", type: "button", style: "margin-top:12px", onclick: () => openMatch(id) }, "Try again"));
  } finally {
    if (state.matchLoading === id) state.matchLoading = null;
    if (isCurrent()) {
      const button = document.getElementById("refresh-match");
      if (button) { button.disabled = false; button.textContent = "Refresh now"; }
    }
  }
}

// ---- track record and settings --------------------------------------------------------
async function renderRecord() {
  const request = ++state.request;
  show(h("h1", {}, "Track record"), h("p", { class: "note", role: "status" }, "Grading finished events…"));
  try {
    const { summary, sports } = await api("/api/track-record");
    if (request !== state.request) return;
    const rate = (record) => record.n ? `${record.correct} of ${record.n}` : "—";
    const detail = h("section", { id: "sport-record", "aria-labelledby": "sport-record-title" });
    const filters = h("div", { class: "row record-filters", role: "group", "aria-label": "Sport" });
    function select(sport) {
      const { summary: stats, matches } = sports[sport];
      for (const button of filters.children) button.setAttribute("aria-pressed", String(button.value === sport));
      const calibration = summary.calibration[sport];
      const metrics = [stat("Winner picked", rate(stats.winner), `${stats.graded} graded · ${stats.waiting} waiting`)];
      if (sport !== "f1") metrics.push(stat("Winner with AI check", rate(stats.ai_winner)));
      if (sport === "tennis") metrics.push(stat("Exact set score", rate(stats.set_score)));
      if (sport === "cricket") metrics.push(
        stat("First-innings error", stats.first_innings.mean_error == null ? "—" : `${stats.first_innings.mean_error} runs`,
          `${stats.first_innings.in_range} of ${stats.first_innings.n} inside the range`),
        stat("Top batter", rate(stats.top_batter)), stat("Top wicket-taker", rate(stats.top_bowler)));
      const table = h("div", { class: "scroll" }, h("table", {},
        h("thead", {}, h("tr", {}, ["Event", "Forecast", "Saved", "Result"].map((label) => h("th", { scope: "col" }, label)))),
        h("tbody", {}, matches.map((match) => {
          const result = match.result;
          const favourite = match.teams.reduce((first, next) => next.win > first.win ? next : first);
          const title = [match.fixture.team, match.fixture.opponent].filter(Boolean).join(" v ");
          const stage = ({ post_toss: "After toss", pre_toss: "Before toss", post_qualifying: "After qualifying", pre_weekend: "Before race weekend" })[match.stage];
          return h("tr", {},
            h("td", {}, h("a", { href: sport === "f1" ? `/lab?sport=f1&season=${match.fixture.season}&round=${match.fixture.round}`
              : `#match/${encodeURIComponent(match.id)}` }, title), h("div", { class: "sub" }, day(match.fixture.start))),
            h("td", {}, `${favourite.name} ${pct(favourite.win)}`),
            h("td", {}, time(match.saved_at), stage ? h("div", { class: "sub" }, stage) : null,
              match.saved_before_start ? null : h("div", { class: "sub" }, "Opened after start")),
            h("td", {}, !result ? "Waiting for result" : !result.winner_pick ? (result.status || "No winner") :
              h("span", { class: result.winner_pick.correct ? "good" : "bad" }, `${result.winner} won · ${result.winner_pick.correct ? "Correct" : "Missed"}`),
              result?.first_innings ? h("div", { class: "sub" }, `First innings ${result.first_innings.actual} vs forecast ${result.first_innings.predicted}`) : null,
              result?.set_score ? h("div", { class: "sub" }, `Sets ${result.set_score.actual} vs forecast ${result.set_score.pick}`) : null));
        }))));
      detail.replaceChildren(
        h("h2", { id: "sport-record-title" }, SPORTS[sport]),
        h("div", { class: "stats record-stats" }, metrics),
        calibration ? h("p", { class: "sub" }, calibration.graded < calibration.needed
          ? `Win chance calibration needs ${calibration.needed} graded forecasts. ${calibration.graded} available.`
          : `Favourites won ${pct(calibration.favourite_won)} of ${calibration.graded} graded forecasts. Average predicted chance was ${pct(calibration.favourite_expected)}.`) : null,
        h("section", { class: "panel" }, h("h3", {}, "Saved forecasts"),
          matches.length ? table : h("p", { class: "note" }, sport === "f1"
            ? "Run a Formula 1 forecast before the race to start tracking it."
            : `Open a ${SPORTS[sport].toLowerCase()} match before the start to save its forecast.`),
          sport === "f1" ? h("p", { class: "sub" }, h("a", { href: "/lab?sport=f1" }, "Open the race forecast")) : null));
    }
    for (const [sport, label] of Object.entries(SPORTS)) {
      filters.append(h("button", { class: "chip", type: "button", value: sport, "aria-controls": "sport-record",
        onclick: () => { state.recordSport = sport; select(sport); } }, `${label} · ${sports[sport].summary.saved}`));
    }
    show(h("div", { class: "head" }, h("div", {}, h("h1", {}, "Track record"),
      h("p", { class: "sub" }, "Accuracy counts forecasts saved before play or the race start."))),
      filters, detail);
    select(state.recordSport || "cricket");
  } catch (error) {
    if (request === state.request) show(h("h1", {}, "Track record"), h("p", { class: "note error", role: "alert" }, error.message));
  }
}

function renderSettings() {
  const hasKey = Boolean(state.keyStatus) && state.keyStatus !== "missing";
  const input = h("input", { type: "password", autocomplete: "off", "aria-label": "OpenRouter API key", placeholder: "Paste your OpenRouter key" });
  const message = h("p", { class: "sub", style: "margin-top:8px" }, hasKey ? "A key is saved on this computer." : "No key saved yet.");
  const send = async (action) => {
    try {
      const out = await api("/api/openrouter-key", action === "save" ? { action, key: input.value } : { action });
      state.keyStatus = out.openrouter_key_status;
      input.value = "";
      message.textContent = action === "save" ? "Key saved on this computer." : "Key removed.";
    } catch (error) { message.textContent = error.message; }
  };
  const b = state.schedule && state.schedule.budget;
  show(h("h1", {}, "Settings"),
    h("section", { class: "panel appearance-settings", "aria-labelledby": "appearance-title" },
      h("h2", { id: "appearance-title" }, "Appearance"),
      h("p", { class: "sub", id: "theme-help" }, "Choose a theme for MatchLab. Your choice is saved in this browser."),
      h("label", { class: "palette-control", for: "palette" }, "Theme",
        h("select", { id: "palette", "aria-label": "Color palette", "aria-describedby": "theme-help", onchange: (event) => changeTheme(event.target.value) },
          Object.entries(THEMES).map(([value, label]) => h("option", { value, selected: state.theme === value }, label))))),
    h("section", { class: "panel" }, h("h2", {}, "Request budgets"),
      h("ul", { class: "why" },
        h("li", {}, `CricketData.org: ${b ? `${b.cricketdata.used} of ${b.cricketdata.limit} used today` : "unknown"}. Only the fixture list uses it, cached for 15 minutes (longer as the budget runs down), and 5 requests are always held back.`),
        h("li", {}, `OpenRouter: ${b ? `${b.openrouter.used} of ${b.openrouter.limit} used today` : "unknown"}. Used for AI checks: one request per match and stage (before the toss or start, after the toss, then a few times as the score moves), at most 12 per match, saved so nothing is asked twice. Checks start by themselves 45 minutes before a match you have open.`),
        h("li", {}, "The toss, playing XIs and live scores come from ESPN's free feed and cost nothing, so the half hour before a match is never rationed."),
        h("li", {}, "Daily limits can be edited in data/local/api_budget.json if your plan differs."))),
    h("section", { class: "panel" }, h("h2", {}, "OpenRouter key (optional)"),
      h("div", { class: "row" }, input, h("button", { class: "btn primary", type: "button", onclick: () => send("save") }, "Save key"),
        h("button", { class: "btn", type: "button", onclick: () => send("clear") }, "Remove key")), message));
}

function f1LapPanel(last, next, request) {
  const choices = [last, next].filter((race) => race?.season && race?.round);
  const panel = h("section", { class: "panel", "aria-labelledby": "f1-lap-title" },
    h("h2", { id: "f1-lap-title" }, "Lap-by-lap analysis"));
  if (!choices.length) {
    panel.append(h("p", { class: "note" }, "Waiting for a published race schedule."));
    return panel;
  }
  const key = (race) => `${race.season}/${race.round}`;
  const start = (race) => Date.parse(`${race.date}T${race.time || "00:00:00Z"}`);
  const preferred = next && start(next) <= Date.now() ? next : last || next;
  const select = h("select", { id: "f1-lap-race" },
    choices.map((race) => h("option", { value: key(race), selected: key(race) === key(preferred) }, race.raceName)));
  const status = h("p", { class: "note", role: "status" });
  const rows = h("div", { class: "scroll lap-table", tabindex: "0", role: "region", "aria-label": "Lap timing" });
  const refresh = h("button", { class: "btn", type: "button", onclick: load }, "Refresh laps");
  let captured = new Map(), generation = 0;

  async function load() {
    clearTimeout(state.timer);
    const selected = choices.find((race) => key(race) === select.value);
    const current = ++generation;
    const active = () => request === state.request && current === generation;
    refresh.disabled = true;
    if (!captured.size) status.textContent = "Loading lap timing…";
    try {
      const result = await api(`/api/f1-timing?season=${selected.season}&round=${selected.round}`);
      if (!active()) return;
      if (result.state === "post") captured.clear();
      for (const lap of result.laps) captured.set(lap.lap, lap);
      const laps = [...captured.values()].sort((a, b) => b.lap - a.lap);
      const recorded = result.state === "post";
      status.textContent = laps.length
        ? recorded ? "Recorded timings from Jolpica F1." : "Live race order from ESPN. Updates are captured while this page is open."
        : result.state === "pre" ? "Lap updates start when race timing is available."
          : "Lap timing hasn’t been published for this race yet.";
      const lapRows = laps.map((lap) => {
        const prior = captured.get(lap.lap - 1);
        const moves = prior ? lap.order.filter((driver) => Object.hasOwn(prior.positions, driver))
          .map((driver) => ({ driver, gain: prior.positions[driver] - lap.positions[driver] }))
          .sort((a, b) => b.gain - a.gain) : [];
        const gain = moves[0];
        const changes = [
          prior?.order[0] && prior.order[0] !== lap.order[0] ? `${lap.order[0]} took the lead` : "",
          gain?.gain > 0 ? `${gain.driver} gained ${gain.gain} place${gain.gain === 1 ? "" : "s"}` : "",
        ].filter(Boolean);
        return h("tr", {}, h("td", {}, lap.lap), h("td", {}, lap.order[0]),
          h("td", {}, lap.fastest ? `${lap.fastest.driver} · ${lap.fastest.time}` : "—"),
          h("td", {}, changes.join(" · ") || (prior ? "—" : "No previous lap captured")));
      });
      const header = ["Lap", "Leader", "Fastest on lap", "Race movement"].map((label) => h("th", { scope: "col" }, label));
      rows.replaceChildren(...(laps.length ? [h("table", {}, h("thead", {}, h("tr", {}, header)), h("tbody", {}, lapRows))] : []));
      if (result.state === "in" || result.state === "pre" && start(selected) - Date.now() <= 60 * 60000) {
        state.timer = setTimeout(load, 25000);
      }
    } catch (error) {
      if (!active()) return;
      status.textContent = captured.size ? "Could not refresh timing. Showing the last captured laps." : error.message;
      if (Date.now() >= start(selected) && Date.now() < start(selected) + 4 * 3600000) state.timer = setTimeout(load, 30000);
    } finally {
      if (active()) refresh.disabled = false;
    }
  }
  select.addEventListener("change", () => {
    captured = new Map();
    rows.replaceChildren();
    load();
  });
  panel.append(h("div", { class: "row lap-controls" }, h("label", { for: "f1-lap-race" }, "Grand Prix"), select, refresh), status, rows);
  load();
  return panel;
}

async function renderF1() {
  const request = ++state.request;
  clearTimeout(state.timer);
  show(h("div", { class: "f1-hero" }, h("p", { class: "f1-kicker" }, "MATCHLAB / FORMULA 1"), h("h1", {}, "The championship, in focus."), h("p", {}, "Loading standings and race results…")));
  try {
    const data = await api("/api/f1-dashboard");
    if (request !== state.request) return;
    const driversList = data.drivers?.StandingsTable?.StandingsLists?.[0];
    const teamsList = data.teams?.StandingsTable?.StandingsLists?.[0];
    const drivers = driversList?.DriverStandings || [];
    const teams = teamsList?.ConstructorStandings || [];
    const last = data.last?.RaceTable?.Races?.[0];
    const next = data.next?.RaceTable?.Races?.[0];
    const table = (headers, rows) => h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {}, headers.map(x => h("th", {}, x)))), h("tbody", {}, rows)));
    const unavailable = () => h("p", { class: "note warn" }, "Data unavailable from Jolpica. Try refreshing.");
    show(h("div", { class: "f1-hero" }, h("p", { class: "f1-kicker" }, "MATCHLAB / FORMULA 1"), h("h1", {}, "The championship, in focus."),
      h("p", {}, "Standings, results and the road ahead."),
      h("div", { class: "f1-hero-bottom" }, h("span", {}, `Jolpica checked ${new Date(data.checked_at).toLocaleString()} · Data may be delayed`), h("button", { class: "btn", type: "button", onclick: renderF1 }, "Refresh data"))),
      h("div", { class: "f1-overview" },
        h("section", { class: "panel" }, h("p", { class: "f1-label" }, "NEXT RACE"), next ? [h("h2", {}, next.raceName), h("p", { class: "sub" }, `${next.Circuit?.circuitName || ""} · ${day(next.date + "T" + (next.time || "00:00:00Z"))}`), h("p", {}, next.time ? time(next.date + "T" + next.time) : "Start time to be confirmed")] : data.next ? h("p", {}, "No upcoming race published.") : unavailable()),
        h("section", { class: "panel" }, h("p", { class: "f1-label" }, "CHAMPIONSHIP LEADER"), drivers.length ? [h("h2", {}, `${drivers[0].Driver.givenName} ${drivers[0].Driver.familyName}`), h("p", { class: "sub" }, (drivers[0].Constructors || []).map(x => x.name).join(" / ")), h("p", { class: "f1-points" }, `${drivers[0].points} pts`)] : unavailable())),
      f1LapPanel(last, next, request),
      h("div", { class: "f1-grid" },
        h("section", { class: "panel" }, h("p", { class: "f1-label" }, `${driversList?.season || "CURRENT"} SEASON · ROUND ${driversList?.round || "—"}`), h("h2", {}, "Driver standings"), drivers.length ? table(["Pos", "Driver", "Team", "Wins", "Points"], drivers.map(d => h("tr", {}, h("td", {}, d.position), h("td", {}, `${d.Driver.givenName} ${d.Driver.familyName}`), h("td", {}, (d.Constructors || []).map(c => c.name).join(" / ")), h("td", {}, d.wins), h("td", {}, h("strong", {}, d.points))))) : unavailable()),
        h("section", { class: "panel" }, h("p", { class: "f1-label" }, "THE TEAMS"), h("h2", {}, "Constructor standings"), teams.length ? table(["Pos", "Team", "Wins", "Points"], teams.map(t => h("tr", {}, h("td", {}, t.position), h("td", {}, t.Constructor.name), h("td", {}, t.wins), h("td", {}, h("strong", {}, t.points))))) : unavailable())),
      h("section", { class: "panel" }, h("p", { class: "f1-label" }, "LATEST GRAND PRIX"), h("h2", {}, last?.raceName || "Race results"), last ? [h("p", { class: "sub" }, `${last.date} · ${last.Circuit?.circuitName || ""}`), table(["Pos", "Driver", "Team", "Points", "Status"], (last.Results || []).map(r => h("tr", {}, h("td", {}, r.position), h("td", {}, `${r.Driver.givenName} ${r.Driver.familyName}`), h("td", {}, r.Constructor.name), h("td", {}, r.points), h("td", {}, r.status))))] : unavailable()),
      h("p", { class: "note f1-source" }, "Standings and results from Jolpica F1 may be delayed. ", h("a", { href: "/lab?sport=f1" }, "Open the race forecast")));
  } catch (error) {
    if (request !== state.request) return;
    show(h("h1", {}, "Formula 1"), h("p", { class: "note error" }, "Could not refresh Formula One data. Check your connection and try again."), h("button", { class: "btn", type: "button", onclick: renderF1 }, "Try again"));
  }
}

function route() {
  clearTimeout(state.timer);
  state.request++;
  state.autoRefreshed = false;
  const hash = location.hash.slice(1) || "matches";
  const tab = hash.startsWith("match/") ? "matches" : hash;
  document.querySelectorAll("nav a").forEach((a) => a.dataset.tab === tab ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
  if (hash.startsWith("match/")) openMatch(decodeURIComponent(hash.slice(6)));
  else if (hash === "f1") renderF1();
  else if (hash === "record") renderRecord();
  else if (hash === "settings") renderSettings();
  else renderMatches();
  window.scrollTo(0, 0);
}

(async function start() {
  try {
    const [app, schedule] = await Promise.all([api("/api/state"), api("/api/today-matches")]);
    state.token = app.token;
    state.keyStatus = app.openrouter_key_status;
    state.schedule = schedule;
    showBudgets(schedule.budget);
  } catch (error) {
    show(h("p", { class: "note error" }, `MatchLab could not load: ${error.message}`));
    return;
  }
  window.addEventListener("hashchange", route);
  route();
  refreshSchedule();
  setInterval(() => { if (!location.hash || location.hash === "#matches") refreshSchedule(); }, 5 * 60 * 1000);
})();
