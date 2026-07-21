# Life Online

Life Online 是一个家庭任务游戏化项目，包含 Web 管理端与 Python 后端。

## 工程基线

- **主开发分支：** `develop`。日常开发与功能分支均以 `develop` 为基线；`main` 不作为当前开发基线。
- **仓库根目录：** Windows 环境统一使用 `D:\workspace\life-online`。
- **禁止嵌套：** 不要将仓库检出为 `D:\workspace\life-online\life-online`。进入仓库后，`git rev-parse --show-toplevel` 应输出 `D:/workspace/life-online`。

首次检出：

```bash
cd /d/workspace
git clone --branch develop <repository-url> life-online
cd life-online
git status --short --branch
```

已有仓库同步基线：

```bash
cd /d/workspace/life-online
git fetch origin
git switch develop
git pull --ff-only origin develop
```

## 功能分支协作流程

功能分支建议使用 `feat/<issue>-<topic>` 命名，并始终从最新的 `develop` 派生：

```bash
cd /d/workspace/life-online
git fetch origin
git switch develop
git pull --ff-only origin develop
git switch -c feat/dev-2-collaboration-baseline

# 完成修改后
git add README.md
git commit -m "docs: document development baseline"
git push -u origin feat/dev-2-collaboration-baseline
```

提交评审并合并到 `develop`。合并前先同步远端基线并解决冲突：

```bash
git fetch origin
git rebase origin/develop
```

不要直接在 `develop` 上提交功能代码，也不要从 `main` 派生当前开发任务。

## 使用 worktree 并行开发

需要同时处理多个任务时，可为每个功能分支创建独立 worktree。worktree 应与主仓库并列放置，避免在仓库内部形成嵌套目录。

```bash
cd /d/workspace/life-online
git fetch origin

# 从远端 develop 创建功能分支和并列 worktree
git worktree add ../life-online-dev-2 -b feat/dev-2-collaboration-baseline origin/develop
cd ../life-online-dev-2
```

此时目录结构应为：

```text
D:\workspace\
├── life-online\          # 主工作区，保持在 develop
└── life-online-dev-2\    # DEV-2 独立 worktree
```

查看和清理 worktree：

```bash
cd /d/workspace/life-online
git worktree list

# 分支已合并且工作区无未提交修改后再移除
git worktree remove ../life-online-dev-2
git branch -d feat/dev-2-collaboration-baseline
git worktree prune
```

不要把 worktree 创建到 `D:\workspace\life-online\life-online-*`，也不要让多个任务共用同一个功能分支或工作目录。

## 项目目录

- `packages/admin/`：Web 管理端。
- `server/`：Python 后端；启动、配置、迁移与测试说明见 `server/README.md`。
