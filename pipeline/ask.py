"""Ask one question from the command line, through the configured model provider.

    .venv/bin/python pipeline/ask.py "How many active users are there?"

Settings come from the environment. If a file named .env sits in the repository root, its
KEY=value lines are read first. Values already set in the environment win. The file is
ignored by Git. See .env.example for the names.

Prints the chat payload as JSON.
"""

import json
import os
import sys
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent
ROOT = PIPELINE.parent
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

from chat import ChatError, answer, model_from_env  # noqa: E402


def load_dotenv(path=ROOT / ".env"):
    """Read KEY=value lines into os.environ without overriding values already set."""
    path = Path(path)
    if not path.exists():
        return []
    loaded = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ and value:
            os.environ[key] = value
            loaded.append(key)
    return loaded


def main(argv):
    if len(argv) != 2 or not argv[1].strip():
        print('Usage: python pipeline/ask.py "your question"', file=sys.stderr)
        return 2
    load_dotenv()
    os.environ.setdefault("CHAT_PROVIDER", "gemini")
    model = model_from_env()
    if model is None:
        print(
            "No model key found. Put GEMINI_API_KEY=... in a file named .env in the repository "
            "root (see .env.example), then run this again.",
            file=sys.stderr,
        )
        return 1
    try:
        payload = answer(argv[1], model)
    except ChatError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
