"""结构化事件日志。

本文件提供统一的 JSON 日志入口，同时可选把事件写入 job_events 表，
用于追踪用户请求和 worker 生命周期。
"""

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import JobEvent
from app.observability.sanitizer import sanitize_for_logging

logger = logging.getLogger("park_agent.events")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def log_event(event: str, job_id: str | None = None, db: Session | None = None, **payload: Any) -> None:
    """输出结构化 JSON 日志，并在提供数据库 session 时写入 JobEvent。"""
    sanitized_payload = sanitize_for_logging(payload)
    log_payload = {"event": event, "job_id": job_id, **sanitized_payload}
    logger.info(json.dumps(log_payload, ensure_ascii=False, default=str))

    if db is not None and job_id is not None:
        db.add(JobEvent(job_id=job_id, event=event, payload=sanitized_payload))
