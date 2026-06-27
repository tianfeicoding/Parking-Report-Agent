"""报告生成 workflow。

本文件负责串联单个 job 的后台生成流程，包括数据清洗、硬指标计算、
profile、Agent report plan、图表渲染和最终 DOCX 输出。
"""

from sqlalchemy.orm import Session

from app.agent.report_planner import create_report_plan
from app.data.parking_csv_loader import load_parking_csv
from app.db.models import Job, JobStatus, utc_now
from app.metrics.parking_metrics import compute_parking_metrics
from app.observability.events import log_event
from app.profiling.anomaly_detector import detect_anomaly_candidates
from app.profiling.domain_context_loader import load_domain_context
from app.profiling.duration_profiler import build_duration_profile
from app.profiling.payment_profiler import build_payment_profile
from app.report.chart_renderer import ChartRenderer
from app.report.docx_renderer import render_report_docx
from app.report.template_instructions import extract_template_instructions
from app.storage.local_storage import LocalStorageService


def run_report_generation_workflow(job: Job, db: Session) -> Job:
    """执行单个报告生成任务，并把成功或失败状态写回数据库。"""
    storage = LocalStorageService()

    try:
        log_event("workflow_started", job.id, db)
        log_event("data_validation_started", job.id, db, data_path=job.data_path)
        cleaned_data = load_parking_csv(job.data_path)
        log_event("data_validation_completed", job.id, db, row_count=len(cleaned_data.rows))

        metrics = compute_parking_metrics(cleaned_data)
        log_event(
            "metrics_computed",
            job.id,
            db,
            total_transactions=metrics.total_transactions,
            total_receivable=str(metrics.total_receivable),
            total_collected=str(metrics.total_collected),
            total_actual_deductions=str(metrics.total_actual_deductions),
            collection_rate_pct=str(metrics.collection_rate_pct),
            top_payment_method=metrics.top_payment_method.method if metrics.top_payment_method else None,
            top_payment_method_count=metrics.top_payment_method.count if metrics.top_payment_method else None,
        )

        payment_profile = build_payment_profile(cleaned_data)
        duration_profile = build_duration_profile(cleaned_data)
        domain_context = load_domain_context(job.domain_context_paths, job.instructions)
        template_instructions = extract_template_instructions(job.template_path)
        anomaly_candidates = detect_anomaly_candidates(
            cleaned_data,
            metrics,
            payment_profile,
            duration_profile,
        )
        log_event(
            "profiles_computed",
            job.id,
            db,
            payment_method_count=len(payment_profile.payment_methods),
            payment_channel_count=len(payment_profile.payment_channels),
            average_duration_hours=str(duration_profile.average_hours),
            over_12h_count=duration_profile.over_12h_count,
            template_section_count=len(template_instructions.sections),
            anomaly_candidate_count=len(anomaly_candidates),
        )

        log_event("agent_planning_started", job.id, db)
        report_plan = create_report_plan(
            db=db,
            job_id=job.id,
            metrics=metrics,
            payment_profile=payment_profile,
            duration_profile=duration_profile,
            domain_context=domain_context,
            template_instructions=template_instructions,
            anomaly_candidates=anomaly_candidates,
        )
        log_event(
            "agent_planning_completed",
            job.id,
            db,
            planner_mode=report_plan.planner_mode,
            fallback_used=report_plan.fallback_used,
            observation_count=len(report_plan.observations),
            recommendation_count=len(report_plan.recommendations),
        )

        log_event("chart_rendering_started", job.id, db)
        charts = ChartRenderer(storage.output_dir(job.id) / "charts").render_all(
            payment_profile,
            duration_profile,
        )
        log_event(
            "chart_rendering_completed",
            job.id,
            db,
            chart_ids=list(charts.keys()),
        )

        log_event("docx_generation_started", job.id, db, mode="python_docx")
        generated_at = utc_now()
        output_path = render_report_docx(
            output_path=storage.output_dir(job.id) / "parking_detail_analysis_report.docx",
            template_path=job.template_path,
            template_instructions=template_instructions,
            metrics=metrics,
            payment_profile=payment_profile,
            duration_profile=duration_profile,
            report_plan=report_plan,
            charts=charts,
            data_period=_format_data_period(cleaned_data),
            generated_at=generated_at,
            on_template_fallback=lambda reason: log_event(
                "template_rendering_fallback_used",
                job.id,
                db,
                reason=reason,
            ),
        )

        job.status = JobStatus.completed
        job.output_path = str(output_path)
        job.error_message = None
        job.completed_at = utc_now()

        log_event("job_completed", job.id, db, output_path=str(output_path))
        db.commit()
        return job
    except Exception as exc:
        db.rollback()
        job = db.get(Job, job.id)
        if job is not None:
            job.status = JobStatus.failed
            job.error_message = str(exc)
            job.completed_at = utc_now()
            log_event("job_failed", job.id, db, error=str(exc))
            db.commit()
        raise


def _format_data_period(cleaned_data) -> str:
    """根据清洗后的收费时间计算报告数据周期。"""
    if not cleaned_data.rows:
        return "无有效数据"
    dates = [row.charged_at.date() for row in cleaned_data.rows]
    start = min(dates).isoformat()
    end = max(dates).isoformat()
    return start if start == end else f"{start} – {end}"
