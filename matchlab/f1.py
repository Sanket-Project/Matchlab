"""Causal, local Grand Prix forecasts using a retirement model and Plackett–Luce."""
import hashlib
import json
import math
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime, timedelta, timezone

from .data import read_csv

PRE_WEEKEND = "pre_weekend"
POST_QUALIFYING = "post_qualifying"
STAGES = (PRE_WEEKEND, POST_QUALIFYING)
FINISHED = {"Finished", "Lapped"}
HALF_LIFE_DAYS = 180
SIMULATIONS = 10_000
SEED = 2026
FORM_FEATURES = ("driver_form", "constructor_form", "teammate_gap", "circuit_form",
                 "driver_mechanical_rate", "driver_incident_rate", "constructor_mechanical_rate",
                 "constructor_incident_rate", "new_regulations")
GRID_FEATURES = ("log_grid", "no_regular_grid_slot")


def fit_order(groups):
    """Minimize the regularized Plackett–Luce negative log likelihood."""
    import numpy as np
    from scipy.optimize import minimize

    width = groups[0].shape[1]
    X = np.zeros((len(groups), max(map(len, groups)), width))
    active = np.zeros(X.shape[:2], dtype=bool)
    for i, group in enumerate(groups):
        X[i, :len(group)] = group
        active[i, :len(group)] = True

    def loss(beta):
        scores = np.where(active, np.einsum("ijk,k->ij", X, beta), -np.inf)
        scores -= scores.max(axis=1, keepdims=True)
        weights = np.exp(scores)
        remaining = np.cumsum(weights[:, ::-1], axis=1)[:, ::-1]
        remaining = np.where(active, remaining, 1.0)
        value = (np.log(remaining[active]) - scores[active]).sum() + 0.5 * (beta @ beta)
        residual = weights * np.cumsum(active / remaining, axis=1) - active
        gradient = np.einsum("ij,ijk->k", residual, X) + beta
        return value, gradient

    result = minimize(loss, np.zeros(width), jac=True, method="L-BFGS-B")
    if not result.success:
        raise ValueError(f"Finishing-order fit failed: {result.message}")
    return result.x


def simulate_race(utilities, retirement, simulations=SIMULATIONS, seed=SEED):
    import numpy as np

    rng = np.random.default_rng(seed)
    shape = (simulations, len(utilities))
    retired = rng.random(shape) < retirement
    # Gumbel perturbations generate a Plackett–Luce order among finishers.
    # Randomly order the retirements behind them, independent of race pace.
    scores = utilities + rng.gumbel(size=shape)
    order = np.lexsort((np.where(retired, rng.random(shape), -scores), retired), axis=1)
    positions = np.argsort(order, axis=1) + 1
    return np.column_stack(((positions == 1).mean(axis=0), (positions <= 3).mean(axis=0),
                            (positions <= 10).mean(axis=0), positions.mean(axis=0)))


def forecast_cutoff(race, stage):
    if stage not in STAGES:
        raise ValueError("Choose pre_weekend or post_qualifying")
    if stage == PRE_WEEKEND:
        return race["weekend_start"]
    if not race["qualifying_start"]:
        return race["start"]
    return min(race["start"], race["qualifying_start"] + timedelta(hours=2))


class RaceEngine:
    def __init__(self, folder):
        self.folder = folder
        self.provenance = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
        self.file_hashes = {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                            for name in ("races.csv", "entries.csv", "sprints.csv", "rosters.csv")}
        for name, digest in self.file_hashes.items():
            if self.provenance.get("files", {}).get(name) != digest:
                raise ValueError(f"Dataset checksum mismatch: {folder / name}. Re-import the Jolpica archive.")

        self.races = read_csv(folder / "races.csv", {"race_id", "season", "round", "name", "circuit", "date", "start",
                                                     "weekend_start", "result_available", "regulation_era", "completed"})
        self.by_id, self.by_round = {}, {}
        for race in self.races:
            for name in ("season", "round", "regulation_era", "completed"):
                race[name] = int(race[name])
            for name in ("start", "weekend_start", "qualifying_start", "result_available"):
                race[name] = datetime.fromisoformat(race[name]) if race.get(name) else None
            self.by_id[race["race_id"]] = race
            self.by_round[race["season"], race["round"]] = race
        self.races.sort(key=lambda r: r["start"])
        self.completed = [r for r in self.races if r["completed"]]
        if not self.completed:
            raise ValueError("Formula 1 requires completed Grands Prix")

        identity = {"race_id", "driver_id", "source_driver_id", "driver", "constructor_id", "source_constructor_id", "constructor"}
        labels = {"finish", "status", "classified"}
        self.entries = defaultdict(list)
        for row in read_csv(folder / "entries.csv", identity | labels):
            self.entries[row["race_id"]].append(row)
        self.rosters = defaultdict(dict)
        for row in read_csv(folder / "rosters.csv", identity):
            self.rosters[row["race_id"]][row["driver_id"]] = row
        known = [row for field in self.entries.values() for row in field]
        known.extend(row for field in self.rosters.values() for row in field.values())
        self.source_drivers = {row["source_driver_id"]: row["driver_id"] for row in known}
        self.source_constructors = {row["source_constructor_id"]: row["constructor_id"] for row in known}
        self.sprints = defaultdict(list)
        for row in read_csv(folder / "sprints.csv", identity | labels | {"available"}):
            self.sprints[row["race_id"], row["available"]].append(row)
        self.driver_history, self.constructor_history = defaultdict(list), defaultdict(list)
        self.events = []
        for race in self.completed:
            self._index_event(race, self.entries[race["race_id"]], race["result_available"], sprint=False)
        for (race_id, when), field in self.sprints.items():
            self._index_event(self.by_id[race_id], field, datetime.fromisoformat(when), sprint=True)
        for history in (*self.driver_history.values(), *self.constructor_history.values()):
            history.sort(key=lambda row: row["available"])
        self.events.sort(key=lambda event: event[0])
        self.fitted = OrderedDict()
        self.training_fields = {}

    def _index_event(self, race, field, available, sprint):
        by_constructor = defaultdict(list)
        for row in field:
            row.update(finish=int(row["finish"]), classified=row["classified"] == "1",
                       points=float(row["points"]) if row.get("points") else None)
            row["grid"] = int(row["grid"]) if row.get("grid") else None
            row["qualifying_position"] = int(row["qualifying_position"]) if row.get("qualifying_position") else None
            pace = (row["finish"] - 1) / max(1, len(field) - 1) if row["status"] in FINISHED and row["classified"] else None
            row.update(available=available, sprint=sprint, pace=pace, circuit=race["circuit"])
            by_constructor[row["constructor_id"]].append(row)
        for row in field:
            peers = [p["pace"] for p in by_constructor[row["constructor_id"]] if p is not row and p["pace"] is not None]
            row["teammate_gap"] = row["pace"] - sum(peers) / len(peers) if row["pace"] is not None and peers else None
            self.driver_history[row["driver_id"]].append(row)
            self.constructor_history[row["constructor_id"]].append(row)
        self.events.append((available, race["season"], field))

    def features(self, race, entry, cutoff, stage, field_size):
        def recent(history):
            return [(2 ** (-(cutoff - row["available"]).total_seconds() / (86400 * HALF_LIFE_DAYS))
                     * (0.35 if row["sprint"] else 1.0), row) for row in history if row["available"] < cutoff]

        driver = recent(self.driver_history.get(entry["driver_id"], ()))
        constructor = recent(self.constructor_history.get(entry["constructor_id"], ()))

        def weighted(history, value, minimum=1):
            observations = [(w, observed) for w, row in history if (observed := value(row)) is not None]
            if len(observations) < minimum:
                return math.nan
            total = sum(w for w, _ in observations)
            return sum(w * v for w, v in observations) / total

        def dnf_rate(history, kind):
            def known_type(row):
                if row["status"] in FINISHED or row.get("dnf_type") in ("incident", "mechanical"):
                    return int(row.get("dnf_type") == kind)
                return None
            return weighted(history, known_type)

        circuit = [(w, row) for w, row in driver if row["circuit"] == race["circuit"] and not row["sprint"]]
        features = [weighted(driver, lambda r: r["pace"]), weighted(constructor, lambda r: r["pace"]),
                    weighted(driver, lambda r: r["teammate_gap"]), weighted(circuit, lambda r: r["pace"], minimum=2),
                    dnf_rate(driver, "mechanical"), dnf_rate(driver, "incident"),
                    dnf_rate(constructor, "mechanical"), dnf_rate(constructor, "incident"),
                    int(race["season"] in (2022, 2026))]
        if stage == POST_QUALIFYING:
            grid = entry["grid"]
            features.extend((math.log(grid or field_size + 1) if grid is not None else math.nan,
                             int(grid == 0) if grid is not None else math.nan))
        return features, sum(not row["sprint"] for _, row in driver)

    def training_field(self, race, stage):
        import numpy as np

        key = (race["race_id"], stage)
        if key not in self.training_fields:
            field = sorted(self.entries[race["race_id"]], key=lambda row: row["finish"])
            cutoff = forecast_cutoff(race, stage)
            X = np.array([self.features(race, row, cutoff, stage, len(field))[0] for row in field])
            retirement = np.array([row["status"] not in FINISHED for row in field], dtype=int)
            classified = np.array([row["classified"] and row["status"] in FINISHED for row in field])
            self.training_fields[key] = X, retirement, classified
        return self.training_fields[key]

    def fit(self, cutoff, stage):
        import numpy as np
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        key = cutoff, stage
        if key in self.fitted:
            self.fitted.move_to_end(key)
            return self.fitted[key]
        training = [r for r in self.completed if r["result_available"] < cutoff]
        if len(training) < 20:
            raise ValueError("Formula 1 forecasts need at least 20 completed Grands Prix before the cutoff")
        groups = [self.training_field(r, stage) for r in training]
        transform = make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler())
        X = transform.fit_transform(np.concatenate([matrix for matrix, _, _ in groups]))
        retirement = LogisticRegression(max_iter=1000).fit(X, np.concatenate([target for _, target, _ in groups]))
        cut = np.cumsum([len(matrix) for matrix, _, _ in groups])[:-1]
        orders = [group[mask] for group, (_, _, mask) in zip(np.split(X, cut), groups) if mask.sum() > 1]
        result = transform, retirement, fit_order(orders), len(training), training[-1]["date"]
        self.fitted[key] = result
        if len(self.fitted) > 12:
            self.fitted.popitem(last=False)
        return result

    def field(self, race):
        race_id = race["race_id"]
        if race["completed"]:
            return sorted(self.entries[race_id], key=lambda row: row["driver_id"]), "Recorded race field"
        roster = self.rosters[race_id]
        if roster:
            return sorted(roster.values(), key=lambda row: row["driver_id"]), "Listed entries in the local Jolpica archive"
        latest = next((r for r in reversed(self.completed) if r["season"] == race["season"] and r["start"] < race["start"]), None)
        if latest is None:
            raise ValueError("No entry list or prior field is available for this Grand Prix")
        return sorted(self.entries[latest["race_id"]], key=lambda row: row["driver_id"]), f"Field carried forward from {latest['name']} ({latest['date']})"

    @staticmethod
    def validate_grid(grid, field, *, recorded=False):
        drivers = {row["driver_id"] for row in field}
        if not isinstance(grid, dict) or grid.keys() != drivers:
            raise ValueError("Enter one grid position for each driver. Use 0 for a pit-lane start or no regular grid slot.")
        positions = list(grid.values())
        if any(type(pos) is not int or not 0 <= pos <= len(field) for pos in positions):
            raise ValueError(f"Grid positions must be whole numbers from 0 to {len(field)}")
        regular = [pos for pos in positions if pos]
        if not regular or (not recorded and len(set(regular)) != len(regular)):
            raise ValueError("Regular grid positions must be unique")
        return grid

    def published_grid(self, race, rows):
        local, _ = self.field(race)
        if len(rows) != len(local):
            raise ValueError("The published grid is incomplete for this field")
        field = [{**row,
                  "driver_id": self.source_drivers.get(row["source_driver_id"], row["source_driver_id"]),
                  "constructor_id": self.source_constructors.get(row["source_constructor_id"], row["source_constructor_id"])}
                 for row in rows]
        field.sort(key=lambda row: row["driver_id"])
        grid = {row["driver_id"]: row["grid"] for row in field}
        if len(grid) != len(field):
            raise ValueError("The published grid has duplicate drivers")
        return dict(grid=self.validate_grid(grid, field), field=field, source="Jolpica published starting grid")

    def predict(self, race, stage, grid=None, *, training_cutoff=None, grid_source=None, published_field=None):
        import numpy as np

        cutoff = forecast_cutoff(race, stage)
        fit_cutoff = training_cutoff or cutoff
        if fit_cutoff > cutoff:
            raise ValueError("Training cannot extend past the forecast cutoff")
        field, field_source = (published_field, "Published Jolpica race entries") if published_field else self.field(race)
        if stage == POST_QUALIFYING:
            recorded = grid is None and race["completed"]
            if grid is None:
                if not race["completed"]:
                    raise ValueError("Grid unavailable for this race. Check updates or enter the grid manually.")
                grid = {row["driver_id"]: row["grid"] for row in field}
                grid_source = "Recorded starting grid"
            grid = self.validate_grid(grid, field, recorded=recorded)
            grid_source = grid_source or "Entered grid"
        else:
            grid, grid_source = {}, None
        X, history = zip(*(self.features(race, {**row, "grid": grid.get(row["driver_id"])}, cutoff, stage, len(field))
                           for row in field))
        transform, retirement, order, fitted_races, fit_through = self.fit(fit_cutoff, stage)
        transformed = transform.transform(np.asarray(X))
        probability_dnf = retirement.predict_proba(transformed)[:, 1]
        probabilities = simulate_race(transformed @ order, probability_dnf)
        names = FORM_FEATURES + (GRID_FEATURES if stage == POST_QUALIFYING else ())
        drivers = []
        for row, values, prior_races, p_dnf, (win, podium, points, finish) in zip(field, X, history, probability_dnf, probabilities):
            actual = ({key: row[key] for key in ("finish", "classified", "status", "points")} if race["completed"] else None)
            drivers.append(dict(driver_id=row["driver_id"], driver=row["driver"], constructor=row["constructor"],
                                grid=grid.get(row["driver_id"]), win=float(win), podium=float(podium), points=float(points),
                                expected_position=float(finish), retirement=float(p_dnf), prior_races=prior_races, actual=actual,
                                imputed_features=[name for name, v in zip(names, values) if math.isnan(v)]))
        return dict(sport="f1", **self.race_summary(race), stage=stage, cutoff=cutoff.isoformat(),
                    drivers=sorted(drivers, key=lambda row: (-row["win"], row["expected_position"], row["driver_id"])),
                    provenance=dict(model="Logistic retirement + Plackett–Luce finishing order", simulations=SIMULATIONS,
                                    seed=SEED, fitted_races=fitted_races, fitted_through=fit_through,
                                    training_cutoff=fit_cutoff.isoformat(), grid_source=grid_source, field_source=field_source,
                                    data_sources=self.provenance, feature_names=list(names), half_life_days=HALF_LIFE_DAYS,
                                    missing_values="Training medians; columns entirely missing in training are zeroed"))

    def standings(self, race, cutoff, driver_ids):
        points = defaultdict(float)
        countback = defaultdict(Counter)
        for available, season, field in self.events:
            if available >= cutoff:
                break
            if season != race["season"]:
                continue
            for row in field:
                if row["points"] is not None:
                    points[row["driver_id"]] += row["points"]
                if row["classified"] and not row["sprint"]:
                    countback[row["driver_id"]][row["finish"]] += 1
        keys = [(points[d], *(countback[d][i] for i in range(1, 26))) for d in driver_ids]
        return [1 + sum(other > key for other in keys) for key in keys]

    @staticmethod
    def race_summary(race):
        return {k: race[k] for k in ("race_id", "season", "round", "name", "circuit", "date", "qualifying_date", "completed")} | {
            "start": race["start"].isoformat(), "qualifying_start": race["qualifying_start"].isoformat() if race["qualifying_start"] else None}

    def catalog(self):
        now = datetime.now(timezone.utc)
        preferred = next((r for r in self.races if r["start"] > now), self.completed[-1])
        return dict(id="f1", name="Formula 1", kind="race", races=[self.race_summary(r) for r in self.races],
                    seasons=sorted({r["season"] for r in self.races}, reverse=True), default_race=preferred["race_id"],
                    drivers=sorted({row["driver"] for field in self.entries.values() for row in field}),
                    rows=len(self.completed), earliest=self.completed[0]["date"], latest=self.completed[-1]["date"],
                    data_provenance=self.provenance, data_sha256=self.file_hashes, demo=False)
