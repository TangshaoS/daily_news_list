# 上线部署方案：如何让用户访问

项目上线给用户用，**不一定要租服务器**。按成本和可控程度，大致有三种方式。

---

## 方式一：不租服务器（GitHub Actions + 静态托管）

**思路**：流水线在 GitHub 上定时跑，把生成的**前端页面 + digest 数据**一起推到静态站点，用户直接打开网页看。

| 项目 | 说明 |
|------|------|
| 跑流水线 | GitHub Actions 定时执行 `run.py`，并导出 digest |
| 托管前端 | GitHub Pages / Vercel / Netlify 等免费静态托管 |
| 是否要租服务器 | **不需要** |
| 适合 | 个人或小规模、先验证有没有人用 |

**本项目已准备好「GitHub Actions + GitHub Pages」的 workflow 和前端路径适配，按文档做即可：**

- **[不租服务器上线详细步骤（从零开始）](deployment_github_pages.md)** — 从建仓库、开启 Pages、手动跑 workflow，到打开站点地址，一步步说明；没弄过也能按步骤完成。

**优点**：零服务器成本、不用维护机器。  
**缺点**：依赖 GitHub 与托管商的限制（频率、构建时间、国内访问可能慢或被墙）。

---

## 方式二：租一台云服务器（VPS）

**思路**：在云上买一台小机器，定时跑流水线，用 Nginx（或 Caddy）把前端和 `exports/` 当静态资源提供给用户。

| 项目 | 说明 |
|------|------|
| 跑流水线 | 服务器上用 cron 定时执行 `python run.py export --formats txt,md,digest --limit 40`（或先 `run` 再 `export`） |
| 提供网页 | Nginx/Caddy 配置：根目录或子路径指向 `frontend/`，`/exports/` 指向 `exports/` |
| 是否要租服务器 | **需要**（一台低配即可，如 1 核 1G） |
| 适合 | 需要稳定、可控、或主要面向国内用户 |

**需要做的事**：

1. **买 VPS**：阿里云 / 腾讯云 / 华为云 / AWS / Vultr 等，选 Linux（如 Ubuntu）。

2. **装环境**：Python 3.11+、项目依赖（`pip install -r requirements.txt`），可选：用 systemd 或 supervisor 管理进程（若以后加 API 服务）。

3. **定时任务**：cron 每天执行，例如：
   ```bash
   0 6 * * * cd /path/to/news_summary && python run.py export --formats txt,md,digest --limit 40
   ```
   若希望先抓再导，可先跑 `python run.py run` 再 `export`，或写成一个小脚本一起跑。

4. **Nginx 示例**（站点根目录即项目根）：
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;
       root /path/to/news_summary;
       location / {
           try_files $uri $uri/ /frontend/index.html;
       }
       location /exports/ {
           alias /path/to/news_summary/exports/;
       }
   }
   ```
   这样用户访问 `http://your-domain.com/` 会看到前端，前端请求 `/exports/latest_digest.json` 能拿到数据。

5. **HTTPS**：用 Let’s Encrypt（certbot）给域名上证书。

**优点**：完全自己控制、国内选国内机房访问会更好。  
**缺点**：要付云主机费、自己要管安全与更新。

---

## 方式三：流水线在云端、前端单独托管（进阶）

**思路**：流水线跑在「云函数 / 定时任务」里，把生成的 `latest_digest.json` 存到对象存储（如阿里云 OSS、AWS S3）；前端部署在 Vercel/Netlify，直接请求对象存储的公开 URL（或通过一层简单 API 转发）。

| 项目 | 说明 |
|------|------|
| 跑流水线 | 云函数（如阿里云 FC、AWS Lambda）+ 定时触发器，或 GitHub Actions 把生成的 JSON 上传到 OSS/S3 |
| 数据存储 | OSS/S3 桶里放 `latest_digest.json`，设成公开读或签名 URL |
| 前端 | 部署在 Vercel 等，前端里 `DIGEST_URL` 改为 OSS/S3 的 URL |
| 是否要租服务器 | **不需要**（用现成的 FaaS + 对象存储） |
| 适合 | 访问量上来后、希望流水线和前端解耦、便于扩展 |

**需要做的事**：改前端请求地址；在 Actions 或云函数里增加「上传到 OSS/S3」步骤；配置 CORS 和访问权限。实现成本比方式一、二高一些。

---

## 建议怎么选

- **先验证、少花钱**：用 **方式一**（GitHub Actions + GitHub Pages/Vercel），不租服务器即可上线。
- **要稳定、国内用户多**：用 **方式二**，租一台小 VPS，按上面配置 Nginx + cron。
- **以后要做大、要解耦**：再考虑 **方式三**，把「跑流水线」和「存/发数据」拆开。

总结：**不是非要租服务器**；要零成本上线就用方式一，要稳定、可控再选方式二租一台云服务器。
