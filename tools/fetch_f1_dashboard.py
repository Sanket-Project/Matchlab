import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen

BASE = 'https://api.jolpi.ca/ergast/f1/current/'

def fetch():
    result = {}
    for name, path in [('drivers', 'driverStandings.json?limit=100'), ('teams', 'constructorStandings.json?limit=100'), ('last', 'last/results.json?limit=100'), ('next', 'next.json')]:
        try:
            with urlopen(Request(BASE + path, headers={'User-Agent': 'MatchLab/1.0', 'Accept': 'application/json'}), timeout=8) as response:
                result[name] = json.load(response)['MRData']
        except (OSError, ValueError, KeyError) as exc:
            result[name] = None
    result['checked_at'] = datetime.now(timezone.utc).isoformat()
    return result

if __name__ == '__main__':
    print(json.dumps(fetch()))
