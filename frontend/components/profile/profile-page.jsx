"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  CalendarDays,
  FileText,
  KeyRound,
  LibraryBig,
  LogOut,
  Mail,
  MessagesSquare,
  Save,
  Sparkles,
} from "lucide-react";
import { authService } from "../../services/auth";
import { fetchDashboard } from "../../services/dashboard";
import { getErrorMessage } from "../../services/api";
import { useLogout } from "../../hooks/use-logout";
import { useSession } from "../../stores/session";
import { useNotice } from "../../stores/notice";
import { formatCount, formatDate, initials } from "../../utils/format";

export function ProfilePage() {
  const user = useSession((state) => state.user);
  const acceptUser = useSession((state) => state.acceptUser);
  const show = useNotice((state) => state.show);
  const { logout, busy: logoutBusy } = useLogout();
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [stats, setStats] = useState(null);

  useEffect(() => {
    if (user?.name) setName(user.name);
  }, [user?.name]);

  useEffect(() => {
    let active = true;
    fetchDashboard()
      .then((data) => {
        if (active) setStats(data);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  async function onSave(event) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || saving) return;
    setSaving(true);
    setError("");
    try {
      const updated = await authService.updateProfile({ name: trimmed });
      acceptUser(updated);
      show("Đã cập nhật hồ sơ.");
    } catch (failure) {
      setError(getErrorMessage(failure));
    } finally {
      setSaving(false);
    }
  }

  if (!user) {
    return (
      <section className="pf-shell">
        <p className="muted">Đang tải hồ sơ…</p>
      </section>
    );
  }

  const statCards = [
    { icon: FileText, label: "Tài liệu", value: stats?.total_documents },
    {
      icon: LibraryBig,
      label: "Kho kiến thức",
      value: stats?.total_knowledge_bases,
    },
    {
      icon: MessagesSquare,
      label: "Cuộc hội thoại",
      value: stats?.total_conversations,
    },
    {
      icon: Sparkles,
      label: "Lượt gọi AI",
      value: stats?.ai_requests_usage,
    },
  ];

  return (
    <section className="pf-shell">
      <div className="pf-card pf-head">
        <span className="pf-avatar">{initials(user.name)}</span>
        <div className="pf-head-info">
          <h2>{user.name}</h2>
          <p>
            <Mail size={14} /> {user.email}
          </p>
          <p>
            <CalendarDays size={14} /> Thành viên từ{" "}
            {formatDate(user.created_at)}
          </p>
        </div>
        <button
          type="button"
          className="button secondary"
          onClick={logout}
          disabled={logoutBusy}
        >
          <LogOut size={16} /> Đăng xuất
        </button>
      </div>

      <div className="pf-stats">
        {statCards.map((card) => (
          <div key={card.label} className="pf-card pf-stat">
            <card.icon size={19} />
            <strong>
              {card.value === undefined || card.value === null
                ? "—"
                : formatCount(card.value)}
            </strong>
            <span>{card.label}</span>
          </div>
        ))}
      </div>

      <div className="pf-card">
        <h3>Thông tin tài khoản</h3>
        <form className="pf-form" onSubmit={onSave}>
          <label>
            Họ và tên
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={100}
              required
              placeholder="Tên hiển thị của bạn"
            />
          </label>
          <label>
            Email
            <input value={user.email} disabled readOnly />
          </label>
          <label>
            Mã người dùng
            <input value={user.id} disabled readOnly className="pf-mono" />
          </label>
          {error ? (
            <p className="form-error" role="alert">
              {error}
            </p>
          ) : null}
          <button
            type="submit"
            className="button primary"
            disabled={saving || name.trim() === user.name}
          >
            <Save size={16} /> {saving ? "Đang lưu…" : "Lưu thay đổi"}
          </button>
        </form>
        <p className="pf-note">
          Đổi API key của các provider AI tại{" "}
          <Link href="/settings">
            <KeyRound size={13} /> Cài đặt AI
          </Link>
          . Mật khẩu hiện chưa đổi được từ giao diện — tính năng đổi mật
          khẩu sẽ bổ sung ở đợt sau.
        </p>
      </div>
    </section>
  );
}
