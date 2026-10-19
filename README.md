# news-hotspot-mining

新闻热点挖掘与传播分析系统。

从中国主流新闻网站自动采集新闻 → 文本预处理 → 热点话题挖掘（TF-IDF + KMeans + LDA）→ 传播网络分析 → pyecharts 可视化仪表板。

---

## 技术流程

```
新闻爬取（6 个网页源 + 4 个 API 源）
         ↓
    MySQL 持久化（news_articles 表）
         ↓
  数据清洗（去重 / jieba 分词 / 停用词过滤 / TF-IDF 关键词）
         ↓
  热点挖掘（肘部法则 KMeans 聚类 + LDA 主题建模）
         ↓
  传播分析（跨源相似新闻建边 → networkx 有向图）
         ↓
  可视化仪表板（pyecharts，已离线化无需 CDN）
```

## 目录结构

| 路径 | 说明 |
|---|---|
| `main.py` | CLI 入口 |
| `run.py` | 交互式启动脚本 |
| `crawler/` | 网页爬虫 + API 爬虫 |
| `preprocessing/` | 文本清洗、分词、关键词提取 |
| `mining/` | KMeans 聚类 + LDA 主题建模 |
| `analysis/` | 传播网络构建、中心性、影响力 |
| `visualization/` | pyecharts 8 图表 + 综合仪表板 |
| `database/` | SQLAlchemy MySQL / Mongo 管理器 |
| `config/settings.py` | 运行参数（数据库、爬虫、聚类、LDA、可视化） |
| `config/local_settings.example.py` | 凭据覆盖示例（复制为 local_settings.py 后填入） |
| `data/visualizations/assets/` | 本地 ECharts JS（离线化） |
| `setup_database.sql` | 建库建表脚本 |
| `requirements.txt` | 依赖清单 |

## 环境要求

- Python 3.10+
- MySQL 5.7+ 或 8.0（默认用户 root，库 news_hotspot，端口 3306）
- pip（依赖版本见 requirements.txt，已锁定）

## 安装

```bash
# 克隆后进入项目目录
cd news-hotspot-mining

# 创建虚拟环境（可选但推荐）
python -m venv .venv
.venv\Scripts\activate          # Windows PowerShell / cmd
# source .venv/bin/activate    # Linux / macOS

# 安装依赖
pip install -r requirements.txt

# 初始化数据库
mysql -u root -p < setup_database.sql
```

## 数据库凭据（脱敏）

项目已去掉硬编码密码，按优先级读取：

1. **环境变量**（推荐）：
   ```bash
   # Windows cmd
   set MYSQL_PASSWORD=your_password
   set MYSQL_USER=root
   # PowerShell
   $env:MYSQL_PASSWORD="your_password"
   ```

2. **本地覆盖文件**：复制 `config/local_settings.example.py` 为 `config/local_settings.py`，填入真实密码。该文件已在 `.gitignore` 中。

未设置任何凭据时默认密码为空，适合本地 root 无密码的开发场景。

## 运行

```bash
# 分析已有数据（最快，只需 MySQL 有数据）
python main.py --mode analyze

# 完整流水线：爬取 + 清洗 + 挖掘 + 分析 + 可视化
python main.py --mode full --max-news 50

# 仅爬取
python main.py --mode crawl --max-news 50

# 定时守护进程（每 15 分钟一轮）
python main.py --mode scheduled

# 查看参数
python main.py --help
```

## 查看可视化图表

仪表板是 pyecharts 生成的 HTML，内含本地 ECharts JS（`data/visualizations/assets/`）。用 HTTP 服务打开（不要 `file://` 直接双击）：

```bash
cd news-hotspot-mining
python -m http.server 8765
# 浏览器打开 http://127.0.0.1:8765/data/visualizations/dashboard.html
```

## 数据来源

| 源 | 类型 | 说明 |
|---|---|---|
| 新华网 | RSS + 网页 | politics.news.cn RSS 列表 + 详情爬取 |
| 人民网 | RSS | www.people.com.cn/rss/politics.xml + 备用 society.xml |
| 新浪新闻 | RSS | rss.sina.com.cn/news/china/focus15.xml |
| 网易新闻 | 网页 | news.163.com 国内频道列表 + 详情 |
| 网易新闻API | 接口 | 3g.163.com/touch/reconstruct/article/list/ 三个板块 |
| 中国新闻网 | RSS + 网页 | chinanews.com RSS + 滚动新闻页 |

**注意**：
- 今日头条 API / 腾讯新闻 API 接口已失效，代码有空响应保护，不会崩溃，返回 0 条。
- 各新闻站可能因反爬/改版导致部分源获取失败，属正常降级，系统会继续处理其他源。

## 分析结果

程序跑完后生成：

| 文件 | 位置 | 说明 |
|---|---|---|
| 清洗后数据 | `data/cleaned_news_*.csv` | 带分词/关键词/长度字段，22 列 |
| 热点报告 | `data/reports/hotspot_report_*.json` | 聚类数、样本数、Top 话题、关键词 |
| 传播报告 | `data/reports/propagation_report_*.json` | 源分布、网络图、影响力指标 |
| 仪表板 | `data/visualizations/dashboard.html` | 8 个图表的综合页面 |
| 模块 A 仪表板 | `data/visualizations/news_scope_dashboard.html` | 可下钻分析页：`python visualization/news_scope_dashboard.py` 重新生成 |

## 已知限制

- **互动量数据当前不可用**：历史互动字段经逐来源核验确认为随机生成，已按字段级清单（`data/reports/engagement_provenance.json`）在内存中全部隔离为「未知」（缺失≠0，不修改数据库）。本次重跑后互动量覆盖率 0/111，热点评分不计入互动项，传播互动统计返回 `insufficient_data`；任何互动量比较、热度排名结论均不可声称。重新采集的真实数据（crawl_time 晚于清单 cutoff）不受影响。

- **聚类效果受样本量影响大**：百级样本下轮廓系数通常 < 0.15，建议累积千级以上数据再看聚类质量。
- **传播网络建边严格**：基于 TF-IDF 余弦相似度 + 时间窗口建边，阈值敏感；样本少时可能 0 边。该图在界面展示为「新闻源相似关系网络」，**表示内容相似与时间先后，不代表已证实的转载路径**；数据不足时显示「传播关系数据不足」提示，不填充任何虚构节点或边。
- **互动热力图空白格**：无新闻样本的「小时×星期」时间格显示为空白（未填充 0），与真实互动量为 0 的格区分；空白格无 tooltip。
- **部分 API 已失效**：头条/腾讯 API 接口已关，代码保留但返回 0 条。
- **可视化依赖 HTTP 服务**：pyecharts 生成的 HTML 用 iframe 组合，需 HTTP server 才能正常加载。
- **无 README 里的截图**：本 README 为后续补充，截图请自行在浏览器打开仪表板后保存。

## 项目修改记录

| 日期 | 内容 |
|---|---|
| 2026-10-14 | 初次运行诊断：补 scipy==1.12.0 依赖（gensim 4.3.1 兼容） |
| 2026-10-14 | 可视化离线化：下载 ECharts JS，设置 pyecharts ONLINE_HOST=assets/ |
| 2026-10-14 | 修复 db_manager.insert_news 重复键导致整批回滚 |
| 2026-10-14 | 修复 api_crawler 头条/腾讯空响应保护 |
| 2026-10-14 | 人民网 RSS 换源（politics.people.com.cn → www.people.com.cn） |
| 2026-10-14 | 传播分析阈值下调（相似度 0.3→0.15，时间 24h→72h） |
| 2026-10-15 | 第二阶段：脱敏配置（环境变量 + local_settings）、补 README、加 .gitignore |
| 2026-10-16 | P0-1：删除传播网络图硬编码伪造数据；空图/无边显示「数据不足」提示；接入真实传播图；标题改为「新闻源相似关系网络」（详见 P0_ACCEPTANCE.md） |
| 2026-10-16 | P0-2：互动热力图无样本时间格不再填 0（改为空白格），tooltip 区分「无数据」与真实 0 |
| 2026-10-17 | 互动量可信性修复：采集层删除全部随机互动值与发布时间兜底（缺失=NULL）；ORM 移除 default=0；清洗层不再用 0 填互动缺失、不用当前时间填发布缺失；新增字段级质量清单 `data/reports/engagement_provenance.json`，历史 130 条 × 3 字段共 390 个值全部隔离为未知（内存级，不改数据库）；热点评分/传播统计全面 NaN-safe；传播分析按标题去重（修复同源重复采集造成的伪传播边，边数从密集伪网降为 2 条真实跨源边） |
| 2026-10-17 | 模块 A 仪表板升级：图表点击联动筛选 + 日期筛选 + 单条新闻详情面板 + 结果解释区（轮廓系数披露、来源×主题交叉表、聚类关键词、结论边界） |
| 2026-10-17 | 新增验证：`tests/test_engagement_integrity.py` 内存测试 5/5 通过；`scripts/verify_null_write.py` MySQL 回滚式 NULL 写入验证通过（显式 None→SQL NULL，显式 0→0，事务回滚无持久化） |
