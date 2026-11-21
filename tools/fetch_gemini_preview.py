"""Call Google Gemini API for match previews & AI second opinions without heavy external dependencies.

Reads GEMINI_API_KEY from CLI, environment, or .env file.
Usage:
  python tools/fetch_gemini_preview.py --prompt "Briefly preview Alcaraz vs Sinner"
  python tools/fetch_gemini_preview.py --stdin < input.json
"""
import argparse
import json
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from matchlab.openrouter_key import get_api_key  # noqa: E402

MODEL = "gemini-3.5-flash-lite"
API_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def generate_gemini(key=None, context=None, instructions=None, as_json=False):
    api_key = key or get_api_key("GEMINI_API_KEY")
    if not api_key:
        return {"error": "Missing GEMINI_API_KEY. Add it to .env or environment variables."}

    prompt = (
        context if isinstance(context, str) else json.dumps(context or {}, ensure_ascii=False)
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 2048,
        },
    }
    if instructions:
        body["systemInstruction"] = {"parts": [{"text": instructions}]}
    if as_json:
        body["generationConfig"]["responseMimeType"] = "application/json"

    url = f"{API_URL}/{MODEL}:generateContent"
    req = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-goog-api-key": api_key,
        },
    )

    try:
        with build_opener().open(req, timeout=45) as res:
            data = json.loads(res.read().decode("utf-8"))
    except HTTPError as err:
        return {"error": f"Gemini API returned HTTP {err.code}: {err.reason}"}
    except (URLError, OSError, ValueError) as err:
        return {"error": f"Connection error reaching Gemini API: {err}"}

    candidates = data.get("candidates") or []
    if not candidates:
        return {"error": "Gemini returned no candidates. Try generating again."}

    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        return {"error": "Gemini returned an empty reply."}

    text = re.sub(r"```(?:json)?\s*", "", text).rstrip("`").strip()
    return {"text": text, "model": MODEL, "web_sources": []}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Call Gemini API for sports previews")
    parser.add_argument("--prompt", default=None, help="Direct prompt text")
    parser.add_argument("--instructions", default=None, help="System instructions")
    parser.add_argument("--key", default=None, help="Gemini API Key override")
    parser.add_argument("--json", action="store_true", help="Expect JSON output")
    parser.add_argument("--stdin", action="store_true", help="Read context payload from stdin")
    args = parser.parse_args()

    context = args.prompt
    if args.stdin:
        try:
            payload = json.loads(sys.stdin.read())
            context = payload.get("context", context)
            if payload.get("instructions"):
                args.instructions = payload.get("instructions")
            if payload.get("key"):
                args.key = payload.get("key")
            if payload.get("json"):
                args.json = True
        except Exception as exc:
            print(json.dumps({"error": f"Invalid JSON on stdin: {exc}"}))
            sys.exit(1)

    result = generate_gemini(
        key=args.key,
        context=context or "Hello",
        instructions=args.instructions,
        as_json=args.json,
    )
    print(json.dumps(result, indent=2))
