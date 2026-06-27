"""报告生成任务 API。

本文件提供创建任务、查询任务状态和下载生成报告的 REST 接口，
是前端 upload -> status -> download 流程的后端入口。
"""

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import Job, JobStatus
from app.db.session import get_db
from app.observability.events import log_event
from app.storage.local_storage import LocalStorageService

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    created_at: str
    started_at: str | None
    completed_at: str | None
    download_url: str | None = None
    error_message: str | None = None


def _iso_or_none(value) -> str | None:
    return value.isoformat() if value else None


def _job_to_status_response(job: Job) -> JobStatusResponse:
    """把数据库 Job 转成 API 响应，并只在完成后暴露下载地址。"""
    download_url = f"/jobs/{job.id}/download" if job.status == JobStatus.completed else None
    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        created_at=job.created_at.isoformat(),
        started_at=_iso_or_none(job.started_at),
        completed_at=_iso_or_none(job.completed_at),
        download_url=download_url,
        error_message=job.error_message,
    )


def _get_job_or_404(job_id: str, db: Session) -> Job:
    """按 job_id 查询任务；不存在时返回统一的 404。"""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.post("", response_model=JobCreateResponse, status_code=status.HTTP_202_ACCEPTED)
def create_job(
    template_file: UploadFile = File(...),
    data_file: UploadFile = File(...),
    domain_context_files: list[UploadFile] | None = File(default=None),
    instructions: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> JobCreateResponse:
    """创建报告生成任务，保存上传文件，并立即返回 pending job。"""
    job_id = f"job_{uuid4().hex}"
    storage = LocalStorageService()

    template_path = storage.save_upload(job_id, template_file, "template")
    data_path = storage.save_upload(job_id, data_file, "data")

    domain_paths: list[str] = []
    for index, upload in enumerate(domain_context_files or []):
        domain_path = storage.save_upload(job_id, upload, f"domain_{index + 1}")
        domain_paths.append(str(domain_path))

    job = Job(
        id=job_id,
        status=JobStatus.pending,
        template_path=str(template_path),
        data_path=str(data_path),
        domain_context_paths=domain_paths,
        instructions=instructions,
    )
    db.add(job)
    log_event(
        "job_created",
        job_id,
        db,
        template_filename=template_file.filename,
        data_filename=data_file.filename,
        domain_context_filenames=[upload.filename for upload in domain_context_files or []],
    )
    log_event(
        "file_saved",
        job_id,
        db,
        template_path=str(template_path),
        data_path=str(data_path),
        domain_context_paths=domain_paths,
    )
    db.commit()

    return JobCreateResponse(job_id=job.id, status=job.status)


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db)) -> JobStatusResponse:
    """查询 job 当前状态，供前端刷新后恢复任务进度。"""
    job = _get_job_or_404(job_id, db)
    return _job_to_status_response(job)


@router.get("/{job_id}/download")
def download_job_report(job_id: str, db: Session = Depends(get_db)) -> FileResponse:
    """下载已完成 job 的报告；未完成或失败任务不会返回报告文件。"""
    job = _get_job_or_404(job_id, db)

    if job.status != JobStatus.completed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is {job.status.value}; report is not available",
        )

    if not job.output_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report file not found")

    output_path = Path(job.output_path)
    if not output_path.exists() or not output_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report file not found")

    return FileResponse(
        path=output_path,
        filename=output_path.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
