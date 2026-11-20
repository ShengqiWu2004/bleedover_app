"""Progress events from the pipeline subprocess to the app: one JSON object per stdout line.

Lines without the prefix (library prints, warnings) are shown in the app's log as they are.
"""

import json

PREFIX = "@@event "


def emit(kind: str, **data) -> None:
    print(PREFIX + json.dumps({"kind": kind, **data}, default=str), flush=True)


def parse(line: str) -> dict | None:
    if not line.startswith(PREFIX):
        return None
    try:
        return json.loads(line[len(PREFIX):])
    except ValueError:
        return None
