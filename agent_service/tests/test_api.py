from pathlib import Path

from fastapi.testclient import TestClient

from agent.message import AgentMessage, MessageType
from agent_service.api import create_app
from agent_service.config import Settings
from agent_service.repository import SQLiteRunRepository
from agent_service.runtime import RuntimeResult
from agent_service.schemas import CreateRunRequest
from agent_service.service import RunService


class FakeRuntime:
    async def run(self, prompt: str, project_id: str | None = None) -> RuntimeResult:
        return RuntimeResult(
            result=f"completed: {prompt}",
            messages=[
                AgentMessage(
                    type=MessageType.ASSISTANT,
                    content={"text": "fake response", "project_id": project_id},
                )
            ],
        )


def create_test_client(tmp_path: Path) -> TestClient:
    database_path = tmp_path / "agent_service.sqlite3"
    repository = SQLiteRunRepository(database_path)
    service = RunService(repository, FakeRuntime())
    app = create_app(Settings(database_path=database_path), repository, service)
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


def test_internal_token_is_required_when_configured(tmp_path: Path) -> None:
    database_path = tmp_path / "agent_service.sqlite3"
    repository = SQLiteRunRepository(database_path)
    service = RunService(repository, FakeRuntime())
    settings = Settings(database_path=database_path, internal_token="secret")
    app = create_app(settings, repository, service)
    client = TestClient(app)

    assert client.get("/api/internal/health").status_code == 401
    assert client.get(
        "/api/internal/health", headers={"X-Service-Token": "secret"}
    ).status_code == 200


def test_cancelled_run_is_not_overwritten_by_execution(tmp_path: Path) -> None:
    database_path = tmp_path / "agent_service.sqlite3"
    repository = SQLiteRunRepository(database_path)
    service = RunService(repository, FakeRuntime())
    run = service.create(CreateRunRequest(prompt="cancel me"))
    run_id = run.run_id
    service.cancel(run_id)
    import asyncio

    asyncio.run(service.execute(run_id))
    assert repository.get_run(run_id).status.value == "CANCELLED"
