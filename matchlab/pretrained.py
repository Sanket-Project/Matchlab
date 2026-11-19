"""Dedicated official TabICLv2 and Chronos-Bolt CPU adapters. No optimizers,
backpropagation, fine-tuning, cloud calls, or weight writes occur here.
"""
import hashlib
import importlib.metadata
import importlib.util
import json
import math
from collections import OrderedDict
from pathlib import Path
from .contexts import HistoryIndex, SIDE_FEATURES, PLAYER_FEATURES, THREAT_FEATURES
from .data import local_path

FORMATS = {"tabicl_classifier": "tabicl", "tabicl_regressor": "tabicl"}


def file_hash(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def inspect_tabicl(task, spec, root):
    path = local_path(spec.get("path"), root)
    if not path.is_file():
        raise ValueError(f"Missing checkpoint: {path}. Run tools/setup_assets.py --models once with internet access.")
    if spec.get("format") != ("tabicl_classifier" if task == "winner" else "tabicl_regressor"):
        raise ValueError("Winner requires TabICL classifier; score/threat tasks require TabICL regressor")
    if not spec.get("sha256") or len(spec["sha256"]) != 64:
        raise ValueError("Configure the publisher-verified SHA-256 for this original checkpoint")
    if importlib.util.find_spec("tabicl") is None:
        raise ValueError("TabICL runtime missing. Restart with .venv\\Scripts\\python.exe app.py")
    return dict(task=task, state="available", message="Official local TabICLv2; CPU; checksum verified before inference; no weight training", path=str(path), format=spec["format"])


class PretrainedModels:
    def __init__(self, config, root):
        self.config, self.root = config or {}, root
        self.indexes, self.verified = {}, {}
        self.estimators, self.results = {}, OrderedDict()
        self.pipeline = None

    def index(self, sport, ds):
        key = (sport, id(ds))
        if key not in self.indexes:
            self.indexes[key] = HistoryIndex(ds)
        return self.indexes[key]

    def verify(self, path, expected):
        if not path.is_file():
            raise ValueError(f"Missing model file: {path}. Re-run the one-time model setup; no automatic download is attempted.")
        st = path.stat()
        key = (str(path), st.st_size, st.st_mtime_ns, expected)
        if key not in self.verified:
            digest = file_hash(path)
            if not expected or digest.lower() != expected.lower():
                raise ValueError(f"SHA-256 mismatch: {path.name}. Restore the publisher file; inference blocked.")
            self.verified[key] = digest
        return self.verified[key]

    def _estimator(self, spec):
        from .offline import enable_offline
        enable_offline()
        import torch
        from tabicl import TabICLClassifier, TabICLRegressor
        path = local_path(spec["path"], self.root)
        digest = self.verify(path, spec["sha256"])
        estimators = int(self.config.get("n_estimators", 2))
        if not 1 <= estimators <= 4:
            raise ValueError("CPU n_estimators must be 1–4 for this laptop")
        key = (str(path), digest, estimators)
        if key not in self.estimators:
            torch.set_num_threads(4)
            cls = TabICLClassifier if spec["format"] == "tabicl_classifier" else TabICLRegressor
            self.estimators[key] = cls(model_path=str(path), allow_auto_download=False,
                checkpoint_version=path.name, device="cpu", use_amp=False, use_fa3=False,
                n_estimators=estimators, batch_size=1, kv_cache=False, n_jobs=4,
                offload_mode=False, random_state=42, verbose=False)
        return self.estimators[key], digest

    def predict(self, sport, ds, task, spec, requests, meta, context_cutoff=None):
        """Batch focal/opponent score queries in a single official forward pass."""
        inspect_tabicl(task, spec, self.root)
        if ds.synthetic:
            raise ValueError("Real pretrained inference is disabled for synthetic demonstration datasets")
        path = local_path(spec["path"], self.root)
        digest = self.verify(path, spec["sha256"])
        cutoff, window = context_cutoff or requests[0]["cutoff"], requests[0]["window"]
        if any((q["cutoff"] != cutoff if context_cutoff is None else q["cutoff"] < cutoff) or q["window"] != window for q in requests):
            raise ValueError("Batch queries must share a window and cannot precede their frozen historical context cutoff")
        max_rows = int(self.config.get("max_context_rows", 192))
        if not 24 <= max_rows <= 512 or max_rows % 2:
            raise ValueError("max_context_rows must be an even number from 24 to 512")
        index = self.index(sport, ds)
        inputs = [index.features(q["team"], q["opponent"], q["cutoff"], window, q.get("venue", "neutral"), q.get("player"), q.get("opponent_player")) for q in requests]
        for f in inputs:
            if min(f["team_matches"], f["opponent_matches"]) < 2:
                raise ValueError("Insufficient history: each side needs at least 2 completed matches before the cutoff. Choose a later date or add real results.")
            if task in ("player_score", "player_threat") and f["player_appearances"] < 2:
                raise ValueError("Insufficient player history: at least 2 recorded appearances for this side are required before the cutoff.")
            if task == "player_threat" and (not ds.interactions or f["player_action_rate"] is None or f["opponent_action_conceded_rate"] is None):
                raise ValueError("Player interaction data unavailable before this date: supply actual directional interactions for both selected players. No threat prediction is fabricated.")
        examples = index.examples(task, cutoff, window, max_rows)
        if len(examples) < 24:
            raise ValueError(f"Insufficient labeled context: {len(examples)} eligible {task} examples; need at least 24. Add real historical data or choose a later cutoff.")
        if task == "winner":
            observed = {r["target"] for r in examples}
            draw = "draw" in observed if sport == "cricket" else meta["draw"]
            required = {"team", "opponent", "draw"} if draw else {"team", "opponent"}
            if observed != required:
                raise ValueError(f"Outcome context needs all legal classes {sorted(required)}; observed {sorted(observed)}. Expand real history; missing draw probabilities cannot be invented.")
        feature_names = SIDE_FEATURES if task in ("winner", "team_score") else PLAYER_FEATURES if task == "player_score" else THREAT_FEATURES
        # Cache depends on actual examples and query values, never on future rows.
        payload = dict(sport=sport, task=task, checkpoint=digest, cutoff=cutoff, window=window,
                       examples=examples, inputs=inputs, settings=self.config, scoring=meta)
        identity = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if identity in self.results:
            self.results.move_to_end(identity)
            return self.results[identity]
        import numpy as np
        import torch
        def matrix(fs):
            return np.asarray([[np.nan if f.get(k) is None else f[k] for k in feature_names] for f in fs], dtype=np.float32)
        X = matrix([r["features"] for r in examples])
        y = np.asarray([r["target"] for r in examples])
        estimator, digest = self._estimator(spec)
        # Official fit prepares labels, preprocessing and context. It does NOT
        # update pretrained transformer weights. Never use FinetunedTabICL.
        with torch.inference_mode():
            estimator.fit(X, y)
            if task == "winner":
                raw = estimator.predict_proba(matrix(inputs))
                values = [dict(zip(map(str, estimator.classes_), map(float, row))) for row in raw]
            else:
                raw = estimator.predict(matrix(inputs))
                values = [float(v) for v in raw]
        provenance = dict(context_rows=len(examples), context_matches=len({r["match_id"] for r in examples}),
                          context_start=examples[0]["date"], context_end=examples[-1]["date"],
                          context_sha256=hashlib.sha256(json.dumps(examples, sort_keys=True).encode()).hexdigest(),
                          context_cutoff=cutoff, feature_names=feature_names,
                          missing_values="Official TabICL NaN handling; no made-up head-to-head or player values",
                          method="Frozen pretrained weights; official fit() supplies historical in-context examples only",
                          runtime=importlib.metadata.version("tabicl"), device="cpu", n_estimators=int(self.config.get("n_estimators", 2)))
        out = []
        for q, f, value in zip(requests, inputs, values):
            if task == "winner":
                if any(not math.isfinite(v) or v < 0 or v > 1 for v in value.values()) or abs(sum(value.values()) - 1) > 1e-4:
                    raise ValueError("TabICL returned invalid outcome probabilities")
                raw_value, adjustment = value, "None"
            else:
                if not math.isfinite(value):
                    raise ValueError("TabICL returned a non-finite regression result")
                raw_value = value
                value = max(0.0, value)
                ceiling = 1 if task == "player_threat" else meta.get("max_score") if task == "team_score" else None
                if ceiling is not None:
                    value = min(float(ceiling), value)
                adjustment = "Clipped to nonnegative score" if ceiling is None else f"Clipped to [0, {ceiling}] legal target range"
            target = ("Expected match outcome probability" if task == "winner" else
                      f"Expected focal-side {meta['unit']} vs selected opponent" if task == "team_score" else
                      f"Expected {meta['player_unit']} per recorded appearance vs selected side" if task == "player_score" else
                      f"Expected next-match success fraction: {meta['threat']}. Equal weight per historical pair-match, not per action; not calibrated event probability.")
            out.append(dict(value=value, raw_value=raw_value, adjustment=adjustment, source="model", model=path.name,
                            sha256=digest, target=target, features=f, provenance={**provenance, "feature_cutoff": q["cutoff"]}))
        self.results[identity] = out
        while len(self.results) > 16:
            self.results.popitem(last=False)
        return out

    def chronos_status(self):
        folder = local_path(self.config.get("chronos_path", "models/chronos-bolt-small"), self.root)
        return dict(task="scoring_form", state="available" if all((folder / n).is_file() for n in ("config.json", "model.safetensors")) and importlib.util.find_spec("chronos") else "unavailable",
                    message="Chronos-Bolt Small: next-appearance scoring form; opponent is not an input", path=str(folder))

    def forecast(self, ds, requests, meta):
        if ds.synthetic:
            raise ValueError("Chronos real-model forecasts are disabled for synthetic data")
        from .offline import enable_offline
        enable_offline()
        import torch
        from chronos import ChronosBoltPipeline
        folder = local_path(self.config.get("chronos_path", "models/chronos-bolt-small"), self.root)
        manifest_path = local_path(self.config.get("manifest", "models/manifest.json"), self.root)
        if not manifest_path.is_file():
            raise ValueError("Missing model manifest. Re-run tools/setup_assets.py --models to record publisher checksums.")
        manifest = json.loads(manifest_path.read_text())
        manifest_files = {(self.root / f["path"]).resolve(): f for f in manifest["files"]}
        digests = {}
        for name in ("config.json", "model.safetensors"):
            path = (folder / name).resolve()
            if path not in manifest_files:
                raise ValueError(f"{name} is absent from the verified local manifest")
            digests[name] = self.verify(path, manifest_files[path]["sha256"])
        eligible = []
        for q in requests:
            if q.get("player"):
                records = [p for p in ds.players if p["player"] == q["player"] and p["team"] == q["team"] and p["date"] < q["cutoff"]][-64:]
            else:
                records = ds.history(q["team"], q["cutoff"])[-64:]
            if len(records) < 8:
                eligible.append(None)
            else:
                eligible.append(records)
        if not any(eligible):
            raise ValueError("Insufficient chronological scoring history: Chronos needs at least 8 pre-cutoff appearances per selected team/player.")
        identity = (str(folder), tuple(digests.values()))
        if getattr(self, "pipeline_identity", None) != identity:
            torch.set_num_threads(4)
            self.pipeline = ChronosBoltPipeline.from_pretrained(str(folder), device_map="cpu", torch_dtype=torch.float32,
                                                               local_files_only=True, trust_remote_code=False)
            self.pipeline_identity = identity
        contexts = [torch.tensor([r["score"] for r in records], dtype=torch.float32) for records in eligible if records]
        with torch.inference_mode():
            quantiles, _ = self.pipeline.predict_quantiles(contexts, prediction_length=1, quantile_levels=[.1, .5, .9])
        outputs, i = [], 0
        for q, records in zip(requests, eligible):
            if records is None:
                outputs.append(dict(value=None, source="unavailable", error="Chronos requires at least 8 pre-cutoff appearances for this series; add real history or choose another player/date."))
                continue
            raw = [float(v) for v in quantiles[i, 0].tolist()]
            i += 1
            if not all(math.isfinite(v) for v in raw):
                raise ValueError("Chronos returned non-finite quantiles")
            ceiling = None if q.get("player") else meta.get("max_score")
            vals = [max(0.0, min(float(ceiling), v) if ceiling is not None else v) for v in raw]
            outputs.append(dict(value=vals[1], q10=vals[0], q90=vals[2], raw_quantiles=raw,
                adjustment="Quantiles clipped to nonnegative scores and sport ceiling if applicable", source="model",
                model="Amazon Chronos-Bolt Small", sha256=digests["model.safetensors"],
                target="Next appearance scoring-form median; opponent, venue and elapsed time are not inputs. Quantiles are uncalibrated model quantiles, not sports confidence levels.",
                provenance=dict(history_count=len(records), history_start=records[0]["date"], history_end=records[-1]["date"], cutoff=q["cutoff"],
                                history_sha256=hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest(),
                                files=digests, runtime=importlib.metadata.version("chronos-forecasting"), device="cpu", step="one match/appearance, irregular calendar spacing ignored")))
        return outputs
