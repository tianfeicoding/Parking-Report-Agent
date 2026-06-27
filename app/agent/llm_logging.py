"""LLM 调用日志。

本文件统一记录 LLM 调用的 prompt、response、model、latency 和错误，
满足面试作业对 Agent 行为可调试性的要求。
"""

from time import perf_counter
from typing import Callable, TypeVar

from sqlalchemy.orm import Session

from app.db.models import LLMCallLog
from app.observability.events import log_event
from app.observability.sanitizer import sanitize_for_logging

T = TypeVar("T")


def run_with_llm_logging(
    *,
    db: Session,
    job_id: str,
    agent_name: str,
    model: str,
    prompt: str,
    call: Callable[[], T],
    response_to_text: Callable[[T], str],
) -> T:
    """执行一次 LLM 调用并记录结构化日志和数据库日志。"""
    started = perf_counter()
    logged_prompt = str(sanitize_for_logging(prompt))
    log_event("llm_call_started", job_id, db, agent_name=agent_name, model=model, prompt=logged_prompt)

    try:
        result = call()
        latency_ms = int((perf_counter() - started) * 1000)
        response_text = response_to_text(result)
        logged_response = str(sanitize_for_logging(response_text))
        db.add(
            LLMCallLog(
                job_id=job_id,
                agent_name=agent_name,
                model=model,
                prompt=logged_prompt,
                response=logged_response,
                latency_ms=latency_ms,
                usage=None,
                status="completed",
            )
        )
        log_event(
            "llm_call_completed",
            job_id,
            db,
            agent_name=agent_name,
            model=model,
            response=logged_response,
            latency_ms=latency_ms,
        )
        return result
    except Exception as exc:
        latency_ms = int((perf_counter() - started) * 1000)
        logged_error = str(sanitize_for_logging(str(exc)))
        db.add(
            LLMCallLog(
                job_id=job_id,
                agent_name=agent_name,
                model=model,
                prompt=logged_prompt,
                response=None,
                latency_ms=latency_ms,
                usage=None,
                status="failed",
                error_message=logged_error,
            )
        )
        log_event(
            "llm_call_failed",
            job_id,
            db,
            agent_name=agent_name,
            model=model,
            latency_ms=latency_ms,
            error=logged_error,
        )
        raise
