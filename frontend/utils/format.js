export function initials(name = "") {
  return name.trim().split(/\s+/).filter(Boolean).slice(-2).map((word) => word[0]).join("").toUpperCase() || "U";
}

export function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}

export function formatCount(value) {
  return new Intl.NumberFormat("vi-VN").format(value ?? 0);
}

export function formatActivity(activity) {
  const labels = { "auth.register": "Đã tạo tài khoản", "auth.login": "Đã đăng nhập" };
  return Object.hasOwn(labels, activity.action) ? labels[activity.action] : activity.description;
}
