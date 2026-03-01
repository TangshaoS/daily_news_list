# 现有流水线与前端展示能力评估

本文档梳理当前新闻摘要项目的流水线、前端展示能力、可复用资产与平台化缺口，供后续「垂直情报简报平台」规划参考。

---

## 一、现有流水线梳理

### 1.1 入口与命令

| 入口 | 说明 |
|------|------|
| `run.py` | 主入口，默认执行 `run`（完整流水线） |
| `backend/app/cli.py` | Typer CLI：`fetch` / `export` / `run` / `stats` / `sources` |

### 1.2 完整流水线步骤（fetch → 处理 → 存储 → 导出）

1. **采集 (Ingest)**  
   - 模块：`backend/app/ingest/`（`RSSFetcher`, `fetch_all_sources`）  
   - 行为：从 `SOURCE_REGISTRY` 配置的 RSS/Google News 等拉取条目，解析为 `NewsItem` 列表。

2. **URL 规范化 (Normalize)**  
   - 模块：`backend/app/normalize/`  
   - 行为：去除 UTM/tracking 等参数，得到 `normalized_url`。

3. **去重 (Dedup)**  
   - 模块：`backend/app/dedup/`（`deduplicate_items`, `cluster_similar_items`）  
   - 行为：URL 精确去重；标题相似度（如 token_sort_ratio ≥ 75）聚类，赋予 `cluster_id`。

4. **主题过滤 (Filter)**  
   - 模块：`backend/app/filter/`（`topic_filter.py`, `filter_by_topics`）  
   - 行为：基于关键词（强/普通/负向）打分，`min_score=1.0` 通过，并写入 `item.categories`。  
   - 主题：地缘、经济、市场、供应链、大宗商品、AI/科技、能源基础设施等（见 `Category` 与 `ALL_TOPIC_KEYWORDS`）。

5. **热度排序 (Rank)**  
   - 模块：`backend/app/rank/`（`HotnessRanker`, `rank_items`）  
   - 行为：`final_score = source_weight × recency × (1 + α × (cluster_size - 1))` 等，按分数排序。

6. **存储 (Store)**  
   - 模块：`backend/app/store/`（`NewsDatabase`）  
   - 行为：SQLite `news_items` 表持久化；`export_history` 记录导出历史。

7. **导出 (Export)**  
   - 模块：`backend/app/export/notebooklm.py`  
   - 行为：  
     - **txt**：纯 URL 列表（NotebookLM 粘贴用）。  
     - **md**：按分类的 Markdown，含元数据。  
     - **json**：单条元数据，可选 `meta_map`  enriching（title, description, resolved_url 等）。  
     - **digest**：按聚类聚合的 JSON（`clusters` + `by_category`），写 `digest_*.json` 与 `latest_digest.json`，供前端与日摘要消费。

8. **可选增强（仅在 export 时）**  
   - **Enrich 页面元数据**：`backend/app/enrich/page_meta.py`（`enrich_items`）→ 解析 HTML 取 og:title、description、resolve 重定向得到 `resolved_url`。  
   - **Enrich 正文**：`backend/app/enrich/article_content.py`（`enrich_items_content`）→ 抽取正文关键段落，供 digest 的 `key_paragraphs`。  
   - **摘要**：`backend/app/summarize/` — 抽取式（`extract_cluster_points_for_digest`）或 LLM 精炼（`refine_all_cluster_points`），得到每聚类的 `points` 写入 digest。

### 1.3 数据流小结

```
RSS/Feeds → Normalize → Dedup → Cluster → Filter(topics) → Rank → DB
                                                                     ↓
Export: txt / md / json / digest (← 可选 enrich_meta, content, LLM points)
```

---

## 二、前端展示能力

### 2.1 载体与数据源

- **载体**：`frontend/index.html` 单页静态前端。  
- **数据源**：通过相对路径请求 **`/exports/latest_digest.json`**（需在项目根目录起 HTTP 服务时，使 `exports/` 可访问）。

### 2.2 已实现能力

| 能力 | 说明 |
|------|------|
| 分类导航 | 由 `digest.by_category` 动态生成 Tab：全部热点 + 各地缘/经济/市场/供应链/大宗/AI/能源等，点击切换筛选。 |
| 聚类卡片 | 每个 cluster 展示：headline（链到首条 `resolved_url`）、要点列表（`points`）、来源条数。 |
| 展开详情 | 可展开「关键段落」与「多源列表」：`key_paragraphs`、各 item 的 title + `resolved_url` + 时间。 |
| 热度榜 | 侧栏「热度榜 TOP 10」取 `digest.clusters` 前 10，展示标题与来源数。 |
| 搜索 | 客户端按标题与 `points` 文本过滤，无服务端检索。 |
| 导出入口 | 页头「导出到 NotebookLM」链接（当前为占位，可指向说明或实际 .txt 下载）。 |

### 2.3 Digest 数据契约（与 export 对齐）

前端依赖的 **digest JSON** 结构（与 `NotebookLMExporter.export_digest_json` 一致）：

- `generated_at`：生成时间（ISO8601）。  
- `item_count`：总条数。  
- `clusters`：数组，每项含  
  - `cluster_id`, `category`（分类列表）, `headline`, `points`（要点）,  
  - `items`：`title`, `input_url`, `resolved_url`, `source_id`, `published_at`, `description`, `key_paragraphs`。  
- `by_category`：`{ "geopolitics": ["cluster_id", ...], ... }`，用于导航与筛选。

### 2.4 前端缺口（相对「平台」目标）

- 无用户系统（无登录、无偏好）。  
- 无订阅/告警（无邮件、飞书/企微推送）。  
- 无历史检索、无收藏/反馈闭环。  
- 依赖本地/自建静态服务 + 本地 `exports/`，无标准 API 与多终端触达。

---

## 三、可复用资产（平台化可依赖）

### 3.1 数据管道

| 资产 | 位置 | 复用方式 |
|------|------|----------|
| 端到端流水线 | `cli.py`（fetch / run / export） | 作为 Daily Brief 的生成引擎，定时跑或按需触发。 |
| 统一 digest 结构 | `export/notebooklm.py`（`export_digest_json`） | 作为「事件卡」统一数据契约，Web/邮件/机器人共用同一 JSON。 |
| 主题与分类 | `filter/topic_filter.py`（`Category` + 关键词） | 作为订阅维度（主题、国家/地区可在此扩展）。 |
| 热度与排序 | `rank/` | 直接复用「今日 Top N」与热度榜。 |
| 聚类与代表项 | `dedup/`（`get_cluster_representatives`） | 多源聚合与代表选取逻辑可直接沿用。 |

### 3.2 内容增强与摘要

| 资产 | 位置 | 复用方式 |
|------|------|----------|
| 页面元数据 | `enrich/page_meta.py`（resolve_url, fetch_html, extract_meta） | 提升链接可读性与 `resolved_url` 质量；可继续加强 gstatic 等边缘情况。 |
| 正文抽取 | `enrich/article_content.py` | 为「关键段落」与深度摘要提供输入。 |
| 抽取式要点 | `summarize/extractive.py`（`extract_cluster_points_for_digest`） | 零成本、可作默认摘要。 |
| LLM 精炼 | `summarize/llm_summarizer.py`（`refine_all_cluster_points`） | 可作为「高级版」卖点，提升要点质量。 |

### 3.3 存储与导出

| 资产 | 位置 | 复用方式 |
|------|------|----------|
| SQLite 与 schema | `store/database.py` | 作为现有数据层；平台化时可保留为「单实例存储」或迁移到 PG 等。 |
| 多格式导出 | `export/notebooklm.py`（txt, md, json, digest） | 已有；可扩展字段（如影响级别、地区标签）仍以 digest 为主接口。 |

### 3.4 前端与展示

| 资产 | 位置 | 复用方式 |
|------|------|----------|
| 日摘要页 UI | `frontend/index.html` | 作为「今日 Top 事件卡」的展示原型；可改为消费 API 或静态 digest。 |
| 事件卡结构 | 同上（headline + points + 多源 + 关键段落） | 与 digest 契约一致，可复用于邮件模板、IM 卡片。 |
| 分类导航 + 热度榜 | 同上 | 产品形态可直接迁移到 P0 Daily Brief 平台。 |

---

## 四、平台化缺口（按优先级）

### 4.1 内容质量与可信度（先于扩平台）

| 缺口 | 现状 | 建议 |
|------|------|------|
| 链接可达性 | `resolved_url` 仍可能落到 gstatic 等；部分 Google News 链接需进一步解链。 | 在 `page_meta.py` 中强化 resolve 逻辑与 googlenewsdecoder 等 fallback；digest 可增加「链接状态」字段供前端/策略过滤。 |
| 噪音控制 | 样本中出现公司公告、停牌通知等，拉低信噪比。 | 在 `topic_filter.py` 或独立 filter 中增加负向规则/正则（如公告、停牌、财报摘要等），或增加「内容类型」标签在导出前过滤。 |

### 4.2 分发与触达（显著提升留存）

| 缺口 | 现状 | 建议 |
|------|------|------|
| 分发渠道 | 仅有 CLI + 本地/自建静态页，无推送。 | 在导出后增加分发任务：早报邮件（可复用/扩展现有 `scripts/send_email.py`）、飞书/钉钉/企微机器人，消费同一 digest JSON。 |
| 移动/随手可看 | 无 PWA、无移动端适配、无 IM 内触达。 | 先做邮件 + 机器人，再考虑响应式前端或 PWA。 |

### 4.3 统一事件卡与扩展字段

| 缺口 | 现状 | 建议 |
|------|------|------|
| 数据契约扩展 | digest 已有 headline/points/items；缺少影响级别、置信度、地区等。 | 在 `export_digest_json` 中增加可选字段（如 impact_level、region_tags），由后续 pipeline 或规则写入。 |
| 多终端一致 | 各终端需同一结构。 | 保持 digest 为单一事实来源，邮件/IM 模板从 digest 生成，不另建一套结构。 |

### 4.4 用户层与个性化（P1+）

| 缺口 | 现状 | 建议 |
|------|------|------|
| 用户与账号 | 无。 | 平台化时引入最小账号体系（如邮箱 + 验证）。 |
| 订阅偏好 | 无。 | 用户可选：主题、国家/地区、关键词、公司、时间窗。 |
| 告警与频率 | 无。 | 支持「每日早报」与「高频/重大事件即时提醒」等策略。 |
| 我的看板 / 历史 / 反馈 | 无。 | 「我的看板」、历史检索、收藏与反馈闭环，放在订阅与告警之后。 |

### 4.5 运维与可观测性

| 缺口 | 现状 | 建议 |
|------|------|------|
| 前端服务方式 | 需手动起 HTTP 服务并保证 `exports/` 可访问。 | 文档化「本地预览」步骤；平台化时改为 API 服务 + 静态资源或 CDN。 |
| 监控与指标 | 无标准化指标。 | 按规划引入打开率、7 日留存、人均阅读事件数、点击原文率、收藏/转发率等。 |

---

## 五、小结

- **流水线**：采集 → 规范化 → 去重聚类 → 主题过滤 → 热度排序 → 存储 → 多格式导出（含 digest），已形成完整内容生产线；可选 enrich + 摘要（抽取式/LLM）已就绪。  
- **前端**：单页日摘要、分类导航、聚类事件卡、热度榜、搜索与展开详情均已具备，且与 digest 契约一致，可作为 Daily Brief 平台的展示基础。  
- **可复用资产**：整条 pipeline、digest 数据契约、主题/热度/聚类/摘要/存储与前端原型均可直接复用或小幅扩展。  
- **平台化缺口**：需优先补齐**链接质量与噪音过滤**，再增加**分发层（邮件 + IM 机器人）**和**统一事件卡扩展字段**，最后再做用户体系、订阅、告警与历史/反馈。

完成上述梳理后，落地顺序建议与《新闻平台化建议方案》一致：先提质量与分发，再统一事件卡与多终端，最后补用户与个性化能力。
