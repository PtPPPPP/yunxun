# 安全边界

## V1.0 已实现

- 密码：PBKDF2-HMAC-SHA256，每个密码使用独立随机盐。
- 登录 Token：随机生成；数据库只保存 HMAC-SHA256 摘要；支持过期、撤销和旧明文 Token 失效迁移。
- 认证：Bearer Token，前端保留在 localStorage。
- 输入保护：Pydantic 校验、消息长度、上传 MIME/Base64/大小、分页和请求体限制。
- 接口保护：CORS 白名单、进程内限流、幂等键、安全响应头和请求 ID。
- 日志：敏感值使用不可逆指纹，不记录原始 Token、系统 API Key 或用户输入全文。
- 生产配置：拒绝短默认 Secret、Debug、通配 CORS 等危险配置。

## 当前工作区增强

- Cookie：登录后签发 HttpOnly 会话 Cookie，生产要求 Secure。
- CSRF：Cookie 写请求使用可读 CSRF Cookie 与请求头双提交校验；Bearer-only 请求保持兼容。
- BYOK：默认关闭；用户 Key 使用独立 32 字节主密钥进行 AES-GCM 加密，并只返回指纹。OpenAI-compatible 地址必须在管理员白名单内，并拒绝私网、回环、非安全协议和重定向。

Cookie/CSRF 已通过本地自动化流程，BYOK 已通过单元和无真实 Key 的 E2E；二者均不属于标签版 V1.0，BYOK 还没有真实 Provider 兼容性证据。

## 未实现

- RBAC、管理员后台、用户禁用和多租户隔离。
- 集中式限流、集中日志、SIEM、metrics 和外部告警。
- 自动 TLS、反向代理安全基线、WAF 和公网渗透测试。
- BYOK 主密钥自动轮换、HSM/KMS 托管和真实 Provider 回归矩阵。

## 数据与部署限制

- SQLite 文件、备份和 `.env` 都可能包含敏感信息，必须保持在 Git 之外并限制访问。
- BYOK 数据库备份只有与正确主密钥配套时才能恢复；主密钥不得与数据库放在同一备份位置。
- 当前项目仅适合本地和内网受控环境。公开互联网部署前必须补齐 HTTPS、持久化数据库、集中限流、监控和安全评审。
