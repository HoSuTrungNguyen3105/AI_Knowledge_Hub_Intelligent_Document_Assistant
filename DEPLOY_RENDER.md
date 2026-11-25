# Triển khai lên Render

Tài liệu này mô tả cách chạy MindFlow AI trên Render: **2 web service** (backend
FastAPI + frontend Next.js) và **MongoDB Atlas** làm database.

> Vì sao phải tách 2 service: `frontend/next.config.mjs` proxy `/api/v1/*` sang
> `BACKEND_URL` (mặc định `http://127.0.0.1:8000`). Trên Render, trong container
> frontend **không có** backend nào lắng nghe cổng 8000, nên mọi request API sẽ
> lỗi (`ECONNREFUSED`) và trả 502. Backend phải là một service riêng có URL công
> khai.

---

## 0. Đọc đúng triệu chứng 502

Khi gọi `https://<frontend>.onrender.com/api/v1/auth/me` trả về trang 502 của
Render kèm header:

```
x-render-routing: no-deploy
```

thì request **chưa hề vào ứng dụng**. Render edge không có instance nào đang chạy
để chuyển tiếp. Trang HTML tĩnh vẫn mở được vì Next đánh dấu
`cache-control: s-maxage=31536000` và Render/CDN phục vụ bản cache
(`x-nextjs-cache: HIT`), còn `/api/v1/*` không cache nên lộ lỗi thật.

Vì vậy đây **không phải lỗi auth**. Thứ tự kiểm tra:

1. Render Dashboard → service → **Events**: deploy gần nhất có `Deploy failed`,
   `Instance failed`, hay service bị suspend / hết free hours?
2. **Logs**: tìm `ValidationError`, `JWT_SECRET`, `MongoServerSelectionError`,
   `no open ports detected`, `Exited with status 1`.
3. Nếu dịch vụ đang ngủ (free tier), mở lại URL và đợi 30–60 giây rồi thử lại.

---

## 1. Database: MongoDB Atlas

Render không cung cấp MongoDB. `docker-compose.yml` chỉ dùng cho máy local.

1. Tạo cluster miễn phí trên MongoDB Atlas.
2. Tạo user database, lấy chuỗi `mongodb+srv://...`.
3. Network Access → thêm `0.0.0.0/0` (hoặc dải IP của Render) để backend kết nối
   được. Nếu chặn IP, backend chết ngay khi khởi động vì `lifespan_mongo` ping
   database trước khi phục vụ request.

Ký tự đặc biệt trong mật khẩu phải URL-encode.

---

## 2. Backend service (FastAPI)

**New → Web Service → Docker**

| Trường | Giá trị |
|---|---|
| Root Directory | *(để trống, repo root)* |
| Dockerfile Path | `backend/Dockerfile` |
| Docker Context Directory | `backend` |
| Health Check Path | `/api/v1/health` |

Image đã tự đọc biến `PORT` do Render inject (xem `backend/Dockerfile`), nên
không cần đặt cổng thủ công.

### Environment Variables (bắt buộc)

`backend/.env` bị `.gitignore` và **không được COPY vào image**, nên mọi cấu
hình phải nhập trên Render:

| Biến | Ghi chú |
|---|---|
| `MONGODB_URI` | `mongodb+srv://...` của Atlas |
| `MONGODB_DATABASE` | `mindflow_ai` (hoặc tên bạn muốn) |
| `JWT_SECRET` | **Bắt buộc**. Chuỗi ngẫu nhiên ≥ 32 ký tự, không chứa `change`/`your-secret`/`placeholder` |
| `CREDENTIAL_ENCRYPTION_KEY` | Khóa Fernet hợp lệ (xem lệnh bên dưới). Phải giữ cố định để giải mã API key provider đã lưu |
| `APP_ENV` | `production` |
| `COOKIE_SECURE` | `true` |

Tạo secret:

```bash
# JWT_SECRET
python -c "import secrets; print(secrets.token_hex(48))"

# CREDENTIAL_ENCRYPTION_KEY (Fernet)
python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

Không cần đặt `PORT`, `CORS_ORIGINS` hay `HOST`: trình duyệt chỉ gọi same-origin
qua frontend, CORS không tham gia; còn `PORT` do Render cấp.

### Kiểm tra backend độc lập

```bash
curl -i https://<backend>.onrender.com/api/v1/health
# 200 {"status":"ok"}
```

Mở `https://<backend>.onrender.com/docs`. Nếu vẫn 502, xem Logs của **service
backend** — đừng sửa frontend.

Lỗi hay gặp:

| Log | Nguyên nhân |
|---|---|
| `validation error ... jwt_secret Field required` | Thiếu `JWT_SECRET` |
| `JWT_SECRET must be a random secret...` | Secret quá ngắn / chứa từ cấm |
| `CREDENTIAL_ENCRYPTION_KEY must be a Fernet key` | Key sai định dạng |
| `MongoServerSelectionError` | Sai URI hoặc Atlas chưa allow IP |
| `no open ports detected` | Ảnh cũ chưa đọc `$PORT` — deploy lại sau khi pull code mới |

---

## 3. Frontend service (Next.js standalone)

**New → Web Service → Docker**

| Trường | Giá trị |
|---|---|
| Root Directory | *(để trống)* |
| Dockerfile Path | `frontend/Dockerfile` |
| Docker Context Directory | `frontend` |
| Health Check Path | `/login` (hoặc để trống) |

### Environment Variables

| Biến | Giá trị |
|---|---|
| `BACKEND_URL` | `https://<backend>.onrender.com` — **không** có dấu `/` cuối |

`BACKEND_URL` được nhúng vào rewrite **lúc build**. Render truyền env của service
thành Docker build args, và `frontend/Dockerfile` đã khai báo
`ARG BACKEND_URL`, nên chỉ cần đặt biến rồi **Manual Deploy → Clear build cache
& deploy**. Nếu đổi URL backend sau này, phải deploy lại frontend.

`PORT` do Render inject; `frontend/Dockerfile` đã đặt `HOSTNAME=0.0.0.0`.

Frontend cần **web service**, không dùng Static Site: rewrite `/api/v1/*` và SSE
(chat streaming) cần một process Next.js thật.

---

## 4. Kiểm tra end-to-end

```bash
curl -i https://<frontend>.onrender.com/api/v1/health
# phải trả JSON {"status":"ok"} — đây là bằng chứng proxy đã tới backend

curl -i https://<frontend>.onrender.com/api/v1/auth/me
# 401 {"detail":"Not authenticated"} khi chưa đăng nhập — đúng, không còn 502
```

Sau đó mở `https://<frontend>.onrender.com/login`, đăng ký/đăng nhập và kiểm tra
`/settings` để lưu API key provider.

---

## 5. Vì sao vẫn có thể 502 dù cấu hình đúng

- **Free tier ngủ sau ~15 phút**: request đầu tiên đánh thức instance, có thể mất
  30–60 giây và trả 502 trong lúc chờ. Thử lại.
- **Health check fail**: nếu đặt Health Check Path `/api/v1/health` mà Atlas
  không kết nối được, Render coi instance là unhealthy và không route traffic →
  502. Sửa `MONGODB_URI`/Network Access trước.
- **Deploy fail nhưng dịch vụ cũ vẫn chạy**: kiểm tra commit đang deploy có chứa
  thay đổi `Dockerfile` mới chưa.
- **Nhầm service**: gọi `/api/v1/...` trên hostname frontend là đi qua Next
  proxy. Muốn kiểm tra backend, gọi trực tiếp hostname backend.
