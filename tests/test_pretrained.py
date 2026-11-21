import copy
import hashlib
import json
import os
import socket
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app import ROOT
from matchlab.contexts import HistoryIndex
from matchlab.data import Dataset
from matchlab.engine import Engine, default_config
from matchlab.pretrained import PretrainedModels, file_hash
from matchlab.sports import SPORTS


class CausalContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = Engine(default_config(), ROOT)

    def test_historical_example_features_exclude_own_and_future_results_for_every_task(self):
        ds = self.engine.datasets["cricket"]
        index = HistoryIndex(ds)
        cutoff = "2026-09-20"
        for task in ("winner", "team_score", "player_score", "player_threat"):
            examples = index.examples(task, cutoff, 10, 32)
            self.assertGreater(len(examples), 0, task)
            for r in examples:
                self.assertLess(r["date"], cutoff)
                self.assertLessEqual(r["feature_cutoff"], r["date"])
            for r in examples[::8]:
                when = r["feature_cutoff"]
                match = ds.by_id[r["match_id"]]
                # Rebuild using only records already available before this
                # historical match. Future labels cannot affect any feature.
                trimmed = SimpleNamespace(matches=[m for m in ds.matches if m["date"] < when],
                    players=[p for p in ds.players if p["date"] < when], interactions=[p for p in ds.interactions if p["date"] < when])
                prior = HistoryIndex(trimmed)
                a = index.features(match["team"], match["opponent"], when, 10, "neutral")
                b = prior.features(match["team"], match["opponent"], when, 10, "neutral")
                self.assertEqual(a, b)

    def test_future_mutations_do_not_change_player_or_pair_features(self):
        ds = self.engine.datasets["cricket"]
        cutoff = "2026-09-20"
        a, b = ds.teams[:2]
        player, other = sorted(ds.rosters[a])[0], sorted(ds.rosters[b])[0]
        original = HistoryIndex(ds).features(a, b, cutoff, 10, "home", player, other)
        modified = copy.deepcopy(ds)
        for m in modified.matches:
            if m["date"] >= cutoff:
                m.update(team_score=999999, opponent_score=999999, outcome="draw")
        for p in modified.players:
            if p["date"] >= cutoff:
                p["score"] = 999999
        for p in modified.interactions:
            if p["date"] >= cutoff:
                p["successes"] = p["opportunities"]
        self.assertEqual(original, HistoryIndex(modified).features(a, b, cutoff, 10, "home", player, other))

    def test_context_orientations_are_paired_and_labels_reversed(self):
        index = HistoryIndex(self.engine.datasets["tennis"])
        examples = index.examples("winner", "2026-11-10", 5, 24)
        for i in range(0, len(examples), 2):
            a, b = examples[i:i+2]
            self.assertEqual(a["match_id"], b["match_id"])
            self.assertEqual({a["target"], b["target"]}, {"team", "opponent"})
            self.assertEqual(a["features"]["team_recent_avg"], b["features"]["opponent_recent_avg"])

    def test_bad_scoring_configuration_and_missing_checkpoint_are_actionable(self):
        cfg = default_config()
        cfg["sports"]["tennis"]["scoring"] = {"draw": True}
        with self.assertRaisesRegex(ValueError, "cannot use draw"):
            Engine(cfg, ROOT)
        cfg = default_config()
        cfg["sports"]["football"]["models"] = {"winner": dict(format="tabicl_classifier", path="models/missing.ckpt", sha256="0"*64)}
        engine = Engine(cfg, ROOT)
        a, b = engine.datasets["football"].teams[:2]
        result = engine.analyze(dict(sport="football", team=a, opponent=b, cutoff="2026-11-10"))
        self.assertIsNone(result["winner"]["value"])
        self.assertIn("Missing checkpoint", result["winner"]["error"])
        self.assertEqual(result["winner"]["source"], "unavailable")
        cfg = default_config()
        cfg["sports"]["football"]["demo"] = False
        mislabeled = Engine(cfg, ROOT)
        self.assertTrue(mislabeled.datasets["football"].synthetic)
        self.assertTrue(mislabeled.catalog()[0]["demo"])

    def test_model_integrity_and_dataset_integrity_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            model = folder / "config.json"
            model.write_text("changed")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                PretrainedModels({}, ROOT).verify(model, "0"*64)
            (folder / "matches.csv").write_text("modified")
            (folder / "provenance.json").write_text(json.dumps(dict(files={"matches.csv": "0"*64})))
            with self.assertRaisesRegex(ValueError, "Dataset checksum mismatch"):
                Dataset(folder, SPORTS["football"])


@unittest.skipUnless((ROOT / "data/real/tennis/matches.csv").exists(), "One-time public data setup not installed")
class PublicDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = Engine(json.loads((ROOT / "config.pretrained.example.json").read_text()), ROOT)

    def test_all_sports_have_verified_real_records_and_legal_scoring(self):
        for sport, ds in self.engine.datasets.items():
            self.assertFalse(ds.synthetic)
            self.assertFalse(ds.provenance["synthetic"])
            self.assertEqual(ds.provenance["files"], ds.file_hashes)
            if sport in ("tennis", "badminton", "baseball", "cricket"):
                self.assertNotIn("draw", {m["outcome"] for m in ds.matches})
            if sport in ("tennis", "badminton"):
                self.assertTrue(all(max(m["team_score"], m["opponent_score"]) == 2 for m in ds.matches))

    def test_tennis_conservative_availability_excludes_same_tournament(self):
        ds = self.engine.datasets["tennis"]
        index = HistoryIndex(ds)
        for m in ds.matches[::100]:
            if "_supplement-" in m["match_id"]:   # published match day: the result is known that day, never earlier
                self.assertEqual(m["pre_match_date"], m["date"])
            else:                                 # archive: tournament start, results available 14 days later
                self.assertLess(m["pre_match_date"], m["date"])
            for side in (m["team"], m["opponent"]):
                records = index.before(index.sides, side, m["pre_match_date"], 30)
                self.assertTrue(all(r["date"] < m["pre_match_date"] for r in records))

    def test_missing_real_interactions_and_tiny_context_are_explicit(self):
        ds = self.engine.datasets["badminton"]
        examples = self.engine.pretrained.index("badminton", ds).examples("winner", "2018-01-12", 5)
        self.assertLess(len(examples), 24)
        self.assertGreaterEqual(len(self.engine.pretrained.index("badminton", ds).examples("winner", "2026-11-10", 5)), 24)
        for sport in ("football", "baseball", "rugby"):
            self.assertEqual(self.engine.datasets[sport].interactions, [])
            self.assertEqual(self.engine.datasets[sport].players, [])


@unittest.skipUnless(os.environ.get("MATCHLAB_REAL_TESTS") == "1", "Set MATCHLAB_REAL_TESTS=1 to run downloaded-weight CPU inference")
class RealWeightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = Engine(json.loads((ROOT / "config.pretrained.example.json").read_text()), ROOT)
        cls.manifest = json.loads((ROOT / "models/manifest.json").read_text())
        cls.before = {f["path"]: file_hash(ROOT / f["path"]) for f in cls.manifest["files"]}

    @classmethod
    def tearDownClass(cls):
        after = {f["path"]: file_hash(ROOT / f["path"]) for f in cls.manifest["files"]}
        if after != cls.before:
            raise AssertionError("An original model file changed")

    def test_01_real_cpu_inference_all_sports_and_player_targets_offline(self):
        from tools.smoke_real_models import recommended_query
        with socket.socket() as sock, self.assertRaisesRegex(OSError, "Offline mode"):
            sock.connect(("203.0.113.1", 443))
        for sport, ds in self.engine.datasets.items():
            with self.subTest(sport=sport):
                q = recommended_query(ds, sport)
                if sport == "cricket":
                    q["opponent_player"] = "JJ Bumrah"
                a = self.engine.analyze(q)
                self.assertAlmostEqual(sum(a["winner"]["value"].values()), 1, places=5)
                self.assertEqual("draw" in a["winner"]["value"], a["meta"]["draw"])
                self.assertTrue(all(p["source"] == "model" and p["value"] >= 0 for p in a["scores"]))
                if sport in ("cricket", "tennis", "badminton"):
                    self.assertEqual(a["player_score"]["source"], "model")
                    self.assertEqual(a["threat"]["source"], "model")
                    self.assertTrue(0 <= a["threat"]["value"] <= 1)
                    self.assertIsNotNone(a["scoring_form"]["player"]["value"])
                if sport in ("football", "baseball", "rugby"):
                    self.assertIsNone(a["player_score"]["value"])
                    self.assertIsNone(a["threat"]["value"])
                self.assertTrue(all(p["source"] == "model" for p in a["scoring_form"]["teams"]))

    def test_02_real_outputs_are_invariant_to_future_mutations_and_weights_are_frozen(self):
        ds = self.engine.datasets["football"]
        cutoff = "2023-08-01"
        q = dict(team="Arsenal FC", opponent="Brentford FC", cutoff=cutoff, window=5, venue="home")
        spec = self.engine.registries["football"].configs["winner"]
        manager = self.engine.pretrained
        a = manager.predict("football", ds, "winner", spec, [q], self.engine.metadata["football"])[0]
        estimator = manager._estimator(spec)[0]
        def tensor_hash():
            h = hashlib.sha256()
            for name, value in estimator.model_.state_dict().items():
                h.update(name.encode())
                h.update(value.detach().cpu().contiguous().numpy().tobytes())
            return h.hexdigest()
        before = tensor_hash()
        altered = copy.deepcopy(ds)
        for m in altered.matches:
            if m["date"] >= cutoff:
                m.update(team_score=999, opponent_score=888, outcome="team")
        # Clear result cache so a second actual forward pass is required.
        manager.results.clear()
        b = manager.predict("football", altered, "winner", spec, [q], self.engine.metadata["football"])[0]
        self.assertEqual(a["features"], b["features"])
        self.assertEqual(a["value"], b["value"])
        self.assertEqual(before, tensor_hash())
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            manager.predict("football", ds, "winner", {**spec, "sha256": "0"*64}, [q], self.engine.metadata["football"])

    def test_03_no_synthetic_real_model_outputs_or_missing_interaction_fallback(self):
        sport = "cricket"
        ds = copy.deepcopy(self.engine.datasets[sport])
        ds.interactions = []
        q = dict(team="Chennai Super Kings", opponent="Mumbai Indians", player="RD Gaikwad", opponent_player="JJ Bumrah", cutoff="2026-11-10", window=5)
        manager = self.engine.pretrained
        spec = self.engine.registries[sport].configs["player_threat"]
        with self.assertRaisesRegex(ValueError, "interaction data unavailable"):
            manager.predict(sport, ds, "player_threat", spec, [q], self.engine.metadata[sport])
        ds.synthetic = True
        with self.assertRaisesRegex(ValueError, "synthetic"):
            manager.predict(sport, ds, "player_threat", spec, [q], self.engine.metadata[sport])


if __name__ == "__main__":
    unittest.main()
