import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class FakeDirectory:
    failing_names: set[str] = field(default_factory=set)
    transient_failures: dict[str, int] = field(default_factory=dict)
    activation_failures: int = 0
    hospitals: dict[int, dict[str, Any]] = field(default_factory=dict)
    create_attempts: Counter[str] = field(default_factory=Counter)
    activated_batches: list[str] = field(default_factory=list)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path == "/hospitals/":
            return self._create(json.loads(request.content))
        if request.method == "PATCH" and path.endswith("/activate"):
            return self._activate(path.split("/")[3])
        return httpx.Response(404)

    def _create(self, payload: dict[str, Any]) -> httpx.Response:
        name = payload["name"]
        self.create_attempts[name] += 1
        if name in self.failing_names:
            return httpx.Response(422, json={"detail": "rejected"})
        if self.transient_failures.get(name, 0) > 0:
            self.transient_failures[name] -= 1
            return httpx.Response(503, text="unavailable")

        hospital_id = len(self.hospitals) + 1
        hospital = {"id": hospital_id, **payload, "active": False}
        self.hospitals[hospital_id] = hospital
        return httpx.Response(200, json=hospital)

    def _activate(self, batch_id: str) -> httpx.Response:
        if self.activation_failures > 0:
            self.activation_failures -= 1
            return httpx.Response(500, text="boom")
        for hospital in self.hospitals.values():
            if hospital["creation_batch_id"] == batch_id:
                hospital["active"] = True
        self.activated_batches.append(batch_id)
        return httpx.Response(200, json={"batch_id": batch_id})
