# 自托管字体（外置资源）

本目录存放 `packages/admin/index.html` 引用的 **Roboto** 与 **Press Start 2P** 字体，
作为**外置文件**随 `public/` 原样拷贝到构建产物，**不打包进 bundle**。

`index.html` 以**绝对路径**引用（Vite `base` 默认 `/`，dev 与 build 均可用）：

```html
<link rel="stylesheet" href="/fonts/fonts.css">
```

`fonts.css` 用相对路径 `./files/*.woff2` 指向同目录 `files/`，
因此整目录搬移也能正常工作。

## 当前版本

| 字体 | 字重 | 子集 | 文件 | 来源 |
| --- | --- | --- | --- | --- |
| Roboto | 400 / 500 / 700 | latin, latin-ext | `files/roboto-latin*-{400,500,700}-normal.woff2` | `@fontsource/roboto@5.3.0` |
| Press Start 2P | 400 | latin, latin-ext | `files/press-start-2p-latin*-400-normal.woff2` | `@fontsource/press-start-2p@5.3.0` |

- 上层字体工程均为 Google Fonts 官方字体，`@fontsource` 只是把它转成 npm 包并附带 `@font-face` / `unicode-range`。
- 仅保留 `latin` + `latin-ext` 子集（UI 文案为英文 / 西欧字符）。
  中文等 CJK 字符本就不在这两款字体的字形范围内，仍按原样回退到系统字体，行为与改造前一致。
- 只提供 `woff2`（2016 年后的主流浏览器均支持）。
- 合计约 140 KB。

## 为什么外置

- 国内 / 无代理环境直连 `fonts.googleapis.com` / `fonts.gstatic.com` 不通，外链会导致字体回退。
- 外置成 `public/` 下的静态文件后，可**替换文件**来切换字体 / 版本，**无需改代码、无需重新构建**
  （`public/` 内容只在构建时被拷贝）。

## 如何换到别的版本

1. 取目标版本的字体包：

   ```bash
   npm pack @fontsource/roboto@5.3.1
   # 或（网络受限时）用国内镜像：
   npm pack @fontsource/roboto@5.3.1 --registry=https://registry.npmmirror.com
   ```

2. 解包后把所需的 `woff2` 拷入 `files/`（保持 `unicode-range` 与文件名一致）：

   ```bash
   tar -xzf fontsource-roboto-5.3.1.tgz
   cp package/files/roboto-latin*-{400,500,700}-normal.woff2 packages/admin/public/fonts/files/
   ```

3. 若文件名或子集有变化，同步修改 `fonts.css` 中对应的 `src` / `unicode-range`。
   只想换字体本身（同名同子集）时，直接覆盖 `files/` 里的文件即可，**不用改任何代码**。

## 如何换回外部 CDN

把 `index.html` 中的 `<link rel="stylesheet" href="/fonts/fonts.css">`
改回 Google Fonts 外链即可（仅限网络可达 `fonts.googleapis.com` 的环境）：

```html
<link href="https://fonts.googleapis.com/css2?family=Press+Start+2P&family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
```

## 复原记录

| 项目 | 值 |
| --- | --- |
| 获取方式 | `npm pack --registry=https://registry.npmmirror.com` |
| 包 | `@fontsource/roboto@5.3.0`、`@fontsource/press-start-2p@5.3.0` |
| 抽取文件 | `package/files/*-latin-*-normal.woff2`、`package/files/*-latin-ext-*-normal.woff2` |
| 许可 | Roboto: Apache-2.0；Press Start 2P: OFL-1.1（随包 `LICENSE`） |