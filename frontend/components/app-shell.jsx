"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { LayoutDashboard, LibraryBig, MessagesSquare, Bot, NotebookPen, Settings2, Menu, X, LogOut, ChevronRight, PanelLeftClose, ShieldCheck, Columns2, Users, GitBranch, Search, Bell } from "lucide-react";
import { Brand } from "./brand";
import { useSession } from "../stores/session";
import { useLogout } from "../hooks/use-logout";
import { initials } from "../utils/format";
import { APP_NAME, APP_STAGE } from "../utils/app-config";

const navigation = [
  { href: "/dashboard", label: "Tổng quan", icon: LayoutDashboard },
  { href: "/chat", label: "AI Chat", icon: MessagesSquare },
  { href: "/compare", label: "Compare AI", icon: Columns2 },
  { href: "/agents", label: "Agent Studio", icon: Bot },
  { href: "/agents/teams", label: "Agent Teams", icon: Users },
  { href: "/agents/workflows", label: "Workflows", icon: GitBranch },
  { href: "/knowledge", label: "Kho kiến thức", icon: LibraryBig, upcoming: true },
  { href: "/notes", label: "Ghi chú", icon: NotebookPen, upcoming: true },
  { href: "/settings", label: "Cài đặt AI", icon: Settings2 },
];

const isActivePath = (pathname, href) => pathname === href || (href !== "/agents" && typeof pathname === "string" && pathname.startsWith(`${href}/`));

function SidebarContent({ pathname, onNavigate, mobile = false }) {
  return <><div className="sidebar-brand"><Link href="/dashboard" onClick={onNavigate} aria-label={`${APP_NAME} — Tổng quan`}><Brand /></Link>{mobile && <button className="icon-button" onClick={onNavigate} aria-label="Đóng menu"><PanelLeftClose size={20} /></button>}</div>
    <div className="workspace-label"><span className="workspace-icon">K</span><div>Không gian cá nhân<small>Chỉ bạn có quyền truy cập</small></div></div>
    <nav aria-label={mobile ? "Điều hướng trên điện thoại" : "Điều hướng chính"} className="main-nav">{navigation.map(({ href, label, icon: Icon, upcoming }) => <Link key={href} href={href} onClick={onNavigate} className={`nav-item ${isActivePath(pathname, href) ? "active" : ""}`} aria-current={isActivePath(pathname, href) ? "page" : undefined}><Icon size={19} strokeWidth={1.7} /><span>{label}</span>{upcoming && <span className="nav-dot" title="Giai đoạn tiếp theo" aria-label="Chưa triển khai" />}</Link>)}</nav>
    <div className="sidebar-bottom"><div className="build-note"><span className="status-dot" /><span>{APP_STAGE}</span></div><p>Nền tảng hôm nay.<br />Tri thức kết nối ngày mai.</p></div>
  </>;
}

export function AppShell({ children }) {
  const pathname = usePathname();
  const user = useSession((state) => state.user);
  const { logout, busy } = useLogout();
  const [menuOpen, setMenuOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [online, setOnline] = useState(null);
  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/health").then((r) => { if (!cancelled) setOnline(r.ok); }).catch(() => { if (!cancelled) setOnline(false); });
    return () => { cancelled = true; };
  }, []);
  const searchResults = query.trim() ? navigation.filter((item) => item.label.toLowerCase().includes(query.trim().toLowerCase())) : [];
  const dialog = useRef(null);
  const isActive = (href) => pathname === href || (href !== "/agents" && pathname.startsWith(`${href}/`));
  const title = navigation.find((item) => isActive(item.href))?.label || "Không gian làm việc";
  useEffect(() => {
    if (menuOpen) dialog.current?.showModal();
    else dialog.current?.close();
  }, [menuOpen]);
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Chuyển đến nội dung</a>
    <aside className="sidebar"><SidebarContent pathname={pathname} /></aside>
    <dialog ref={dialog} className="mobile-drawer" aria-label="Menu điều hướng" onCancel={() => setMenuOpen(false)} onClick={(event) => { if (event.target === event.currentTarget) setMenuOpen(false); }}><div className="drawer-content"><SidebarContent pathname={pathname} onNavigate={() => setMenuOpen(false)} mobile /></div></dialog>
    <div className="workspace-main"><header className="topbar"><div className="breadcrumbs"><button className="icon-button mobile-menu" aria-label="Mở menu điều hướng" aria-expanded={menuOpen} onClick={() => setMenuOpen(true)}>{menuOpen ? <X size={22} /> : <Menu size={22} />}</button><span className="breadcrumb-parent">Không gian làm việc</span><ChevronRight size={14} className="breadcrumb-parent" /><span>{title}</span></div><div className="topbar-search"><Search size={16} /><input aria-label="Tìm nhanh trang" placeholder="Search anything... (Ctrl + K)" value={query} onChange={(event) => setQuery(event.target.value)} />{searchResults.length > 0 && <div className="topbar-search-results">{searchResults.map((item) => <Link key={item.href} href={item.href} onClick={() => setQuery("")}>{item.label}</Link>)}</div>}</div><div className="topbar-account"><span className="system-status"><span className="status-dot" style={online === false ? { background: "#dc2626" } : undefined} />{online === null ? "System …" : online ? "System Online" : "System Offline"}</span><Link className="icon-button" href="/agents/workflows" aria-label="Hoạt động workflow gần đây" title="Workflows"><Bell size={18} /></Link><span className="private-label"><ShieldCheck size={15} />Riêng tư</span><span className="avatar" title={user?.name} aria-label={`Tài khoản ${user?.name}`}>{initials(user?.name)}</span><button className="icon-button logout-button" onClick={logout} disabled={busy} aria-label={busy ? "Đang đăng xuất" : "Đăng xuất"} title="Đăng xuất"><LogOut size={18} /></button></div></header>
      <main id="main-content" className="page-content">{children}</main>
      {/* <footer className="app-footer"><span>{APP_NAME}</span><span>{APP_STAGE}</span></footer> */}
    </div>
  </div>;
}
