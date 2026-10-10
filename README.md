# Life Online

家庭任务 RPG(表面是 RPG 公会冒险,内核是家庭任务管理)。后端 API 在 `server/`,Web 管理后台在 `packages/admin/`,移动端(家长/孩子)规划于 `packages/client/`。

设计与实施文档见 [docs/00-README.md](./docs/00-README.md)(阅读顺序、三端全景、API 契约入口)。

---

## 工程基线(新成员必读)

### 主开发分支:`develop`

- **`develop` 是主开发分支**,所有功能开发以此为基础。`main` 目前几乎为空,仅作保留,**不要基于 `main` 开发**。
- 需要定位"当前最新代码基线"时,一律看 `origin/develop`。

### 工程根目录:`D:\workspace\life-online`

- 本地克隆/检出时,工程根目录固定为 **`D:\workspace\life-online`**。
- **禁止嵌套**:不得出现 `D:\workspace\life-online\life-online` 这类目录套娃。若发现仓库被克隆到了仓库内部的子目录,立即删除该嵌套目录并重新在正确根目录检出。

### Git Worktree 并行开发

多个任务并行时,使用 git worktree 从 `develop` 派生独立工作树,互不干扰:

```powershell
# 在主工作树(D:\workspace\life-online)中,基于 develop 创建功能分支 + worktree
git fetch origin
git worktree add ..\life-online-feat-x -b feat/xxx origin/develop

# 查看所有 worktree
git worktree list

# 任务完成、分支合入 develop 后,清理 worktree
git worktree remove ..\life-online-feat-x
git branch -d feat/xxx
```

要点:

- 每个 worktree 对应一个功能分支,从 `origin/develop` 派生;
- worktree 目录放在 `D:\workspace\` 下与主工作树平级(如 `D:\workspace\life-online-feat-x`),**不要放在仓库内部**;
- 主工作树保持跟踪 `develop`,随时可拉取最新基线。

## 基础协作流程

```powershell
# 1. 拉取最新基线
git switch develop
git pull origin develop

# 2. 创建功能分支(从 develop 派生)
git switch -c feat/xxx      # 或 fix/xxx、docs/xxx

# 3. 开发、提交(提交信息使用 conventional commits:feat/fix/docs/...)
git add <files>
git commit -m "feat(scope): 简述变更"

# 4. 推送并合入
git push -u origin feat/xxx
#   - 有 PR 流程时:发起 PR,目标分支 develop,评审通过后合并
#   - 直接合并时:回到 develop,git merge --no-ff feat/xxx 后推送

# 5. 合入后同步本地
git switch develop
git pull origin develop
git branch -d feat/xxx
```

分支命名约定:`feat/*` 新功能、`fix/*` 修复、`docs/*` 文档、`chore/*` 杂项。所有合并目标都是 `develop`。
