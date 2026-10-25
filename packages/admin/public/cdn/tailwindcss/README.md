# Tailwind 浏览器构建脚本（外置资源）

本目录存放 `packages/admin/index.html` 引用的 **Tailwind Play CDN 浏览器构建脚本**，
作为**外置文件**随 `public/` 原样拷贝到构建产物，**不打包进 bundle**。

`index.html` 以**绝对路径**引用（Vite `base` 默认 `/`，dev 与 build 均可用）：

```html
<script src="/cdn/tailwindcss/tailwindcss-3.4.17.js"></script>
```

## 当前版本

| 文件 | 版本 | 来源 |
| --- | --- | --- |
| `tailwindcss-3.4.17.js` | 3.4.17 | `https://cdn.tailwindcss.com/3.4.17`（Play CDN 同款脚本） |

大小约 407 KB（minified，自包含浏览器构建）。

## 为什么外置

- 国内 / 无代理环境直连 `cdn.tailwindcss.com` 不通，外链会导致**全站无样式**。
- 外置成 `public/` 下的静态文件后，可**替换文件或改路径**来切换 CDN / 版本，
  **无需改代码、无需重新构建**（`public/` 内容只在构建时被拷贝）。

## 如何换到别的版本

1. 下载目标版本的 Play CDN 脚本，文件名带版本号，例如：

   ```bash
   curl -o packages/admin/public/cdn/tailwindcss/tailwindcss-3.4.18.js \
     https://cdn.tailwindcss.com/3.4.18
   ```

   （网络受限时可用代理 `-x http://127.0.0.1:7890`，或经 jsDelivr 等国内可达镜像获取
   同版本脚本；下载后请确认内容为 Tailwind Play CDN 构建：文件约 400 KB、
   含 `tailwindcss` 与版本号字符串。）

2. 修改 `packages/admin/index.html` 中的 `src` 指向新文件名：

   ```html
   <script src="/cdn/tailwindcss/tailwindcss-3.4.18.js"></script>
   ```

3. 删除旧版本文件（可选）：`rm packages/admin/public/cdn/tailwindcss/tailwindcss-3.4.17.js`

> 若希望**替换文件即生效**（不改 `index.html`），可约定固定文件名
> （如 `tailwindcss.js`）覆盖写入——但那样会丢失版本信息。当前方案选择**文件名带版本**，
> 版本切换时同步更新 `index.html` 一处引用，路径集中在本目录。

## 如何换回外部 CDN

把 `index.html` 中的 `src` 改回外链即可（仅限网络可达 `cdn.tailwindcss.com` 的环境）：

```html
<script src="https://cdn.tailwindcss.com/3.4.17"></script>
```