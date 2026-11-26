"use client";

import { useCallback, useEffect, useState } from "react";
import { Download, Github, Loader2, Plus } from "lucide-react";
import {
  getWorkflowTemplatesError,
  workflowTemplatesService,
} from "../../services/workflow-templates";

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("vi-VN");
}

export default function TemplateSources() {
  const [sources, setSources] = useState([]);
  const [logs, setLogs] = useState([]);
  const [pendingCount, setPendingCount] = useState(null);
  const [totalCount, setTotalCount] = useState(null);
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [repoUrl, setRepoUrl] = useState("");

  const load = useCallback(async () => {
    try {
      const [sourceList, logList, pending, total] = await Promise.all([
        workflowTemplatesService.listSources(),
        workflowTemplatesService.listImports(),
        workflowTemplatesService.countTemplates({ review_status: "pending_review" }),
        workflowTemplatesService.countTemplates({}),
      ]);
      setSources(sourceList || []);
      setLogs(logList || []);
      setPendingCount(pending);
      setTotalCount(total);
    } catch {
      // Section is auxiliary; keep whatever is already shown.
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function addDefault() {
    setBusy("default");
    setError("");
    setNote("");
    try {
      await workflowTemplatesService.ensureDefaultSource();
      setNote("Đã đăng ký nguồn awesome-n8n-templates. Bấm Nhập ngay để lấy toàn bộ workflow.");
      load();
    } catch (err) {
      setError(getWorkflowTemplatesError(err, "Không đăng ký được nguồn mặc định."));
    } finally {
      setBusy("");
    }
  }

  async function addCustom() {
    if (!repoUrl.trim()) return;
    setBusy("custom");
    setError("");
    setNote("");
    try {
      await workflowTemplatesService.createSource({ repo_url: repoUrl.trim() });
      setRepoUrl("");
      setNote("Đã thêm nguồn. Bấm Nhập ngay ở nguồn đó để lấy workflow.");
      load();
    } catch (err) {
      setError(getWorkflowTemplatesError(err, "Không thêm được nguồn."));
    } finally {
      setBusy("");
    }
  }

  async function runImport(source) {
    setBusy(source.id);
    setError("");
    setNote(`Đang bắt đầu nhập từ ${source.repo}…`);
    try {
      const started = await workflowTemplatesService.importSource(source.id);
      // The server imports in the background (a full repo takes minutes);
      // poll the import log every 3 seconds and show real progress.
      let finalLog = started;
      for (let attempt = 0; attempt < 240 && finalLog.status === "running"; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 3000));
        const logs = await workflowTemplatesService.listImports();
        const current = (logs || []).find((item) => item.id === started.id);
        if (!current) continue;
        finalLog = current;
        if (current.status === "running") {
          const done =
            current.created + current.updated + current.unchanged + current.rejected;
          setNote(
            `Đang nhập từ ${source.repo}: đã xử lý ${done}${current.found ? `/${current.found}` : ""} file · mới ${current.created} · cập nhật ${current.updated} · loại ${current.rejected}…`,
          );
        }
      }
      setNote(
        finalLog.status === "completed"
          ? `Nhập xong ${source.repo}: tìm thấy ${finalLog.found} file · tải ${finalLog.downloaded} · mới ${finalLog.created} · cập nhật ${finalLog.updated} · giữ nguyên ${finalLog.unchanged} · loại ${finalLog.rejected}. Template mới vào trạng thái chờ duyệt, chưa chạy gì cả.`
          : finalLog.status === "running"
            ? `Việc nhập vẫn đang chạy ở server. Quay lại sau ít phút và xem Lịch sử nhập gần đây để biết kết quả.`
            : `Nhập thất bại (${finalLog.error || "không rõ lý do"}). Hãy thử lại sau.`,
      );
      load();
    } catch (err) {
      setError(getWorkflowTemplatesError(err, "Nhập thất bại. Hãy thử lại sau."));
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="fx-card">
      <h2>
        <Github size={17} /> Nguồn template GitHub
      </h2>
      <p className="fx-run-meta">
        Nhập workflow thật từ kho GitHub vào Thư viện mẫu dùng chung: hệ thống tải JSON, phân tích
        node, quét secret hardcode và rủi ro, lưu kèm ghi công theo license. Template nhập vào ở
        trạng thái chờ duyệt và không bao giờ tự chạy.
        {totalCount != null
          ? ` Hiện thư viện có ${totalCount} template, ${pendingCount ?? 0} đang chờ duyệt.`
          : ""}
      </p>
      {error ? (
        <p className="fx-alert" role="alert">
          {error}
        </p>
      ) : null}
      {note ? <p className="fx-run-meta">{note}</p> : null}

      {sources.length === 0 ? (
        <p className="fx-run-meta">Chưa có nguồn nào. Đăng ký nguồn mặc định để bắt đầu:</p>
      ) : (
        sources.map((source) => (
          <div key={source.id} className="n8n-node">
            <h3>
              {source.name}
              <span style={{ marginLeft: "auto" }} className="fx-actions">
                <button
                  type="button"
                  className="fx-btn primary"
                  onClick={() => runImport(source)}
                  disabled={busy === source.id}
                >
                  {busy === source.id ? (
                    <Loader2 size={15} className="spin" />
                  ) : (
                    <Download size={15} />
                  )}
                  Nhập ngay
                </button>
              </span>
            </h3>
            <p className="fx-run-meta">
              {source.repo_url} · nhánh {source.branch} · {source.template_count} template
              {source.license ? ` · License ${source.license}` : ""}
              {source.last_import_at ? ` · Nhập gần nhất ${formatTime(source.last_import_at)}` : ""}
            </p>
            {source.attribution ? <p className="fx-run-meta">{source.attribution}</p> : null}
          </div>
        ))
      )}

      <div className="fx-actions">
        <button type="button" className="fx-btn" onClick={addDefault} disabled={busy === "default"}>
          {busy === "default" ? <Loader2 size={15} className="spin" /> : <Plus size={15} />}
          Đăng ký nguồn mặc định (awesome-n8n-templates)
        </button>
      </div>
      <label className="fx-field">
        Thêm kho GitHub khác (https://github.com/owner/repo)
        <span className="fx-actions">
          <input
            className="fx-input"
            type="text"
            value={repoUrl}
            onChange={(event) => setRepoUrl(event.target.value)}
            placeholder="https://github.com/owner/repo"
          />
          <button
            type="button"
            className="fx-btn"
            onClick={addCustom}
            disabled={busy === "custom" || !repoUrl.trim()}
          >
            {busy === "custom" ? <Loader2 size={15} className="spin" /> : <Plus size={15} />}
            Thêm nguồn
          </button>
        </span>
      </label>

      {logs.length ? (
        <div className="n8n-node">
          <h3>Lịch sử nhập gần đây</h3>
          {logs.slice(0, 5).map((log) => (
            <p key={log.id} className="fx-run-meta">
              {formatTime(log.started_at)} · {log.source_repo} · {log.status} · thấy {log.found} ·
              mới {log.created} · cập nhật {log.updated} · giữ nguyên {log.unchanged} · loại{" "}
              {log.rejected}
              {log.error ? ` · lỗi: ${log.error}` : ""}
            </p>
          ))}
        </div>
      ) : null}
    </section>
  );
}
