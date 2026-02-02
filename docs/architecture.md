# 系统架构设计文档

## 概述

本系统是一个新闻热点链接聚合管道，从多个国际知名新闻源抓取内容，经过过滤、打分、去重后导出适合 NotebookLM 导入的链接清单。

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                           数据源层 (Sources)                         │
├─────────────────────────────────────────────────────────────────────┤
│  路透社(RSS)  │  华尔街日报(RSS)  │  彭博社(Google News)  │  金融时报  │  澎湃(RSSHub)  │
└───────┬───────┴────────┬──────────┴──────────┬───────────┴─────┬────┴───────┬────────┘
        │                │                     │                 │            │
        ▼                ▼                     ▼                 ▼            ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              采集层 (Ingest)                                             │
│  - RSSFetcher: 异步HTTP请求 + feedparser解析                                            │
│  - 超时重试、User-Agent 伪装                                                             │
└───────────────────────────────────────────────────────────────────────────────┬─────────┘
                                                                                │
                                                                                ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              处理层 (Processing)                                         │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                 │
│  │  Normalize  │ → │    Dedup    │ → │   Filter    │ → │    Rank     │                 │
│  │  URL规范化   │   │ URL去重+聚类 │   │  主题过滤   │   │  热度排序   │                 │
│  └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘                 │
└───────────────────────────────────────────────────────────────────────────────┬─────────┘
                                                                                │
                    ┌───────────────────────────────────────────────────────────┼───────┐
                    │                                                           │       │
                    ▼                                                           ▼       │
┌─────────────────────────────┐                               ┌────────────────────────┐│
│      存储层 (Store)         │                               │    导出层 (Export)      ││
│  SQLite: news.db           │                               │  - notebooklm_urls.txt ││
│  - news_items 表            │                               │  - notebooklm_news.md  ││
│  - export_history 表        │                               │  - JSON (可选)          ││
└─────────────────────────────┘                               └────────────────────────┘│
                                                                                        │
                    ┌───────────────────────────────────────────────────────────────────┘
                    ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              前端层 (Frontend) - 可选                                    │
│  - 静态HTML原型展示信息架构                                                              │
│  - 分类导航: 地缘政治 / 经济 / 市场 / 供应链 / 大宗商品 / AI                             │
│  - 热度榜 + 分类新闻流                                                                   │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

## 数据模型

### NewsItem

```python
@dataclass
class NewsItem:
    url: str                    # 原始URL
    title: str                  # 标题
    source_id: str              # 来源ID (reuters, wsj, bloomberg, ft, thepaper)
    published_at: datetime      # 发布时间
    summary: str                # RSS摘要
    normalized_url: str         # 规范化URL
    categories: list[Category]  # 分类标签
    keywords: list[str]         # 关键词
    source_weight: float        # 来源权重
    recency_score: float        # 时效分数
    cluster_size: int           # 聚类大小（多源报道数）
    final_score: float          # 最终热度分数
    cluster_id: str             # 聚类ID
```

### Category 枚举

| 值 | 含义 | 关键词示例 |
|---|---|---|
| geopolitics | 地缘政治 | war, sanctions, conflict, diplomacy |
| economy | 经济数据 | GDP, inflation, interest rate, Fed |
| markets | 投资市场 | stock, rally, selloff, sentiment |
| supply_chain | 供应链 | logistics, semiconductor, decoupling |
| commodities | 大宗商品 | oil, copper, rare earth, lithium |
| ai_tech | AI与科技 | AI, LLM, OpenAI, chip, data center, 液冷 |
| energy_infra | 能源基础设施 | electricity, power grid, 电力, 液冷, 储能, 新能源 |

## 核心算法

### 热度排序公式

```
score = source_weight × recency × (1 + α × (cluster_size - 1)) × category_bonus
```

- **source_weight** (0.5-1.5): 来源权重，路透社/WSJ/Bloomberg/FT = 1.0，澎湃 = 0.9
- **recency**: 时间衰减，`exp(-ln(2) × hours / 12)`，12小时半衰期
- **cluster_size**: 同一事件被多少个来源报道
- **α** = 0.3: 多源加成系数
- **category_bonus**: 跨分类报道 +10%

### 主题过滤规则

- **强关键词** (+2分): 一次命中即相关，如 "sanctions", "inflation", "rare earth"
- **普通关键词** (+0.5分): 需多次命中，如 "market", "growth"
- **阈值**: score ≥ 1.0 视为相关

### 去重与聚类

1. **URL去重**: 规范化后的URL精确匹配
2. **标题聚类**: `token_sort_ratio(title_a, title_b) ≥ 75` 判定为同一事件
3. **聚类代表**: 取来源权重最高的条目作为代表

## 数据流

```
RSS Feed → HTTP GET → feedparser → NewsItem
    ↓
normalize_url (去utm/tracking参数)
    ↓
deduplicate_items (URL精确去重)
    ↓
cluster_similar_items (标题相似聚类)
    ↓
filter_by_topics (关键词过滤)
    ↓
rank_items (热度打分+排序)
    ↓
get_cluster_representatives (每个聚类取代表)
    ↓
export_for_notebooklm (输出txt/md)
```

## 新闻源配置

| Source | RSS/API | 权重 | 语言 |
|--------|---------|------|------|
| Reuters | reutersagency.com/feed + Google News fallback | 1.0 | en |
| WSJ | feeds.a.dj.com/rss/* | 1.0 | en |
| Bloomberg | Google News (site:bloomberg.com) | 1.0 | en |
| FT | ft.com/?format=rss + Google News fallback | 1.0 | en |
| 澎湃新闻 | RSSHub (/thepaper/channel/*) | 0.9 | zh |

## NotebookLM 集成

### 导出格式

1. **notebooklm_urls.txt**: 纯URL列表，一行一个，直接粘贴导入
2. **notebooklm_news.md**: Markdown格式，按分类组织，包含元数据

### 使用流程

1. 运行 `python run.py run`
2. 打开 NotebookLM → 创建/打开 Notebook
3. Add Source → Website URL
4. 粘贴 `exports/notebooklm_urls_*.txt` 内容
5. 等待 NotebookLM 抓取处理

### 限制

- 单个Notebook最多50个Sources
- 建议每次导出40条，留有余量
- 部分URL可能因付费墙/反爬无法被NotebookLM抓取

## 摘要方案（可选）

### 方案A: 非LLM（默认）

- 基于TF的句子打分
- 提取RSS summary中的关键句
- 零成本，实时响应

### 方案B: LLM（需配置API Key）

- 支持OpenAI (gpt-4o-mini) 和 Anthropic (claude-3-haiku)
- 结构化prompt生成要点摘要
- 适合高价值内容的深度处理

## 运维建议

### 定时任务

```cron
# 每小时运行一次
0 * * * * cd /path/to/news_summary && python run.py run >> logs/cron.log 2>&1
```

### 监控指标

- 抓取成功率（每源）
- 相关内容占比（过滤前后）
- 平均热度分数趋势
- 导出数量/频率

### 合规注意

- 仅抓取公开RSS/列表页
- 不存储全文，只存元数据
- 导出链接回源，保留版权标注
