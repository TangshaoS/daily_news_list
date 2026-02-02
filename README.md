# News Summary Pipeline

从路透社、华尔街日报、彭博社、金融时报、澎湃新闻抓取热点新闻，过滤并导出适合 NotebookLM 导入的链接清单。

## 功能特点

- **多源采集**：支持 RSS、Google News 代理、RSSHub 等多种接入方式
- **智能过滤**：基于关键词的主题过滤（地缘政治、经济、市场、供应链、大宗商品、AI）
- **热度排序**：综合时间衰减、来源权重、多源印证计算热度分数
- **去重聚类**：URL 去重 + 标题相似度聚类，避免重复报道
- **NotebookLM 导出**：生成可直接粘贴导入的 URL 清单

## 快速开始

### 1. 安装依赖

```bash
cd news_summary
pip install -r requirements.txt
```

### 2. 运行完整流水线

```bash
python run.py run
```

这会：
1. 从所有配置的新闻源抓取最新内容
2. 进行 URL 规范化、去重、主题过滤、聚类、热度排序
3. 存储到 SQLite 数据库
4. 导出 Top 40 链接到 `exports/` 目录

### 3. 导入 NotebookLM

1. 打开 [NotebookLM](https://notebooklm.google.com/)
2. 创建或打开一个 Notebook
3. 点击 "Add Source" → "Website URL"
4. 打开 `exports/notebooklm_urls_YYYYMMDD_HHMMSS.txt`
5. 复制全部内容，粘贴到 NotebookLM

## 命令行用法

```bash
# 完整流水线
python run.py run

# 仅抓取（不导出）
python run.py fetch

# 仅导出（使用数据库中现有数据）
python run.py export --limit 50

# 查看数据库统计
python run.py stats

# 列出所有配置的新闻源
python run.py sources

# 指定单个来源
python run.py fetch --source reuters

# 按分类导出
python run.py export --category geopolitics
python run.py export --category economy
python run.py export --category commodities
```

## 项目结构

```
news_summary/
├── run.py                    # 主入口
├── requirements.txt          # 依赖
├── README.md
├── data/                     # 数据目录（自动创建）
│   └── news.db              # SQLite 数据库
├── exports/                  # 导出目录（自动创建）
│   ├── notebooklm_urls_*.txt   # URL 清单
│   └── notebooklm_news_*.md    # Markdown 格式
├── backend/
│   └── app/
│       ├── cli.py           # 命令行接口
│       ├── models.py        # 数据模型
│       ├── sources/         # 新闻源配置
│       │   └── registry.py  # 源注册表（路透社、WSJ、Bloomberg等）
│       ├── ingest/          # RSS 抓取
│       ├── normalize/       # URL 规范化
│       ├── dedup/           # 去重与聚类
│       ├── filter/          # 主题过滤
│       ├── rank/            # 热度排序
│       ├── store/           # SQLite 存储
│       ├── export/          # NotebookLM 导出
│       └── summarize/       # 摘要生成（可选）
└── frontend/                 # 简单前端原型（可选）
    └── index.html
```

## 配置新闻源

编辑 `backend/app/sources/registry.py` 添加或修改新闻源：

```python
MY_SOURCE = SourceConfig(
    id="my_source",
    name="My Source",
    name_zh="我的来源",
    weight=1.0,  # 来源权重（影响热度分数）
    language="en",
    feed_urls=[
        "https://example.com/rss/feed.xml",
    ],
)

# 添加到注册表
SOURCE_REGISTRY["my_source"] = MY_SOURCE
```

## 主题过滤配置

编辑 `backend/app/filter/topic_filter.py` 修改关键词：

- **GEOPOLITICS_KEYWORDS**: 地缘政治（战争、制裁、外交）
- **ECONOMY_KEYWORDS**: 经济数据（GDP、通胀、利率、央行）
- **MARKETS_KEYWORDS**: 投资市场（股市、债券、情绪）
- **SUPPLY_CHAIN_KEYWORDS**: 供应链（物流、半导体、脱钩）
- **COMMODITIES_KEYWORDS**: 大宗商品（石油、稀土、有色金属）
- **AI_TECH_KEYWORDS**: AI 与科技

## 热度计算公式

```
score = source_weight × recency × (1 + α × (cluster_size - 1))
```

- `source_weight`: 来源权重（0.5-1.5）
- `recency`: 时间衰减（12小时半衰期）
- `cluster_size`: 报道该事件的来源数量
- `α`: 多源加成系数（默认 0.3）

## 可选：LLM 摘要

如果需要 AI 生成摘要（而非仅导出链接），设置环境变量：

```bash
# OpenAI
export OPENAI_API_KEY=sk-...

# 或 Anthropic
export ANTHROPIC_API_KEY=sk-ant-...
```

然后在代码中调用：

```python
from backend.app.summarize import LLMSummarizer

summarizer = LLMSummarizer()
if summarizer.is_available:
    points = await summarizer.summarize(item)
```

## 定时运行

### 方案一：GitHub Actions（推荐）

将代码推送到 GitHub 后，自动每天早上6点运行并发送邮件。

#### 1. 推送到 GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/news_summary.git
git push -u origin main
```

#### 2. 配置 Secrets

在 GitHub 仓库 → Settings → Secrets and variables → Actions 添加：

| Secret | 说明 | 示例 |
|--------|------|------|
| `SMTP_SERVER` | SMTP服务器 | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP端口 | `465` |
| `SMTP_USER` | 发件邮箱 | `your@gmail.com` |
| `SMTP_PASSWORD` | 邮箱密码/应用密码 | `xxxx xxxx xxxx xxxx` |
| `EMAIL_TO` | 收件邮箱 | `your@email.com` |

**Gmail 用户注意**：需要开启"应用专用密码"：
1. 前往 https://myaccount.google.com/apppasswords
2. 生成新的应用密码
3. 将生成的16位密码填入 `SMTP_PASSWORD`

#### 3. 手动测试

在 GitHub → Actions → Daily News Summary → Run workflow

#### 4. 自动运行

配置完成后，每天北京时间早上6点自动运行并发送邮件。

---

### 方案二：本地 cron（备用）

使用 cron 定时执行（每小时运行一次）：

```bash
crontab -e
# 添加：
0 * * * * cd /path/to/news_summary && python run.py run >> logs/cron.log 2>&1
```

## 注意事项

1. **版权合规**：本工具仅抓取公开 RSS/列表页，不存储全文，导出链接回源
2. **Rate Limiting**：默认每个源至少间隔 5 分钟抓取
3. **NotebookLM 限制**：单个 Notebook 最多 50 个 Sources

## License

MIT
