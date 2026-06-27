// 停车报告生成前端入口。
// 本文件实现上传模板/数据、提交 job、查询状态和下载报告的最小可用流程。

import React, { FormEvent, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const lastJobStorageKey = "park-agent:last-job-id";

type JobStatusValue = "pending" | "running" | "completed" | "failed";

type JobCreateResponse = {
  job_id: string;
  status: JobStatusValue;
};

type JobStatusResponse = {
  job_id: string;
  status: JobStatusValue;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  download_url: string | null;
  error_message: string | null;
};

function App() {
  const [apiStatus, setApiStatus] = useState<"checking" | "ok" | "unavailable">("checking");
  const [templateFile, setTemplateFile] = useState<File | null>(null);
  const [dataFile, setDataFile] = useState<File | null>(null);
  const [domainFiles, setDomainFiles] = useState<File[]>([]);
  const [instructions, setInstructions] = useState("");
  const [jobIdInput, setJobIdInput] = useState(() => localStorage.getItem(lastJobStorageKey) ?? "");
  const [activeJob, setActiveJob] = useState<JobStatusResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isChecking, setIsChecking] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const canSubmit = templateFile !== null && dataFile !== null && !isSubmitting;
  const downloadUrl = useMemo(() => {
    if (!activeJob?.download_url) {
      return null;
    }
    return `${apiBaseUrl}${activeJob.download_url}`;
  }, [activeJob]);

  useEffect(() => {
    fetch(`${apiBaseUrl}/health`)
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then(() => setApiStatus("ok"))
      .catch(() => setApiStatus("unavailable"));

    const savedJobId = localStorage.getItem(lastJobStorageKey);
    if (savedJobId) {
      void fetchJobStatus(savedJobId, { silent: true });
    }
  }, []);

  useEffect(() => {
    if (!activeJob || activeJob.status === "completed" || activeJob.status === "failed") {
      return;
    }

    const timer = window.setInterval(() => {
      void fetchJobStatus(activeJob.job_id, { silent: true });
    }, 2000);
    return () => window.clearInterval(timer);
  }, [activeJob?.job_id, activeJob?.status]);

  async function submitJob(event: FormEvent<HTMLFormElement>) {
    // 提交用户上传文件并创建后台 job。
    event.preventDefault();
    if (!templateFile || !dataFile) {
      setMessage("请先选择模板文件和 CSV 数据文件。");
      return;
    }

    setIsSubmitting(true);
    setMessage(null);
    const formData = new FormData();
    formData.append("template_file", templateFile);
    formData.append("data_file", dataFile);
    domainFiles.forEach((file) => formData.append("domain_context_files", file));
    if (instructions.trim()) {
      formData.append("instructions", instructions.trim());
    }

    try {
      const response = await fetch(`${apiBaseUrl}/jobs`, {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        throw new Error(`提交失败：HTTP ${response.status}`);
      }
      const payload = (await response.json()) as JobCreateResponse;
      localStorage.setItem(lastJobStorageKey, payload.job_id);
      setJobIdInput(payload.job_id);
      await fetchJobStatus(payload.job_id, { silent: true });
      setMessage("任务已提交。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "提交失败。");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function fetchJobStatus(jobId: string, options: { silent?: boolean } = {}) {
    // 查询 job 状态；页面刷新后也可以通过 job id 恢复进度。
    const normalizedJobId = jobId.trim();
    if (!normalizedJobId) {
      setMessage("请输入 job id。");
      return;
    }

    if (!options.silent) {
      setIsChecking(true);
      setMessage(null);
    }

    try {
      const response = await fetch(`${apiBaseUrl}/jobs/${normalizedJobId}`);
      if (!response.ok) {
        throw new Error(`查询失败：HTTP ${response.status}`);
      }
      const payload = (await response.json()) as JobStatusResponse;
      localStorage.setItem(lastJobStorageKey, payload.job_id);
      setJobIdInput(payload.job_id);
      setActiveJob(payload);
      if (!options.silent) {
        setMessage("状态已更新。");
      }
    } catch (error) {
      if (!options.silent) {
        setMessage(error instanceof Error ? error.message : "查询失败。");
      }
    } finally {
      if (!options.silent) {
        setIsChecking(false);
      }
    }
  }

  return (
    <main className="page">
      <header className="topbar">
        <div>
          <h1>停车明细分析报告生成</h1>
          <p>上传模板和停车明细数据，后台生成 Word 分析报告。</p>
        </div>
        <div className={`api-pill api-pill-${apiStatus}`}>
          <span>API</span>
          <strong>{apiStatus}</strong>
        </div>
      </header>

      <section className="layout">
        <form className="panel form-panel" onSubmit={submitJob}>
          <h2>提交任务</h2>

          <label className="field">
            <span>报告模板 `.docx`</span>
            <input
              type="file"
              accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              onChange={(event) => setTemplateFile(event.target.files?.[0] ?? null)}
            />
          </label>

          <label className="field">
            <span>停车数据 `.csv`</span>
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => setDataFile(event.target.files?.[0] ?? null)}
            />
          </label>

          <label className="field">
            <span>领域知识文件</span>
            <input
              type="file"
              multiple
              accept=".txt,.md,.docx"
              onChange={(event) => setDomainFiles(Array.from(event.target.files ?? []))}
            />
          </label>

          <label className="field">
            <span>处理说明</span>
            <textarea
              rows={4}
              value={instructions}
              onChange={(event) => setInstructions(event.target.value)}
              placeholder="例如：会员积分可能是正常营销核销，避免直接判定为违规。"
            />
          </label>

          <button className="primary-button" type="submit" disabled={!canSubmit}>
            {isSubmitting ? "提交中..." : "提交生成"}
          </button>
        </form>

        <section className="panel status-panel">
          <h2>任务状态</h2>
          <div className="query-row">
            <label className="field compact-field">
              <span>Job ID</span>
              <input
                type="text"
                value={jobIdInput}
                onChange={(event) => setJobIdInput(event.target.value)}
                placeholder="job_xxx"
              />
            </label>
            <button
              className="secondary-button"
              type="button"
              onClick={() => void fetchJobStatus(jobIdInput)}
              disabled={isChecking}
            >
              {isChecking ? "查询中..." : "查询"}
            </button>
          </div>

          {message && <div className="message">{message}</div>}

          {activeJob ? (
            <div className="job-card">
              <div className="job-card-header">
                <span className={`status-badge status-${activeJob.status}`}>{activeJob.status}</span>
                <code>{activeJob.job_id}</code>
              </div>
              <dl className="job-meta">
                <div>
                  <dt>创建时间</dt>
                  <dd>{formatDate(activeJob.created_at)}</dd>
                </div>
                <div>
                  <dt>开始时间</dt>
                  <dd>{formatDate(activeJob.started_at)}</dd>
                </div>
                <div>
                  <dt>完成时间</dt>
                  <dd>{formatDate(activeJob.completed_at)}</dd>
                </div>
              </dl>

              {activeJob.status === "completed" && downloadUrl && (
                <a className="download-link" href={downloadUrl}>
                  下载 Word 报告
                </a>
              )}

              {activeJob.status === "failed" && (
                <div className="error-box">{activeJob.error_message ?? "任务失败，未返回错误详情。"}</div>
              )}
            </div>
          ) : (
            <div className="empty-state">提交任务后会在这里显示状态，也可以输入已有 job id 查询。</div>
          )}
        </section>
      </section>
    </main>
  );
}

function formatDate(value: string | null) {
  // 将后端 ISO 时间转成浏览器本地时间显示。
  if (!value) {
    return "-";
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(new Date(value));
}

createRoot(document.getElementById("root")!).render(<App />);
