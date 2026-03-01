按你想做的事选一种方式即可：

---

## 1. 完整流水线（抓取 + 处理 + 导出）

```bash
cd /Users/shens/projects/news_summary
pip install -r requirements.txt   # 首次需要
python run.py run
```

会：抓取 RSS → 去重/聚类/排序 → 存库 → 导出到 exports/。

---

## 2. 分步运行

```bash
cd /Users/shens/projects/news_summary

# 只抓取并入库
python run.py fetch

# 只从数据库导出（不抓取）
python run.py export --limit 40

# 导出 digest（给前端每日总结页用）
python run.py export --formats txt,md,digest --limit 40
```

---

## 3. 端到端验证（用当日导出做校验）

```bash
cd /Users/shens/projects/news_summary

# 先导出 digest
python run.py export --formats txt,md,digest --limit 40

# 再跑验证
python3 scripts/validate_e2e.py
```

---

## 4. 其他常用命令

```bash
python run.py stats                    # 看数据库统计
python run.py sources                  # 列出所有新闻源
python run.py fetch --source reuters   # 只抓 reuters
```

---

## 5. 本地查看前端（每日摘要页）

前端会请求 `/exports/latest_digest.json`，所以要在**项目根目录**起一个静态服务器，再在浏览器里打开前端页面。

**步骤一：确保有 digest 数据（二选一）**

- 已有数据：若 `exports/latest_digest.json` 存在，可跳过。
- 需要新数据：先跑一次导出生成 digest：
  ```bash
  cd /Users/shens/projects/news_summary
  python run.py export --formats txt,md,digest --limit 40
  ```

**步骤二：在项目根目录启动静态服务器**

```bash
cd /Users/shens/projects/news_summary
python -m http.server 8000
```

**步骤三：在浏览器打开**

- 打开：**http://localhost:8000/frontend/index.html**
- 即可看到「新闻热点总结」页：按分类看聚类、要点、热度榜，点击标题跳原文。

关掉服务：在终端按 `Ctrl+C`。

注意：若系统里只能用 `python3`，把上面的 `python` 换成 `python3`。