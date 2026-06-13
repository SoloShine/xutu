import json
from pathlib import Path
from dataclasses import asdict
from .schemas import Event


class EventStore:
    """append-only JSONL event log（单一真相源）。"""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: Event):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")

    def load_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        events = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        return events

    def query(self, tick=None, agent_id=None, event_type=None) -> list[dict]:
        events = self.load_all()
        result = []
        for e in events:
            if tick is not None and e.get("tick") != tick:
                continue
            if agent_id is not None and e.get("agent_id") != agent_id:
                continue
            if event_type is not None and e.get("event_type") != event_type:
                continue
            result.append(e)
        return result