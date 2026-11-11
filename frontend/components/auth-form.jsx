"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, Eye, EyeOff, LoaderCircle, LockKeyhole } from "lucide-react";
import { useAuthForm } from "../hooks/use-auth-form";

export function AuthForm({ mode }) {
  const registering = mode === "register";
  const { submit, busy, error } = useAuthForm(mode);
  const [showPassword, setShowPassword] = useState(false);
  return <div className="auth-form-wrap">
    <span className="eyebrow">Bắt đầu từ những điều bạn biết</span>
    <h1>{registering ? "Tạo không gian của bạn" : "Chào mừng trở lại"}</h1>
    <p className="muted auth-description">{registering ? "Một tài khoản riêng để quản lý tài liệu và kết nối tri thức." : "Đăng nhập để tiếp tục xây dựng thư viện tri thức của bạn."}</p>
    <form onSubmit={submit} className="auth-form" aria-busy={busy}>
      <fieldset disabled={busy}>
        {registering && <label>Họ và tên<input name="name" autoComplete="name" placeholder="Nguyễn Minh An" required maxLength={100} /></label>}
        <label>Email<input name="email" type="email" autoComplete="email" placeholder="ban@example.com" required maxLength={254} spellCheck={false} /></label>
        <label>Mật khẩu<span className="password-field"><input name="password" type={showPassword ? "text" : "password"} autoComplete={registering ? "new-password" : "current-password"} placeholder={registering ? "Từ 10 đến 128 ký tự" : "Nhập mật khẩu của bạn"} required minLength={registering ? 10 : undefined} maxLength={128} aria-describedby={registering ? "password-hint" : undefined} /><button type="button" className="icon-button" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"} aria-pressed={showPassword}>{showPassword ? <EyeOff size={18} /> : <Eye size={18} />}</button></span></label>
        {registering && <><p className="field-hint" id="password-hint">Dùng mật khẩu riêng, tối thiểu 10 ký tự.</p><label>Nhập lại mật khẩu<input name="confirmPassword" type={showPassword ? "text" : "password"} autoComplete="new-password" placeholder="Nhập lại mật khẩu" required minLength={10} maxLength={128} /></label></>}
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="button primary auth-submit" type="submit">{busy ? <><LoaderCircle size={18} className="spin" />Đang xử lý…</> : <>{registering ? "Tạo tài khoản" : "Đăng nhập"}<ArrowRight size={18} /></>}</button>
      </fieldset>
    </form>
    <p className="auth-switch">{registering ? "Đã có tài khoản?" : "Chưa có tài khoản?"} <Link href={registering ? "/login" : "/register"}>{registering ? "Đăng nhập" : "Tạo tài khoản"}</Link></p>
    <div className="auth-security"><LockKeyhole size={15} aria-hidden="true" /><span>Phiên đăng nhập được bảo vệ bằng cookie HttpOnly.</span></div>
  </div>;
}
