"""后台 worker 入口。

本文件负责轮询数据库中的 pending job，claim 后执行报告生成 workflow，
并维护 running/completed/failed 状态流转。
"""

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Job, JobStatus, utc_now
from app.db.session import SessionLocal, init_db
from app.observability.events import log_event
from app.workflows.report_generation import run_report_generation_workflow

POLL_INTERVAL_SECONDS = 2


def claim_next_pending_job(db: Session) -> Job | None:
    """领取一个 pending job，并立即标记为 running，避免重复处理。"""
    job = db.execute(
        select(Job)
        .where(Job.status == JobStatus.pending)
        .order_by(Job.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()

    if job is None:
        return None

    job.status = JobStatus.running
    job.started_at = utc_now()
    job.error_message = None
    log_event("job_claimed_by_worker", job.id, db)
    db.commit()
    db.refresh(job)
    return job


def run_once() -> bool:
    """执行一次 worker 轮询；处理到 job 返回 True，没有 pending job 返回 False。"""
    with SessionLocal() as db:
        job = claim_next_pending_job(db)
        if job is None:
            return False

        try:
            run_report_generation_workflow(job, db)
        except Exception:
            # workflow 内部已经记录 failed 状态；这里吞掉异常，避免 worker 进程退出。
            return True

        return True


def main() -> None:
    """启动 worker 主循环，持续轮询 pending job。"""
    init_db()
    while True:
        processed = run_once()
        if not processed:
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
