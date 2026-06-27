"""可观测性和日志脱敏测试。

本文件验证生命周期事件和 LLM 调用日志会以结构化形式写入，
且不会把 API key、token 等敏感信息写入 stdout/数据库日志。
"""

import pytest

from app.agent.llm_logging import run_with_llm_logging
from app.db.models import JobEvent, LLMCallLog
from app.observability.events import log_event
from app.observability.sanitizer import REDACTED, sanitize_for_logging


class FakeDb:
    def __init__(self) -> None:
        self.added = []

    def add(self, item) -> None:
        self.added.append(item)


def test_sanitize_for_logging_redacts_sensitive_values():
    payload = {
        "OPENAI_API_KEY": "sk-thisShouldNeverAppear123456",
        "nested": {
            "authorization": "Bearer tokenShouldNeverAppear123456",
            "message": "api_key=sk-anotherSecretValue123456",
        },
    }

    sanitized = sanitize_for_logging(payload)

    assert sanitized["OPENAI_API_KEY"] == REDACTED
    assert sanitized["nested"]["authorization"] == REDACTED
    assert "sk-anotherSecretValue" not in sanitized["nested"]["message"]
    assert REDACTED in sanitized["nested"]["message"]


def test_log_event_writes_sanitized_job_event_payload():
    db = FakeDb()

    log_event(
        "job_created",
        "job_test",
        db,
        api_key="sk-secretValueThatShouldBeRedacted",
        data_filename="data.csv",
    )

    event = db.added[0]
    assert isinstance(event, JobEvent)
    assert event.payload["api_key"] == REDACTED
    assert event.payload["data_filename"] == "data.csv"


def test_run_with_llm_logging_redacts_prompt_and_response():
    db = FakeDb()

    result = run_with_llm_logging(
        db=db,
        job_id="job_test",
        agent_name="ReportPlannerAgent",
        model="test-model",
        prompt="请分析 OPENAI_API_KEY=sk-secretPromptValue123456",
        call=lambda: {"text": "response has sk-secretResponseValue123456"},
        response_to_text=lambda value: value["text"],
    )

    llm_log = [item for item in db.added if isinstance(item, LLMCallLog)][0]
    assert result["text"].startswith("response")
    assert "sk-secretPromptValue" not in llm_log.prompt
    assert "sk-secretResponseValue" not in llm_log.response
    assert REDACTED in llm_log.prompt
    assert REDACTED in llm_log.response


def test_run_with_llm_logging_redacts_failure_error():
    db = FakeDb()

    with pytest.raises(RuntimeError):
        run_with_llm_logging(
            db=db,
            job_id="job_test",
            agent_name="ReportPlannerAgent",
            model="test-model",
            prompt="normal prompt",
            call=lambda: (_ for _ in ()).throw(
                RuntimeError("upstream rejected Authorization=Bearer secretTokenValue123456")
            ),
            response_to_text=str,
        )

    llm_log = [item for item in db.added if isinstance(item, LLMCallLog)][0]
    assert "secretTokenValue" not in llm_log.error_message
    assert REDACTED in llm_log.error_message
