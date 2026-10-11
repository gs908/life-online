# life-online 管理后台(packages/admin)

React + Vite + Tailwind 的家庭任务游戏化管理后台。

AI 能力(任务文案生成 / 评分)统一走后端 `/api/v1/scn/ai/*` 接口
(模型与默认参数配置在后端 `server/config.yaml` 的 `ai:` 段);
前端不持有任何模型 key。API 调用约定见 `src/services/api/`
(docs/10-前端API接入计划.md)。

## Run Locally

**Prerequisites:** Node.js + pnpm

1. Install dependencies:
   `pnpm install`
2. Run the app:
   `pnpm run dev`

## 后端 API 接入方式（二选一）

前端请求基础地址由 `VITE_API_BASE_URL` 决定（`src/services/api/http.ts`），
**未设置时默认走相对路径 `/api/v1`**，由 Vite dev server 代理转发（`vite.config.ts`
的 `server.proxy`，`/api` → `VITE_API_PROXY_TARGET`，默认 `http://localhost:8000`，
与 `server/config.yaml` 默认端口一致）。

- **a) 默认：Vite 代理**（推荐，免 CORS）。不设 `VITE_API_BASE_URL` 即可；
  后端不在本机时在 `packages/admin/.env.local` 设
  `VITE_API_PROXY_TARGET=http://<后端主机>:8000`。
  修改代理配置后需重启 `pnpm run dev`。
- **b) 直连后端**：设 `VITE_API_BASE_URL=http://<host>:8000/api/v1`
  （复制 `.env.example` 为 `.env.local` 修改）。需后端 CORS 放行该来源
  （`server/config.yaml` 的 `cors:` 段）。

## 开发期登录（dev-login）

需要登录态的接口走开发期登录（`POST /sys/auth/dev-login`，契约见
`docs/08-后端API契约.md` §2）。该接口仅在后端开启 `DEV_LOGIN_ENABLED=true`
时可用——**本地开发需在 `server/.env`（或对应环境配置）设置该项，否则登录会
返回 403 `permission_denied`**；生产环境保持默认关闭。

