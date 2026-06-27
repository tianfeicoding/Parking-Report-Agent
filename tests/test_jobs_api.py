"""Job API 端到端接口测试。

本文件覆盖 submit -> status -> download 的 API-level 主流程。
报告生成过程在测试中用临时 docx 文件模拟，避免依赖 worker 或真实 LLM。
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import jobs as jobs_api
from app.db.models import Job, JobEvent, JobStatus, LLMCallLog, utc_now
from app.db.session import SessionLocal
from app.main import app
from app.storage.local_storage import LocalStorageService


@pytest.fixture(autouse=True)
def clean_jobs_table():
    # 每个 API 测试前后清理数据库，避免 Docker 本地运行历史 job 影响断言。
    _delete_all_jobs()
    yield
    _delete_all_jobs()


@pytest.fixture
def client(tmp_path, monkeypatch):
    class TestStorageService(LocalStorageService):
        def __init__(self) -> None:
            super().__init__(root_dir=str(tmp_path / "storage"))

    monkeypatch.setattr(jobs_api, "LocalStorageService", TestStorageService)
    with TestClient(app) as test_client:
        yield test_client


def _delete_all_jobs() -> None:
    # 按外键依赖顺序删除测试数据。
    db = SessionLocal()
    try:
        db.query(LLMCallLog).delete()
        db.query(JobEvent).delete()
        db.query(Job).delete()
        db.commit()
    finally:
        db.close()


def _mark_job_completed(job_id: str, output_path: Path) -> None:
    # 模拟后台生成完成，只改变可观察状态和下载文件路径。
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        assert job is not None
        now = utc_now()
        job.status = JobStatus.completed
        job.started_at = now
        job.completed_at = now
        job.output_path = str(output_path)
        db.commit()
    finally:
        db.close()


def test_submit_status_and_download_with_mocked_generation(client, tmp_path):
    response = client.post(
        "/jobs",
        files={
            "template_file": (
                "template.docx",
                b"fake template content",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            "data_file": ("data.csv", b"col1,col2\n1,2\n", "text/csv"),
        },
        data={"instructions": "testing instructions"},
    )

    assert response.status_code == 202
    created = response.json()
    assert created["job_id"].startswith("job_")
    assert created["status"] == "pending"

    status_response = client.get(f"/jobs/{created['job_id']}")
    assert status_response.status_code == 200
    pending_payload = status_response.json()
    assert pending_payload["status"] == "pending"
    assert pending_payload["download_url"] is None

    blocked_download = client.get(f"/jobs/{created['job_id']}/download")
    assert blocked_download.status_code == 409

    fake_report = tmp_path / "generated-report.docx"
    fake_report.write_bytes(b"fake generated docx")
    _mark_job_completed(created["job_id"], fake_report)

    completed_response = client.get(f"/jobs/{created['job_id']}")
    assert completed_response.status_code == 200
    completed_payload = completed_response.json()
    assert completed_payload["status"] == "completed"
    assert completed_payload["download_url"] == f"/jobs/{created['job_id']}/download"
    assert completed_payload["error_message"] is None

    download_response = client.get(completed_payload["download_url"])
    assert download_response.status_code == 200
    assert download_response.content == b"fake generated docx"
    assert (
        download_response.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
