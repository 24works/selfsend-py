# selfsend

自托管的 Resend 兼容 API。让部署在 Cloudflare Workers 上的
[melody-auth](../melody-auth) 通过 HTTP 调用你自己的 SMTP 服务发邮件，
无需购买 Resend。

## 工作原理

melody-auth 的 `ResendMailer`（`server/src/services/email/resend.ts`）会向
`POST /emails` 发送：

```
Authorization: bearer <RESEND_API_KEY>
Content-Type: application/json

{
  "from": "DisplayName <sender@example.com>",
  "to": ["receiver@example.com"],
  "subject": "...",
  "html": "..."
}
```

本服务接收同样格式的请求，校验 API Key 后通过配置好的 SMTP 服务器发送，
并返回 Resend 格式的响应（HTTP 200 + `{"id": "..."}`）。

melody-auth 只需设置：

```
EMAIL_PROVIDER_NAME=resend
RESEND_API_KEY=re_你的selfsend密钥
RESEND_SENDER_ADDRESS=noreply@yourdomain.com
```

（`resend.ts` 中的 URL 已改为你的 selfsend 地址。）

## 安装与运行

```bash
cd selfsend
.venv/Scripts/activate            # Windows; Linux 为 source .venv/bin/activate
pip install -r requirements.txt

python scripts/generate_key.py    # 生成 API Key，形如 re_xxxxxxxx

Copy-Item .env.example .env       # 然后编辑 .env，至少配置:
                                  #   SELFSEND_API_KEYS
                                  #   SMTP_HOST / SMTP_PORT / 账号密码等

python run.py                     # 默认监听 127.0.0.1:8787
```

## 安全设计

- **API Key 鉴权**：请求必须带 `Authorization: Bearer <key>`，服务端使用
  `secrets.compare_digest` 常量时间比较，防时序攻击。scheme 大小写不敏感
  （melody-auth 发送的是小写 `bearer`）。
- **速率限制**：每个 Key 每分钟默认 60 次，超出返回 429，防暴力枚举。
- **发件人域名白名单**：`SELFSEND_ALLOWED_FROM_DOMAINS` 限制 from 域名，
  防止 Key 泄露后被冒充其他域名发信（建议务必设置）。
- **收件人/体积上限**：默认单请求最多 50 收件人、2MB 请求体。
- **响应面最小化**：关闭 OpenAPI 文档端点，日志只记录 Key 指纹不记录明文。
- **TLS**：服务只监听 `127.0.0.1`，公网 HTTPS 由反向代理（Caddy/Nginx）
  终结。**不要**将 8787 直接暴露公网，否则 API Key 会明文传输。

反代示例（Caddy，自动 HTTPS）：

```
selfsend.iicemeta.com {
    reverse_proxy 127.0.0.1:8787
}
```

## API

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | `/health` | 无 | 健康检查 |
| POST | `/emails` | Bearer Key | 发送邮件（Resend 兼容） |

`POST /emails` 支持 `from`、`to`/`cc`/`bcc`（字符串或数组）、`subject`、
`html`/`text`、`reply_to`、`headers`、`tags`、`attachments`（base64）。
错误响应为 Resend 风格：`{"name": "...", "message": "..."}`，状态码
401（鉴权失败）/ 422（参数错误）/ 429（限流）/ 502（SMTP 投递失败）。

## 部署到 Linux 服务器

```ini
# /etc/systemd/system/selfsend.service
[Unit]
Description=selfsend (Resend-compatible SMTP gateway)
After=network.target

[Service]
WorkingDirectory=/opt/selfsend
ExecStart=/opt/selfsend/.venv/bin/python run.py
Restart=always
EnvironmentFile=-/opt/selfsend/.env

[Install]
WantedBy=multi-user.target
```

```bash
systemctl enable --now selfsend
```

### Docker 部署（推荐）

推送 `main` 分支或 `v*` 标签后，GitHub Actions 会自动构建 Alpine 镜像并发布到
GHCR（`.github/workflows/docker-publish.yml`），镜像名
`ghcr.io/<owner>/<repo>:latest`（首次发布后需在 GitHub Package 页面调整可见性/关联仓库）。

服务器上运行（仓库自带 `docker-compose.yml`，所有配置都写在其中
`environment` 段，编辑后生效）：

```bash
docker compose pull && docker compose up -d
```

镜像说明：多阶段构建、非 root 用户运行、内置 `/health` HEALTHCHECK；
容器内强制监听 `0.0.0.0`，仍只映射到宿主机 `127.0.0.1`，公网 TLS 由反代终结。
selfsend 是无状态服务（无数据库、无文件写入），**没有需要持久化的数据**，
compose 不挂载任何卷/目录；配置直接写在 compose 的 `environment` 中，
并以只读根文件系统 + `no-new-privileges` 加固。

## 本地冒烟测试

```bash
pip install aiosmtpd        # 仅测试用
python scripts/smoke_test.py
```

脚本会启动本地 SMTP sink 与服务，依次验证健康检查、401 鉴权、422 校验、
正常发送、域名白名单 403 与 429 限流。
