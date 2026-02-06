from dataclasses import dataclass, field
from datetime import datetime
import json
from typing import Any, Dict
import uuid

@dataclass
class Event:
    type: str  # Ex: "device.action", "system.startup", "user.command"
    source: str # Ex: "frontend", "brain", "system"
    payload: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_json(self):
        return json.dumps(self.__dict__)

    @staticmethod
    def from_json(json_str):
        data = json.loads(json_str)
        return Event(**data)
