# 不租服务器上线：GitHub Actions + GitHub Pages 详细步骤

从没弄过也没关系，按下面一步步做即可。做完后用户可以通过一个网址打开你的「新闻热点总结」页面，每天自动更新。

---

## 一、前置条件

- 已安装 **Git**（终端能执行 `git --version`）。
- 有一个 **GitHub 账号**（没有的话去 [github.com](https://github.com) 注册）。
- 本机已经能正常运行项目（`python run.py run`、`python run.py export --formats digest` 能成功）。

---

## 二、整体流程概览

1. 把项目推到 GitHub 仓库。
2. 在仓库设置里把 GitHub Pages 的「发布来源」选成 **GitHub Actions**。
3. 项目里已准备好部署用的 workflow，推代码后会按 schedule 跑（或你手动跑一次）。
4. 跑成功后，用户打开 `https://<你的用户名>.github.io/<仓库名>/` 就能看到页面。

下面按步骤写。

---

## 三、第一步：把代码推到 GitHub

### 3.1 在 GitHub 上建一个新仓库

1. 登录 GitHub，右上角点 **+** → **New repository**。
2. **Repository name** 填一个名字，例如：`news_summary`（后面访问地址里会用到）。
3. 选 **Public**，**不要**勾选 "Add a README file"（你本地已有代码）。
4. 点 **Create repository**。

### 3.2 在本地把项目推上去

在终端里执行（把 `YOUR_USERNAME` 换成你的 GitHub 用户名，`news_summary` 换成你刚建的仓库名）：

```bash
cd /Users/shens/projects/news_summary

# 如果还没初始化过 Git（一般你已经有了）
git init
git add .
git commit -m "Add news summary pipeline and frontend"

# 添加远程仓库并推送
git remote add origin https://github.com/YOUR_USERNAME/news_summary.git
git branch -M main
git push -u origin main
```

如果仓库已存在且已有 `origin`，只差推送，就只执行：

```bash
git add .
git commit -m "Add deploy workflow and docs"
git push origin main
```

推送成功后，在 GitHub 上刷新仓库页面，能看到代码和 `.github/workflows/deploy-pages.yml`。

---

## 四、第二步：开启 GitHub Pages 并选「GitHub Actions」

1. 打开你的仓库页面，点顶部的 **Settings**。
2. 左侧菜单最下面找到 **Pages**，点进去。
3. 在 **Build and deployment** 里：
   - **Source** 选 **GitHub Actions**（不要选 "Deploy from a branch"）。
4. 不需要再点别的，保存即可。

这样以后每次跑「Deploy to GitHub Pages」这个 workflow 并成功结束时，GitHub 会自动把生成的静态站发布出去。

---

## 五、第三步：确认部署用的 workflow（项目里已写好）

项目里已经有一个专门用来部署到 Pages 的 workflow，路径是：

`.github/workflows/deploy-pages.yml`

它会：

1. 拉取代码、装依赖。
2. 执行 `python run.py run --limit 40`（抓取、处理、入库、导出 txt/md）。
3. 再执行 `python run.py export --formats digest --limit 40`，生成 `exports/latest_digest.json`。
4. 把 `frontend/index.html` 和 `exports/latest_digest.json` 放进一个「站点目录」并上传为 artifact。
5. 用 GitHub 官方的 **deploy-pages** 把该 artifact 发布到 GitHub Pages。

你只要保证这个文件在仓库里并且已推送到 `main` 即可。如需改定时时间，可编辑该文件里的 `cron: '0 22 * * *'`（默认是每天 UTC 22:00，即北京时间早上 6 点）。

---

## 六、第四步：跑一次 workflow（建议先手动跑）

1. 打开仓库页面，点顶部的 **Actions**。
2. 左侧会看到 **Deploy to GitHub Pages**，点它。
3. 右侧点 **Run workflow**，再点绿色的 **Run workflow** 按钮。
4. 等几分钟，列表里会出现一条 run，点进去看进度。全部打勾表示成功。

若某一步报错，点开该 step 看日志（例如 Python 依赖失败、网络超时等），根据报错修好再重新 **Run workflow**。

---

## 七、第五步：打开你的站点地址

workflow 跑成功后，站点地址是：

**`https://<你的用户名>.github.io/<仓库名>/`**

例如仓库名是 `news_summary`、用户名是 `zhangsan`，则地址为：

**`https://zhangsan.github.io/news_summary/`**

在浏览器里打开这个地址，就能看到「新闻热点总结」页面，数据是上一次 workflow 跑出来的 digest。

- 之后每天会按 schedule 自动跑一次（默认北京时间早上 6 点），跑完页面会自动更新。
- 你也可以随时在 Actions 里再点 **Run workflow** 手动更新。

---

## 八、前端和路径说明（已自动处理好）

- 部署到 GitHub Pages 时，站点根目录是「仓库根」对应的那层，所以首页是 `index.html`，数据在 `exports/latest_digest.json`。
- 前端里已经做了判断：**在 GitHub Pages 上**用相对路径 `exports/latest_digest.json`，**在本地打开 frontend/index.html** 时用绝对路径 `/exports/latest_digest.json`，这样本地和线上都能正常加载数据，你不需要再改代码。

---

## 九、常见问题

### 1. 打开链接是 404

- 确认 **Settings → Pages → Source** 选的是 **GitHub Actions**，不是 branch。
- 确认 **Deploy to GitHub Pages** 这个 workflow 至少成功跑过一遍（Actions 里能看到绿色勾）。

### 2. 页面打开了但显示「加载失败」或没有数据

- 说明 digest 没生成或没被正确打进 artifact。到 Actions 里点进最近一次 run，看 **Export digest for frontend** 和 **Prepare site** 两步是否成功；若某步失败，看日志里的报错（例如数据库为空、网络错误等）。

### 3. 想立刻更新一次数据

- 到 **Actions → Deploy to GitHub Pages → Run workflow** 再跑一次即可。

### 4. 想改自动运行的时间

- 编辑 `.github/workflows/deploy-pages.yml`，改 `schedule` 里的 `cron`。例如改成北京时间每天 8 点：`cron: '0 0 * * *'`（UTC 0 点 = 北京时间 8 点）。改完提交并推送到 `main`。

### 5. 国内访问很慢或打不开

- GitHub 服务器在国外，国内访问有时会慢或被墙。若主要用户在国内，可以考虑之后用「租一台国内 VPS」的方式，见 [deployment.md](deployment.md) 里的「方式二」。

### 6. 发邮件和部署是两套 workflow

- 当前仓库里可能还有一个 **Daily News Summary** workflow（发邮件、上传 artifact）。  
- **Deploy to GitHub Pages** 只负责「跑流水线 + 生成 digest + 部署到 Pages」，不会发邮件。两套可以并存：一个定时发邮件，一个定时更新网页。

---

## 十、小结

| 步骤 | 做什么 |
|------|--------|
| 1 | 在 GitHub 建仓库，本地 `git push` 上去 |
| 2 | 仓库 **Settings → Pages → Source** 选 **GitHub Actions** |
| 3 | **Actions** 里运行一次 **Deploy to GitHub Pages** |
| 4 | 打开 `https://<用户名>.github.io/<仓库名>/` 查看页面 |

不需要租服务器，也不用买域名（用默认的 `*.github.io` 即可）。以后只要代码和 workflow 在，就会按你设定的时间自动更新页面供用户访问。
