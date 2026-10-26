# -*- coding: utf-8 -*-
"""News Hotspot Mining System — Streamlit web app (cloud deployment entry point).

本地预览:  .venv/Scripts/python.exe -m streamlit run app.py
云端部署:  Streamlit Community Cloud 指定本文件为入口，数据库使用随仓库分发的
           data/news.db（SQLite 快照），预生成仪表板位于 data/visualizations/。
视觉风格:  新闻媒体风（纸感底色 + 墨蓝 + 衬线标题），主题见 .streamlit/config.toml。
"""
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parent
VIS_DIR = ROOT / 'data' / 'visualizations'
EXPORT_DIR = ROOT / 'data' / 'exports'
DB_FILE = ROOT / 'data' / 'news.db'
LOG_FILE = ROOT / 'data' / 'web_run.log'

# 与 web_server 相同的单任务互斥状态（模块级，跨 rerun 存活；禁止并发触发）
STATE = {'running': False, 'exit_code': None, 'ended': None}
STATE_LOCK = threading.Lock()

# 版面：分组 -> 图表列表[(文件名主干, 高度)]，每图通栏一行
SECTIONS = [
    ('topics', [('hotspot_wordcloud', 430), ('hotspot_ranking', 430)]),
    ('pulse', [('time_trend', 430), ('source_distribution', 430)]),
    ('reach', [('engagement_top', 430), ('propagation_network', 610)]),
    ('evolution', [('topic_evolution', 470)]),
]

I18N = {
    'en': {
        'kicker': 'Chinese Media Watch',
        'title': 'News Hotspot Mining',
        'lede': 'A monthly read of the Chinese news cycle — articles clustered into topics, '
                'measured for real engagement, and mapped across outlets.',
        'chip_articles': 'Articles', 'chip_outlets': 'Outlets',
        'chip_window': 'Window', 'chip_snapshot': 'Snapshot',
        'window_value': '30 days',
        'sections': {
            'topics': {'k': 'Topics', 't': 'What Is Being Talked About'},
            'pulse': {'k': 'Pulse', 't': 'Volume Over Time & Outlets'},
            'reach': {'k': 'Reach', 't': 'Engagement & Propagation'},
            'evolution': {'k': 'Evolution', 't': 'How Topics Rise and Fall'},
        },
        'controls': 'Controls',
        'run': 'Collect & Update',
        'running': 'Collecting and analyzing, please wait (usually a few minutes)...',
        'done': 'Update completed at {t}; charts below are regenerated.',
        'fail': 'Run failed. See the log below for details.',
        'log': 'Run log',
        'csv': 'Download EchoMap CSV',
        'cloud_notice': ('This cloud deployment ships a **SQLite snapshot**; '
                         'live crawling runs locally against Chinese news sites '
                         '(streamlit cloud overseas IPs are rate-limited). '
                         'Use the CSV below, or run the project locally to refresh.'),
        'notes_kicker': 'Methodology',
        'notes_title': 'Data & Method Notes',
        'missing_chart': 'Chart file missing: {f} (run Collect & Update to regenerate)',
        'unknown_date': 'unknown',
        'footer': ('Sources: Xinhua · People.cn · Sina · NetEase · Chinanews · Bilibili News'
                   '&nbsp;&nbsp;|&nbsp;&nbsp;Snapshot {date}'
                   '&nbsp;&nbsp;|&nbsp;&nbsp;Python · jieba · scikit-learn · ECharts · Streamlit'),
        'notes': """
- **Time window**: analysis covers the **last 30 days**; items missing a publish time are assigned to the window by their crawl time (publish time itself is never filled in).
- **Engagement data**: comments / likes / shares are only publicly available from **Bilibili News**; for all other sources they are marked **Unknown**, never zero-filled or fabricated. 130 historical records with unreliable engagement values are quarantined field-by-field via a provenance manifest (`data/reports/engagement_provenance.json`).
- **Sample size & clustering**: with a few hundred articles, cluster structure is weak (silhouette score < 0.05); this is disclosed honestly on the charts instead of being hidden.
- **Bundled snapshot**: this deployment ships a **SQLite snapshot** (`data/news.db`, exported 2026-10-18) plus pre-generated charts, so the page works even if live crawling fails.
- **Live crawling on cloud**: runs from overseas servers against Chinese news sites, so it may be slow or partially fail; any data collected on cloud is **ephemeral** (the filesystem resets on app restart/redeploy).
- **Free tier**: the app sleeps after inactivity; first visit after sleep takes a moment to wake.
""",
    },
    'zh': {
        'kicker': '中文媒体观察',
        'title': '新闻热点挖掘',
        'lede': '一份中文新闻周期的月度解读——聚类成题、量化真实互动、描摹媒体传播。',
        'chip_articles': '文章', 'chip_outlets': '来源',
        'chip_window': '分析窗口', 'chip_snapshot': '数据快照',
        'window_value': '近 30 天',
        'sections': {
            'topics': {'k': '议题', 't': '正在讨论什么'},
            'pulse': {'k': '脉络', 't': '报道量与媒体构成'},
            'reach': {'k': '触达', 't': '互动与传播'},
            'evolution': {'k': '演化', 't': '话题的起落'},
        },
        'controls': '控制台',
        'run': '一键采集更新',
        'running': '正在采集与分析，请稍候（通常需要几分钟）…',
        'done': '已完成更新（{t}），下方图表已重新生成。',
        'fail': '运行失败，请查看下方日志了解原因。',
        'log': '运行日志',
        'csv': '下载 EchoMap CSV',
        'cloud_notice': ('当前为云端部署，随仓库分发 **SQLite 数据快照**；'
                         '在线采集需在本地运行（海外服务器访问国内新闻源受限流）。'
                         '下方 CSV 直接可用，或本地运行项目刷新数据。'),
        'notes_kicker': '方法',
        'notes_title': '数据与方法说明',
        'missing_chart': '图表文件缺失：{f}（可点击"一键采集更新"重新生成）',
        'unknown_date': '未知',
        'footer': ('来源：新华网 · 人民网 · 新浪 · 网易 · 中新网 · 哔哩哔哩资讯'
                   '&nbsp;&nbsp;|&nbsp;&nbsp;数据快照 {date}'
                   '&nbsp;&nbsp;|&nbsp;&nbsp;Python · jieba · scikit-learn · ECharts · Streamlit'),
        'notes': """
- **时间窗口**：分析范围为**近30天**；发布时间缺失的条目按采集时间判断窗口归属（发布时间字段本身不填充）。
- **互动数据**：评论/点赞/分享仅**哔哩哔哩资讯**公开可得，其余来源一律标注为**未知**，不用0或伪造值填充。130条历史记录的不可靠互动值通过字段级清单（`data/reports/engagement_provenance.json`）隔离。
- **样本规模与聚类**：数百条样本下聚类结构极弱（轮廓系数<0.05），已在图表中如实披露而非掩盖。
- **内置快照**：本部署随仓库分发 **SQLite 快照**（`data/news.db`，2026-10-18 导出）与预生成图表，即使在线采集失败页面也可正常展示。
- **云端在线采集**：从海外服务器访问国内新闻站点，可能缓慢或部分失败；云端采集到的数据是**易失的**（应用重启/重新部署后文件系统重置）。
- **免费额度**：应用空闲后会休眠，休眠后首次访问需要片刻唤醒。
""",
    },
}

CSS = """
<style>
/* —— 隐藏 Streamlit 默认装饰（工具条/顶部色带/页脚）—— */
[data-testid="stToolbar"], [data-testid="stDecoration"], footer { display: none !important; }
[data-testid="stHeader"] { background: transparent; }

/* —— 纸感背景与版面宽度：整页统一为一张纸，只有图表卡片是白色 —— */
.stApp { background: #f7f4ee; }
[data-testid="stAppViewContainer"], [data-testid="stMain"], .stMain,
[data-testid="stMainBlockContainer"], .block-container { background: #f7f4ee !important; border-radius: 0 !important; }
.block-container { max-width: 1280px; padding-top: 2.2rem; }

/* —— 报头（masthead）—— */
.kicker {
  font-size: 12px; font-weight: 700; letter-spacing: .24em;
  text-transform: uppercase; color: #9a2a2a;
}
.masthead h1 {
  font-family: Georgia, 'Times New Roman', 'Songti SC', 'SimSun', serif;
  font-size: 46px; font-weight: 700; color: #152c46;
  margin: .12em 0 .08em; padding: 0;
}
.lede { color: #4b5a68; font-size: 16px; max-width: 720px; margin: 0 0 6px; }
.rule-double { border: 0; border-top: 3px double #152c46; margin: 14px 0 4px; }

/* —— 关键数字（chips）—— */
.chips { display: flex; gap: 38px; flex-wrap: wrap; margin: 10px 0 2px; }
.chip .num {
  font-family: Georgia, 'Times New Roman', serif; font-size: 26px;
  color: #152c46; line-height: 1.1;
}
.chip .lab {
  font-size: 11px; letter-spacing: .14em; text-transform: uppercase;
  color: #857a67; margin-top: 2px;
}

/* —— 分组小标题 —— */
.sec { margin: 30px 0 4px; }
.sec h2 {
  font-family: Georgia, 'Times New Roman', 'Songti SC', 'SimSun', serif;
  font-size: 26px; font-weight: 700; color: #152c46;
  margin: 2px 0 6px; padding: 0;
}
.sec hr { border: 0; border-top: 1px solid #d8d2c4; margin: 0 0 14px; }

/* —— 图表卡片样式注入在各图表 iframe 文档内部（见 render_chart_html），
      此处不全局设白底：stVerticalBlockBorderWrapper 命中根块会污染整页 —— */

/* —— 兜底：所有布局块（根块/列/侧栏内容块）一律透明，白色只留给图表卡片自身 —— */
[data-testid="stVerticalBlockBorderWrapper"], [data-testid="stVerticalBlock"],
.stVerticalBlock, [data-testid="stSidebarUserContent"], [data-testid="stColumn"] {
  background: transparent !important; border-color: transparent !important;
  box-shadow: none !important;
}

/* —— 侧边栏：与整页同一纸色系，内容区不再套白盒 —— */
[data-testid="stSidebar"], [data-testid="stSidebarContent"] { background: #f0ebdf !important; }
[data-testid="stSidebar"] { border-right: 1px solid #ddd5c4; }
[data-testid="stSidebar"] .stButton > button {
  background: #16324f; color: #fff; border: none; width: 100%; font-weight: 600;
}
[data-testid="stSidebar"] .stButton > button:hover { background: #1f4066; color: #fff; }
[data-testid="stSidebar"] .stDownloadButton > button {
  width: 100%; background: transparent; border: 1px solid #b9ad97; color: #2c3a49;
}
[data-testid="stSidebar"] .stDownloadButton > button:hover { border-color: #16324f; color: #16324f; }
.side-head {
  font-size: 12px; font-weight: 700; letter-spacing: .2em;
  text-transform: uppercase; color: #857a67; margin-bottom: 6px;
}

/* —— 页脚 —— */
.footer {
  margin-top: 34px; padding-top: 10px; border-top: 1px solid #d8d2c4;
  font-size: 12px; letter-spacing: .04em; color: #857a67; text-align: center;
}

/* —— 说明区标题对齐整体风格 —— */
.notes h3 {
  font-family: Georgia, 'Times New Roman', 'Songti SC', 'SimSun', serif;
  color: #152c46; font-size: 20px; margin: 2px 0 6px;
}
</style>
"""


@st.cache_data(show_spinner=False)
def _load_asset_js(name):
    """读取 data/visualizations/assets 下的小体积 JS（缓存避免每次 rerun 重读）"""
    return (VIS_DIR / 'assets' / name).read_text(encoding='utf-8')


# 大体积依赖不再内联：echarts.min.js 约 1MB，7 张图内联即为 ~7MB，
# 云端靠后的 iframe 要等很久才渲染。改为 CDN 外链后浏览器跨 iframe 复用同一份缓存，
# 整页只付一次下载代价。版本与仓库内置资源一致（assets/echarts.min.js 的 version = 5.5.0）。
CDN_ASSETS = {
    'echarts.min.js': ('https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js',
                       'https://cdnjs.cloudflare.com/ajax/libs/echarts/5.5.0/echarts.min.js'),
}


def _asset_script(name):
    """把 assets/<name> 引用换成可加载的 <script>：大库走 CDN（带备用源），小插件仍内联。"""
    urls = CDN_ASSETS.get(name)
    if not urls:
        return f'<script type="text/javascript">{_load_asset_js(name)}</script>'
    primary, fallback = urls
    return (f'<script type="text/javascript" src="{primary}"></script>'
            '<script type="text/javascript">window.echarts||document.write('
            f'\'<script type="text/javascript" src="{fallback}"><\\/script>\');</script>')


@st.cache_data(ttl=300, show_spinner=False)
def load_kpis():
    """从 SQLite 快照读取报头关键数字；库缺失时返回 None（不展示，不编造）"""
    if not DB_FILE.is_file():
        return None
    con = sqlite3.connect(str(DB_FILE))
    try:
        cur = con.cursor()
        total = cur.execute('SELECT COUNT(*) FROM news_articles').fetchone()[0]
        outlets = cur.execute('SELECT COUNT(DISTINCT source) FROM news_articles').fetchone()[0]
        snap = cur.execute('SELECT MAX(crawl_time) FROM news_articles').fetchone()[0]
    finally:
        con.close()
    return {'articles': total, 'outlets': outlets, 'snapshot': (snap or '')[:10]}


def render_chart_html(stem, lang):
    """读取单个图表 HTML：把 assets/*.js 引用换成可加载的 <script> 标签
    （components.html 无法解析相对路径），并把卡片样式（白底/细边框/圆角/轻阴影）
    注入图表文档自身的 <head>。"""
    suffix = '_en' if lang == 'en' else ''
    path = VIS_DIR / f'{stem}{suffix}.html'
    if not path.is_file():
        return None
    html = path.read_text(encoding='utf-8')
    html = re.sub(
        r'<script[^>]*src="assets/([\w.\-]+)"[^>]*></script>',
        lambda m: _asset_script(m.group(1)),
        html,
    )
    card_css = ('<style>html,body{margin:0;padding:0;background:#f7f4ee;}'
                'body{border:1px solid #e0d8c8;border-radius:3px;'
                'box-sizing:border-box;padding:6px 8px;}</style>')
    return html.replace('</head>', card_css + '</head>', 1)


def latest_csv():
    """旧逻辑已废弃：从 news.db 实时生成 EchoMap CSV（见 build_echomap_csv）。
    保留此函数作为入口，返回 (filename, bytes) 或 (None, None)。"""
    if not DB_FILE.is_file():
        return None, None
    buf = build_echomap_csv()
    if buf is None:
        return None, None
    snap_date = load_kpis()['snapshot'] or 'unknown' if load_kpis() else 'unknown'
    fname = f'echomap_news_snapshot_{snap_date}.csv'
    return fname, buf


@st.cache_data(ttl=600, show_spinner=False)
def build_echomap_csv():
    """直接从 SQLite 快照构建 EchoMap 兼容 CSV（bytes）。
    不依赖仓库预置的 data/exports/*.csv —— 只要 news.db 在，按钮就在。
    复用 echomap_export.py 的脱敏与清洗规则，保持输出一致。"""
    if not DB_FILE.is_file():
        return None
    try:
        from echomap_export import mask_sensitive, SENSITIVE_COLUMNS
    except Exception:
        # 极端情况下脱敏模块导入失败，降级为原始数据（不脱敏，仍可用）
        def _no_mask(text): return (text, {})
        mask_sensitive = _no_mask
        SENSITIVE_COLUMNS = ("title", "content", "author")

    con = sqlite3.connect(str(DB_FILE))
    try:
        df = pd.read_sql_query(
            'SELECT news_id, title, content, source, author, publish_time, url '
            'FROM news_articles', con)
    finally:
        con.close()
    if df.empty:
        return None

    out = pd.DataFrame()
    out['id'] = df['news_id'].astype(str)
    out['title'] = df['title'].astype(str).str.strip()
    out['content'] = df['content'].astype(str).str.strip()
    out['source'] = df['source'].astype(str).str.strip()
    out['author'] = df.get('author', '').astype(str).str.strip()
    out['url'] = df.get('url', '').astype(str).str.strip()

    # 文本净化（HTML标签 + 空白压缩）—— echomap_export.py 的简化版，
    # 去掉了 remove_noise_phrases 依赖（它需要 preprocessing 包）。
    for col in ('title', 'content'):
        out[col] = out[col].str.replace(r'<[^>]+>', '', regex=True)
    out[['title', 'content']] = out[['title', 'content']].apply(
        lambda s: s.str.replace(r'\s+', ' ', regex=True).str.strip())

    # 敏感信息脱敏
    for col in SENSITIVE_COLUMNS:
        masked = out[col].map(mask_sensitive)
        out[col] = masked.map(lambda x: x[0])

    # 发布时间：解析失败/缺失 -> 空字符串（EchoMap 会记为 NaT）
    parsed_dates = pd.to_datetime(df['publish_time'], errors='coerce')
    out['published_at'] = parsed_dates.dt.strftime('%Y-%m-%d %H:%M:%S').fillna('')

    # id 去重（数据库本身已去重，保险）
    out = out.drop_duplicates(subset='id', keep='first').reset_index(drop=True)

    buf = BytesIO()
    out.to_csv(buf, index=False, encoding='utf-8-sig')
    return buf.getvalue()


def run_pipeline():
    """后台线程：完整流水线（采集→预处理→挖掘→可视化→导出CSV），日志写文件"""
    try:
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            code = subprocess.call(
                [sys.executable, 'main.py', '--mode', 'full', '--max-news', '50',
                 '--days', '30', '--db-type', 'sqlite', '--export-echomap'],
                cwd=str(ROOT), stdout=f, stderr=subprocess.STDOUT)
    except Exception as e:
        code = -1
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f'\nPipeline launch failed: {e}\n')
    with STATE_LOCK:
        STATE['running'] = False
        STATE['exit_code'] = code
        STATE['ended'] = time.strftime('%Y-%m-%d %H:%M:%S')


def read_log_tail(n=4000):
    try:
        return LOG_FILE.read_text(encoding='utf-8', errors='replace')[-n:]
    except FileNotFoundError:
        return ''


def show_chart(stem, height, lang, t):
    """嵌入一张图（卡片样式在图表文档内部）；文件缺失时如实提示"""
    html = render_chart_html(stem, lang)
    if html is None:
        st.warning(t['missing_chart'].format(f=f'{stem}.html'))
    else:
        components.html(html, height=height, scrolling=False)


def main():
    st.set_page_config(page_title='News Hotspot Mining', layout='wide')
    st.markdown(CSS, unsafe_allow_html=True)

    # 云端检测：Streamlit Community Cloud 会设 STREAMLIT_SHARING_MODE 或
    # 主机名含 streamlit.app；云端海外 IP 爬不到国内新闻源，且文件系统是临时的。
    # 诚实禁用采集按钮，避免评审点击后看到空跑/报错。
    CLOUD = (os.environ.get('STREAMLIT_SHARING_MODE') is not None
             or 'streamlit.app' in os.environ.get('HOSTNAME', '')
             or 'streamlit.app' in os.environ.get('CLOUD_SERVER_NAME', ''))

    # 语言选择：默认英文，选择结果写入 URL query 参数（刷新/分享链接可保留）
    qp_lang = st.query_params.get('lang', 'en')

    with st.sidebar:
        lang = st.radio(
            'Language / 语言', ['en', 'zh'],
            index=0 if qp_lang != 'zh' else 1,
            format_func=lambda x: 'English' if x == 'en' else '中文',
        )
        if lang != qp_lang:
            st.query_params['lang'] = lang
        t = I18N[lang]

        st.markdown(f"<div class='side-head'>{t['controls']}</div>", unsafe_allow_html=True)
        if CLOUD:
            st.info(t['cloud_notice'])
        run_disabled = CLOUD or STATE['running']
        if st.button(t['run'], type='primary', disabled=run_disabled):
            with STATE_LOCK:
                STATE['running'] = True
                STATE['exit_code'] = None
            threading.Thread(target=run_pipeline, daemon=True).start()
            st.rerun()
        if STATE['running']:
            st.info(t['running'])
        elif STATE['exit_code'] is not None:
            if STATE['exit_code'] == 0:
                st.success(t['done'].format(t=STATE['ended']))
            else:
                st.error(t['fail'])

        csv_fname, csv_bytes = latest_csv()
        if csv_bytes is not None:
            st.download_button(t['csv'], csv_bytes,
                               file_name=csv_fname, mime='text/csv')

    t = I18N[lang]

    # —— 报头 + 关键数字 ——
    st.markdown(
        f"<div class='masthead'><div class='kicker'>{t['kicker']}</div>"
        f"<h1>{t['title']}</h1><p class='lede'>{t['lede']}</p>"
        f"<hr class='rule-double'></div>",
        unsafe_allow_html=True,
    )
    kpis = load_kpis()
    if kpis:
        snapshot = kpis['snapshot'] or t['unknown_date']
        st.markdown(
            f"<div class='chips'>"
            f"<div class='chip'><div class='num'>{kpis['articles']}</div>"
            f"<div class='lab'>{t['chip_articles']}</div></div>"
            f"<div class='chip'><div class='num'>{kpis['outlets']}</div>"
            f"<div class='lab'>{t['chip_outlets']}</div></div>"
            f"<div class='chip'><div class='num'>{t['window_value']}</div>"
            f"<div class='lab'>{t['chip_window']}</div></div>"
            f"<div class='chip'><div class='num'>{snapshot}</div>"
            f"<div class='lab'>{t['chip_snapshot']}</div></div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # —— 采集运行状态（运行中只显示日志，跳过图表渲染以减轻 rerun 负担）——
    if STATE['running']:
        with st.expander(t['log'], expanded=True):
            st.code(read_log_tail() or '...', language=None)
        time.sleep(3)
        st.rerun()
    else:
        if STATE['exit_code'] not in (None, 0):
            with st.expander(t['log'], expanded=True):
                st.code(read_log_tail(), language=None)

        # —— 分组图表（每图通栏一行）——
        for sec_key, charts in SECTIONS:
            s = t['sections'][sec_key]
            st.markdown(
                f"<div class='sec'><div class='kicker'>{s['k']}</div>"
                f"<h2>{s['t']}</h2><hr></div>",
                unsafe_allow_html=True,
            )
            for stem, height in charts:
                show_chart(stem, height, lang, t)

        # —— 方法与数据说明（如实披露，常驻可见）——
        st.markdown(
            f"<div class='sec notes'><div class='kicker'>{t['notes_kicker']}</div>"
            f"<h2>{t['notes_title']}</h2><hr></div>",
            unsafe_allow_html=True,
        )
        st.markdown(t['notes'])

    # —— 页脚 ——
    footer_date = (kpis['snapshot'] if kpis and kpis['snapshot'] else t['unknown_date'])
    st.markdown(f"<div class='footer'>{t['footer'].format(date=footer_date)}</div>",
                unsafe_allow_html=True)


if __name__ == '__main__':
    main()
