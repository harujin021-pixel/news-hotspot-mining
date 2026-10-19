# -*- coding: utf-8 -*-
"""
互动量数据完整性测试（内存级，不依赖 MySQL）

覆盖设计（对应阶段 A-2 v5 测试矩阵的内存可执行部分）：
  D1 清洗层不再用 0 填充互动缺失、不再用当前时间填充发布缺失
  D2 热点排序区分"真实 0"与"未知(NaN)"
  D3 传播互动统计不吞缺失：全缺失 → insufficient_data；部分已知 → 仅统计已知
  D4 数据质量清单 fail-closed：未 verified_real 一律置 NaN；清单损坏 → 历史全置 NaN
  D5 清单字段级粒度：同一条记录可按字段分别保留/隔离

运行（项目根目录）：
  python tests/test_engagement_integrity.py
也兼容 pytest（如已安装）：pytest tests/test_engagement_integrity.py
"""
import sys
import os
import json
import tempfile
import traceback

import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)  # 清单默认相对路径基于项目根目录

from preprocessing.text_processor import TextProcessor, apply_engagement_provenance
from mining.hotspot_miner import HotspotMiner
from analysis.propagation_analyzer import PropagationAnalyzer

ENG = ['comments_count', 'likes_count', 'shares_count']


def _base_df(rows):
    """构造最小可用 DataFrame"""
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- D1
def test_d1_cleaning_preserves_nan():
    tp = TextProcessor()
    df = _base_df([
        {'title': 'a', 'content': 'x', 'comments_count': np.nan, 'likes_count': np.nan,
         'shares_count': np.nan, 'publish_time': None, 'author': None,
         'category': None, 'tags': None},
        {'title': 'b', 'content': 'y', 'comments_count': 0, 'likes_count': 5,
         'shares_count': np.nan, 'publish_time': '2026-01-01 08:00', 'author': 'z',
         'category': 'c', 'tags': 't'},
    ])
    out = tp.handle_missing_values(df)
    # 互动缺失保持 NaN（不得填 0）
    assert pd.isna(out.loc[0, 'comments_count']), 'D1: 互动缺失被填充，应为 NaN'
    assert pd.isna(out.loc[0, 'likes_count'])
    assert pd.isna(out.loc[0, 'shares_count'])
    # 真实 0 保持不变
    assert out.loc[1, 'comments_count'] == 0
    # 发布缺失保持 NaT（不得填当前时间）
    assert pd.isna(out.loc[0, 'publish_time']), 'D1: 发布缺失被填充，应为 NaT'
    assert pd.notna(out.loc[1, 'publish_time'])
    # 非关键字段仍按原逻辑填充
    assert out.loc[0, 'author'] == '未知'


# ---------------------------------------------------------------- D2
def test_d2_rank_hotspots_zero_vs_unknown():
    miner = HotspotMiner()
    now = pd.Timestamp.now()
    df = _base_df([
        # 聚类 0：互动全部未知
        {'title': 'n1', 'publish_time': now, 'comments_count': np.nan,
         'likes_count': np.nan, 'shares_count': np.nan},
        {'title': 'n2', 'publish_time': now, 'comments_count': np.nan,
         'likes_count': np.nan, 'shares_count': np.nan},
        # 聚类 1：互动真实为 0
        {'title': 'n3', 'publish_time': now, 'comments_count': 0,
         'likes_count': 0, 'shares_count': 0},
        {'title': 'n4', 'publish_time': now, 'comments_count': 0,
         'likes_count': 0, 'shares_count': 0},
    ])
    labels = [0, 0, 1, 1]

    ranked = dict(miner.rank_hotspots(df.copy(), labels, method='engagement'))
    # 全未知聚类：status=unknown，total=None，engagement 法分数 NaN
    assert ranked[0]['engagement_status'] == 'unknown'
    assert ranked[0]['total_engagement'] is None
    assert pd.isna(ranked[0]['score']), 'D2: 全未知聚类 engagement 分数应为 NaN'
    # 真实 0 聚类：status=available，total=0（真实零值，可与未知区分）
    assert ranked[1]['engagement_status'] == 'available'
    assert ranked[1]['total_engagement'] == 0
    assert ranked[1]['score'] == 0

    ranked_c = dict(miner.rank_hotspots(df.copy(), labels, method='comprehensive'))
    # 综合分：未知聚类互动项不计入但不视为真实 0 的证据体现在 status/coverage
    assert ranked_c[0]['engagement_coverage'] == 0.0
    assert ranked_c[1]['engagement_coverage'] == 1.0


# ---------------------------------------------------------------- D3
def test_d3_propagation_engagement_not_swallowing_missing():
    pa = PropagationAnalyzer()
    # 全缺失 → insufficient_data
    df_all_nan = _base_df([
        {'title': 'a', 'comments_count': np.nan, 'likes_count': np.nan, 'shares_count': np.nan},
        {'title': 'b', 'comments_count': np.nan, 'likes_count': np.nan, 'shares_count': np.nan},
    ])
    res = pa._analyze_engagement_patterns(df_all_nan.copy())
    assert res.get('status') == 'insufficient_data', 'D3: 全缺失应返回 insufficient_data'
    assert res['known_records'] == 0 and res['coverage'] == 0.0

    # 部分已知 → 统计仅基于已知记录
    df_mixed = _base_df([
        {'title': 'a', 'comments_count': 10, 'likes_count': 20, 'shares_count': 30},
        {'title': 'b', 'comments_count': np.nan, 'likes_count': np.nan, 'shares_count': np.nan},
        {'title': 'c', 'comments_count': 0, 'likes_count': 0, 'shares_count': 0},
    ])
    res2 = pa._analyze_engagement_patterns(df_mixed.copy())
    stats = res2['engagement_statistics']
    assert stats['known_records'] == 2, 'D3: 已知记录数应为 2'
    assert abs(stats['coverage'] - 2 / 3) < 1e-9
    # mean 仅基于已知(60, 0)，不含缺失行
    assert abs(stats['mean_engagement'] - 30.0) < 1e-9


# ---------------------------------------------------------------- D4 / D5
def _write_manifest(tmpdir, records, cutoff='2026-10-17 00:00:00'):
    path = os.path.join(tmpdir, 'manifest.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'cutoff_time': cutoff, 'records': records}, f, ensure_ascii=False)
    return path


def _prov_df():
    return _base_df([
        {'news_id': 'n1', 'crawl_time': pd.Timestamp('2026-10-01'),
         'comments_count': 100.0, 'likes_count': 200.0, 'shares_count': 50.0},
        {'news_id': 'n2', 'crawl_time': pd.Timestamp('2026-10-01'),
         'comments_count': 5.0, 'likes_count': 6.0, 'shares_count': 7.0},
        {'news_id': 'n3', 'crawl_time': pd.Timestamp('2026-12-01'),  # 晚于 cutoff → 新数据
         'comments_count': 1.0, 'likes_count': 2.0, 'shares_count': 3.0},
    ])


def test_d4_manifest_fail_closed():
    with tempfile.TemporaryDirectory() as td:
        # n1 全部 verified_real；n2 未标记（未知）→ 全置 NaN
        manifest = _write_manifest(td, [
            {'news_id': 'n1', 'fields': {
                'comments_count': {'status': 'verified_real'},
                'likes_count': {'status': 'verified_real'},
                'shares_count': {'status': 'verified_real'}}},
            {'news_id': 'n2', 'fields': {
                'comments_count': {'status': 'random_generated'},
                'likes_count': {'status': 'random_generated'},
                'shares_count': {'status': 'random_generated'}}},
        ])
        out = apply_engagement_provenance(_prov_df(), manifest_path=manifest)
        r1 = out[out['news_id'] == 'n1'].iloc[0]
        assert r1['comments_count'] == 100.0 and r1['likes_count'] == 200.0, 'D4: verified_real 字段应保留'
        r2 = out[out['news_id'] == 'n2'].iloc[0]
        assert pd.isna(r2['comments_count']) and pd.isna(r2['likes_count']) and pd.isna(r2['shares_count']), \
            'D4: 未 verified_real 字段应置 NaN'
        r3 = out[out['news_id'] == 'n3'].iloc[0]
        assert r3['comments_count'] == 1.0, 'D4: cutoff 之后的新数据不应受影响'

        # 清单损坏 → fail-closed：有 crawl_time 的记录互动全置 NaN
        bad = os.path.join(td, 'bad.json')
        with open(bad, 'w', encoding='utf-8') as f:
            f.write('{not valid json')
        out2 = apply_engagement_provenance(_prov_df(), manifest_path=bad)
        assert out2[ENG].isna().all().all(), 'D4: 清单损坏时历史互动应全部置 NaN'


def test_d5_manifest_field_level():
    with tempfile.TemporaryDirectory() as td:
        manifest = _write_manifest(td, [
            {'news_id': 'n1', 'fields': {
                'comments_count': {'status': 'verified_real'},
                'likes_count': {'status': 'pending_field_verification'},
                'shares_count': {'status': 'code_path_inferred'}}},
        ])
        out = apply_engagement_provenance(_prov_df(), manifest_path=manifest)
        r1 = out[out['news_id'] == 'n1'].iloc[0]
        assert r1['comments_count'] == 100.0, 'D5: verified_real 字段应保留'
        assert pd.isna(r1['likes_count']), 'D5: pending 字段应置 NaN'
        assert pd.isna(r1['shares_count']), 'D5: inferred 字段应置 NaN'


# ---------------------------------------------------------------- 独立运行器
def main():
    tests = [
        ('D1 清洗层保留 NaN/NaT，不冒充真实值', test_d1_cleaning_preserves_nan),
        ('D2 排序区分真实 0 与未知(NaN)', test_d2_rank_hotspots_zero_vs_unknown),
        ('D3 传播互动统计不吞缺失', test_d3_propagation_engagement_not_swallowing_missing),
        ('D4 清单 fail-closed（含损坏清单）', test_d4_manifest_fail_closed),
        ('D5 清单字段级粒度', test_d5_manifest_field_level),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f'PASS  {name}')
        except Exception:
            failed += 1
            print(f'FAIL  {name}')
            traceback.print_exc()
    print('-' * 60)
    print(f'结果: {len(tests) - failed}/{len(tests)} 通过')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
