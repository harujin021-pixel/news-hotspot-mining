# -*- coding: utf-8 -*-
"""
EchoMap 兼容 CSV 导出（Hot-Mining 侧适配层，独立功能，不影响原有流程）

字段规范来源（已核实，非自行设计）：
    EchoMap 项目 src/data/loader.py ——
    必需列: title, content, source
    可选列: id, author, published_at, url
    导入编码依次尝试: utf-8-sig / utf-8 / gbk
    EchoMap 清洗(src/data/cleaning.py)：文本去首尾空白；published_at 用
    pd.to_datetime(format="mixed", errors="coerce") 解析（失败记 NaT，不删行）；
    删除必需列为空的行；删除完全重复行。

映射关系（Hot-Mining -> EchoMap）：
    news_id      -> id            （内容哈希，跨次采集稳定）
    title        -> title         （原始标题，不改动）
    content      -> content       （原始正文，不改动）
    source       -> source        （原始来源名）
    author       -> author        （缺失留空，不编造）
    publish_time -> published_at  （格式 YYYY-MM-DD HH:MM:SS；缺失留空，
                                    EchoMap 解析为 NaT 但保留该行）
    url          -> url           （缺失留空）

附加分析列（可选，均为真实计算结果，不冒充新闻事实）：
    hotspot_cluster  聚类编号（-1 为噪声点）
    hotspot_score    话题热度分数（口径=新闻数量+真实互动量(缺失不计入)+时间因子）
    topic_keywords   话题 Top3 关键词（TF-IDF/TextRank 提取结果）

编码策略：utf-8-sig（EchoMap 候选编码首位；同时保证 Excel 打开中文不乱码）。

敏感信息脱敏：导出前对 title/content/author 三列做个人信息过滤，检出即替换为
占位符（[邮箱]/[身份证号]/[手机号]），脱敏数量写入导出报告如实披露；不做静默
删除或改写其它内容，也不影响行数与热点分析列。
"""
import logging
import os
import re
from datetime import datetime

import pandas as pd

from preprocessing.text_processor import remove_noise_phrases

logger = logging.getLogger(__name__)

# 敏感信息识别模式（按序替换；邮箱在前，避免其数字局部先被手机号规则截断）。
# 负向断言排除两类误报：URL/文件路径片段（前导"/"或后随图片扩展名）、更长数字串内部
_NO_FILE = r"(?!\.(?:png|jpe?g|gif|webp|bmp|svg|css|js))"
SENSITIVE_PATTERNS = [
    ("邮箱", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("身份证号", re.compile(r"(?<![/\d])\d{17}[\dXx](?!\d)" + _NO_FILE)),
    ("手机号", re.compile(r"(?<![/\d])1[3-9]\d{9}(?!\d)" + _NO_FILE)),
]
# 需要脱敏的导出列（正文/标题/作者；source 为机构名、url 为页面地址，不在此列）
SENSITIVE_COLUMNS = ("title", "content", "author")

# 18 位身份证号校验（GB 11643 mod-11-2）：排除图片文件名等 18 位数字的误报
_ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_ID_CHECK = "10X98765432"


def _valid_id18(num):
    """校验 18 位身份证号校验码是否合法；非法视为普通数字串，不脱敏。"""
    try:
        s = sum(int(num[i]) * _ID_WEIGHTS[i] for i in range(17))
    except ValueError:
        return False
    return _ID_CHECK[s % 11] == num[17].upper()


def mask_sensitive(text):
    """脱敏文本中的个人信息（邮箱/身份证号/手机号），返回 (脱敏后文本, 命中计数)。"""
    if text is None or text == "":
        return text, {}
    out = str(text)
    hits = {}
    for name, pat in SENSITIVE_PATTERNS:
        if name == "身份证号":
            # 仅替换校验码合法的身份证号，其余 18 位数字串原样保留
            n = 0

            def _repl(m):
                nonlocal n
                if _valid_id18(m.group()):
                    n += 1
                    return f"[{name}]"
                return m.group()

            out = pat.sub(_repl, out)
            if n:
                hits[name] = n
        else:
            out, n = pat.subn(f"[{name}]", out)
            if n:
                hits[name] = n
    return out, hits

# 导出的核心列（严格按 EchoMap 规范命名与顺序）
CORE_COLUMNS = ["id", "title", "content", "source", "author", "published_at", "url"]
# 附加分析列（仅在传入真实热点挖掘结果时出现）
EXTRA_COLUMNS = ["hotspot_cluster", "hotspot_score", "topic_keywords"]
REQUIRED = ("title", "content", "source")  # EchoMap 必需列


def export_echomap_csv(df, hotspot_results=None, output_dir="data/exports", days_note=None):
    """将 Hot-Mining 新闻数据导出为 EchoMap 兼容 CSV。

    参数:
        df: 清洗后的新闻 DataFrame（含 news_id/title/content/source/author/
            publish_time/url 等真实字段）。
        hotspot_results: 可选，mining.hotspot_miner 的真实挖掘结果；
            提供时按行对齐附加 hotspot_cluster/hotspot_score/topic_keywords。
        output_dir: 输出目录（默认 data/exports）。
        days_note: 分析时间窗口说明（仅写入导出报告，不改动数据）。

    返回:
        (csv_path, report) —— 导出文件路径与导出前后检查报告。
    """
    os.makedirs(output_dir, exist_ok=True)
    report = {"rows_in": int(len(df)), "checks": [], "warnings": []}

    out = pd.DataFrame()
    out["id"] = df["news_id"].astype(str)
    out["title"] = df["title"].astype(str).str.strip()
    out["content"] = df["content"].astype(str).str.strip()
    out["source"] = df["source"].astype(str).str.strip()
    out["author"] = df.get("author", "").astype(str).str.strip()
    out["url"] = df.get("url", "").astype(str).str.strip()

    # 文本净化（title/content）：去HTML标签 → 去模板词组（图为/编辑标注/导流语等）→ 压缩空白
    noise_hits = 0
    for col in ("title", "content"):
        out[col] = out[col].str.replace(r"<[^>]+>", "", regex=True)
        cleaned = out[col].map(remove_noise_phrases)
        out[col] = cleaned.map(lambda x: x[0])
        noise_hits += int(cleaned.map(lambda x: x[1]).sum())
    out[["title", "content"]] = out[["title", "content"]].apply(
        lambda s: s.str.replace(r"\s+", " ", regex=True).str.strip())
    if noise_hits:
        report["checks"].append(f"已去除模板词组（图为/编辑标注/导流语等）×{noise_hits} 处")
    else:
        report["checks"].append("未检出模板词组（图为/编辑标注等）")

    # 敏感信息脱敏：title/content/author 中检出个人信息即替换为占位符，数量如实入报告
    mask_stats = {}
    for col in SENSITIVE_COLUMNS:
        masked = out[col].map(mask_sensitive)
        out[col] = masked.map(lambda x: x[0])
        for _, hits in masked:
            for k, n in hits.items():
                mask_stats[k] = mask_stats.get(k, 0) + n
    if mask_stats:
        report["checks"].append(
            "已脱敏敏感信息（替换为占位符）: " + "、".join(f"{k}×{v}处" for k, v in mask_stats.items()))
    else:
        report["checks"].append("未检出邮箱/身份证号/手机号等敏感信息")

    # 日期：解析失败/缺失 -> 空字符串（EchoMap 会记为 NaT 但保留该行；不填充伪造日期）
    parsed_dates = pd.to_datetime(df["publish_time"], errors="coerce")
    out["published_at"] = parsed_dates.dt.strftime("%Y-%m-%d %H:%M:%S").fillna("")
    nat_count = int(parsed_dates.isna().sum())
    if nat_count:
        report["warnings"].append(
            f"{nat_count} 条记录发布时间缺失或不可解析，published_at 留空（EchoMap 将记为 NaT，不会删行）")

    # 导出前检查 1：必需列空值（EchoMap 清洗会删除这些行，先如实披露数量）
    empty_required = {c: int((out[c] == "").sum()) for c in REQUIRED}
    report["empty_required"] = empty_required
    if any(empty_required.values()):
        report["warnings"].append(
            f"必需列存在空值 {empty_required}，对应行将被 EchoMap 清洗删除")

    # 导出前检查 2：id 重复（保留首条并披露；数据库本身按 news_id 去重，正常应为 0）
    dup_count = int(out["id"].duplicated().sum())
    if dup_count:
        out = out.drop_duplicates(subset="id", keep="first")
        report["warnings"].append(f"发现 {dup_count} 条重复 id，已保留首条")
    report["duplicates_dropped"] = dup_count

    # 附加真实热点分析结果（可选）
    if hotspot_results is not None:
        labels = hotspot_results.get("cluster_labels")
        if labels is not None and len(labels) == len(df):
            scores = {cid: round(info["score"], 4)
                      for cid, info in hotspot_results.get("hotspot_rankings", [])}
            topics = hotspot_results.get("cluster_topics", {})
            out["hotspot_cluster"] = list(labels)
            out["hotspot_score"] = [scores.get(c, "") for c in labels]
            out["topic_keywords"] = [
                "/".join(w for w, _ in topics.get(c, {}).get("topic_words", [])[:3])
                for c in labels]
            report["checks"].append("已附加真实热点分析列（cluster/score/keywords，来自本次挖掘结果）")
        else:
            report["warnings"].append("热点结果与数据行数不一致，未附加分析列")

    out = out.reset_index(drop=True)
    report["rows_out"] = int(len(out))

    csv_path = os.path.join(
        output_dir, f"echomap_news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    out.to_csv(csv_path, index=False, encoding="utf-8-sig")
    report["path"] = csv_path
    report["encoding"] = "utf-8-sig"
    report["columns"] = list(out.columns)
    if days_note:
        report["window"] = days_note

    # 导出后验证：回读文件，确认编码可读、日期可解析、无乱码替换符
    back = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    assert list(back.columns) == list(out.columns), "回读列名不一致"
    assert len(back) == len(out), "回读行数不一致"
    reparsed = pd.to_datetime(back["published_at"], format="mixed", errors="coerce")
    bad_dates = int(((back["published_at"] != "") & reparsed.isna()).sum())
    mojibake = int(back["title"].str.contains("�", regex=False).sum())
    report["checks"] += [
        f"回读校验通过：{len(back)} 行，列名一致",
        f"非空 published_at 全部可解析（解析失败 {bad_dates} 条）",
        f"标题乱码替换符(�)检出 {mojibake} 条",
    ]
    if bad_dates or mojibake:
        report["warnings"].append("回读发现日期解析失败或乱码，请人工抽查")

    logger.info("EchoMap 兼容 CSV 已导出: %s（%s 行）", csv_path, len(out))
    for line in report["checks"] + report["warnings"]:
        logger.info("[导出报告] %s", line)
    return csv_path, report


if __name__ == "__main__":
    # 独立使用：从数据库读取清洗数据（近30天窗口）并导出核心字段（不含热点列）
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    from preprocessing.text_processor import DataCleaner, apply_analysis_window

    data = DataCleaner("mysql").clean_database_data()
    if data.empty:
        raise SystemExit("数据库无数据可导出")
    data, win = apply_analysis_window(data, days=30)
    path, rep = export_echomap_csv(data, days_note="近30天")
    print(f"\n导出完成: {path}")
    print(f"行数: {rep['rows_out']}，列: {rep['columns']}，编码: {rep['encoding']}")
    for w in rep["warnings"]:
        print(f"注意: {w}")
