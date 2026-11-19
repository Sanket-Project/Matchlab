import unittest

from matchlab import cricket_ratings as cr


def match(day, teams, winner, intl=False, runs=(160, 140)):
    return {"day": day, "fmt": 1, "gender": "male", "intl": intl, "teams": list(teams), "winner": winner, "adjusted": False,
            "innings": [{"team": teams[0], "runs": runs[0], "wickets": 6, "balls": 120}, {"team": teams[1], "runs": runs[1], "wickets": 8, "balls": 120}]}


class Ratings(unittest.TestCase):
    def test_winners_rise_and_only_earlier_matches_count(self):
        games = [match(day, ("Lions", "Tigers"), "Lions") for day in range(1, 21)]
        ratings, played = {}, {}
        seen = [(ra, rb) for _, ra, rb, _ in cr.walk(games, "short", False, before_day=11, ratings=ratings, played=played)]
        self.assertEqual((len(seen), seen[0]), (10, (cr.START, cr.START)))       # first match is predicted from nothing
        self.assertGreater(ratings["lions"], ratings["tigers"])
        self.assertEqual(played["lions"], 10)

    def test_associate_nations_start_lower_than_full_members(self):
        ratings = {}
        list(cr.walk([match(1, ("India", "Nepal"), "India", intl=True)], "short", False, ratings=ratings, played={}))
        first = next(cr.walk([match(1, ("India", "Nepal"), "India", intl=True)], "short", False))
        self.assertEqual((first[1], first[2]), (cr.START, cr.ASSOCIATE_START))

    def test_blend_fades_to_the_live_simulation(self):
        weights, edge = (0.3, 0.9), cr.log_odds(1700, 1500)
        before = cr.blend(0.5, edge, weights)
        self.assertGreater(before, 0.6)                                          # the rating edge counts before the start
        self.assertAlmostEqual(cr.blend(0.2, edge, weights, share=0.0), 0.2, places=6)   # at the end only the score counts
        self.assertTrue(0.2 < cr.blend(0.2, edge, weights, share=0.5) < before)


if __name__ == "__main__":
    unittest.main()
