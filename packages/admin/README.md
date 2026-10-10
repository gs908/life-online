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

需要登录态的接口走开发期登录(`POST /sys/auth/dev-login`,
需后端 `DEV_LOGIN_ENABLED=true`);API 地址经 `VITE_API_BASE_URL` 配置。
