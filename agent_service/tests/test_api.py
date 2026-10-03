from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from agent.message import AgentMessage, MessageType
from agent_service.api import create_app
from agent_service.config import Settings
from agent_service.domain import Run, RunMessage
from agent_service.runtime import RuntimeResult
from agent_service.schemas import CreateRunRequest
from agent_service.service import RunService


class MemoryRunRepository:
    def __init__(self):
        self.runs = {}
        self.messages = {}

    def initialize(self):
        pass

    def create_run(self, run):
        self.runs[run.run_id] = run
        return run

    def get_run(self, run_id):
        return self.runs.get(run_id)

    def update_run(self, run):
        self.runs[run.run_id] = run
        return run

    def append_messages(self, run_id, messages):
        current = len(self.messages.setdefault(run_id, []))
        now = datetime.now(timezone.utc)
        self.messages[run_id].extend(
            RunMessage(
                sequence=current + index,
                message_type=message_type,
                content=content,
                created_at=now,
            )
            for index, (message_type, content) in enumerate(messages, start=1)
        )

    def list_messages(self, run_id):
        return self.messages.get(run_id, [])


class FakeRuntime:
    async def run(self, prompt: str, project_id: str | None = None, context: list[dict[str, str]] | None = None) -> RuntimeResult:
        return RuntimeResult(
            result=f"completed: {prompt}" if not context else f"completed: {prompt}; previous: {context[-1]['content']}",
            messages=[
                AgentMessage(
                    type=MessageType.ASSISTANT,
                    content={"text": "fake response", "project_id": project_id},
                )
            ],
        )


def create_test_client(tmp_path: Path) -> TestClient:
    repository = MemoryRunRepository()
    service = RunService(repository, FakeRuntime())
    app = create_app(Settings(), repository, service)
    return TestClient(app)


def test_run_lifecycle_and_messages(tmp_path: Path) -> None:
    client = create_test_client(tmp_path)

    created = client.post(
        "/api/internal/runs",
        json={"project_id": "project-1", "prompt": "analyze"},
    )

    assert created.status_code == 202
    run_id = created.json()["run_id"]

    detail = client.get(f"/api/internal/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "COMPLETED"
    assert detail.json()["result"] == "completed: analyze"

    messages = client.get(f"/api/internal/runs/{run_id}/messages")
    assert messages.status_code == 200
    assert messages.json()["messages"][0]["message_type"] == "assistant"


def test_missing_run_returns_404(tmp_path: Path) -> None:
    client = create_test_client(tmp_path)
    response = client.get("/api/internal/runs/missing")
    assert response.status_code == 404


def test_run_receives_conversation_context(tmp_path: Path) -> None:
    client = create_test_client(tmp_path)
    created = client.post(
        "/api/internal/runs",
        json={"project_id": "p1", "conversation_id": "c1", "prompt": "follow up",
              "context": [{"role": "user", "content": "first question"},
                          {"role": "assistant", "content": "first answer"}]},
    )
    assert created.status_code == 202
    run = client.get(f"/api/internal/runs/{created.json()['run_id']}").json()
    assert run["conversation_id"] == "c1"
    assert run["result"] == "completed: follow up; previous: first answer"


def test_internal_token_is_required_when_configured(tmp_path: Path) -> None:
    repository = MemoryRunRepository()
    service = RunService(repository, FakeRuntime())
    settings = Settings(internal_token="secret")
    app = create_app(settings, repository, service)
    client = TestClient(app)

    assert client.get("/api/internal/health").status_code == 401
    assert client.get(
        "/api/internal/health", headers={"X-Service-Token": "secret"}
    ).status_code == 200


def test_cancelled_run_is_not_overwritten_by_execution(tmp_path: Path) -> None:
    repository = MemoryRunRepository()
    service = RunService(repository, FakeRuntime())
    run = service.create(CreateRunRequest(prompt="cancel me"))
    run_id = run.run_id
    service.cancel(run_id)
    import asyncio

    asyncio.run(service.execute(run_id))
    assert repository.get_run(run_id).status.value == "CANCELLED"
