import csv
import tempfile
import unittest
from pathlib import Path

from tools.import_public_data import badminton_game, import_bwf, match


class BadmintonImportTests(unittest.TestCase):
    def test_score_validation_name_normalization_and_cross_source_deduplication(self):
        original = match("shuttle-1", "2019-01-01", "CHEN Long", "Viktor AXELSEN", 2, 1)
        columns = ("date", "discipline", "retired", "winner", "team_one_players", "team_two_players",
                   "game_1_score", "game_2_score", "game_3_score", "tournament", "tournament_type", "round")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ms.csv"
            with path.open("w", encoding="utf-8", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(columns)
                writer.writerow(["01-01-2019", "MS", "False", "2", "Viktor Axelsen", "Long Chen",
                                 "21-11", "20-22", "28-30", "Open", "BWF Tour Super 500", "Final"])
                writer.writerow(["02-01-2019", "MS", "False", "1", "Long Chen", "New Player",
                                 "21-5", "30-29", "", "Open", "BWF Tour Super 500", "Final"])
            added, skipped = import_bwf(path, [original])
        self.assertEqual(skipped, {"duplicate_date_and_players": 1})
        self.assertEqual(original["round"], "Final")
        self.assertEqual((added[0]["team"], added[0]["opponent"], added[0]["team_score"], added[0]["opponent_score"]),
                         ("CHEN Long", "PLAYER New", 2, 0))
        with self.assertRaises(ValueError):
            badminton_game("30-27")
