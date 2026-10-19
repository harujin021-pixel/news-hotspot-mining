# -*- coding: utf-8 -*-
"""生成互动数据质量清单 data/reports/engagement_provenance.json。

只读数据库，逐条登记每条 news_id 三个互动字段的真实性状态；不修改任何历史记录。
仅当字段被显式标记 verified_real 时才允许进入互动统计；其余一律 unknown（fail-closed）。
"""
import sys, os, json
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_manager import get_db_manager

# 代码路径已确认三列互动均为 random.randint 生成的来源
RANDOM_ALL = {
    '新华网':   'crawler/news_crawler.py 原 L328-330',
    '人民网':   'crawler/news_crawler.py 原 L795-797',
    '新浪新闻': 'crawler/news_crawler.py 原 L512-514',
    '网易新闻': 'crawler/news_crawler.py 原 L652-654',
    '中国新闻网': 'crawler/api_crawler.py 原 L487-489/L544-546',
}
ENG_COLS = ['comments_count', 'likes_count', 'shares_count']

def main():
    mgr = get_db_manager('mysql')
    df = mgr.get_all_news_df()
    mgr.close()
    cutoff = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    records = []
    for _, r in df.iterrows():
        src = r['source']
        if src in RANDOM_ALL:
            fields = {c: {'status': 'unknown',
                          'reason': '采集代码 random.randint 生成（代码路径确认，非逐条数值验证）',
                          'evidence': RANDOM_ALL[src],
                          'verification_status': 'code_path_inferred'} for c in ENG_COLS}
        elif src == '网易新闻API':
            fields = {
                'comments_count': {'status': 'unknown',
                                   'reason': '可能取自响应 replyCount 或随机兜底，无原始响应无法区分',
                                   'evidence': 'crawler/api_crawler.py 原 L683',
                                   'verification_status': 'pending_field_verification'},
                'likes_count': {'status': 'unknown', 'reason': '采集代码 random.randint 生成',
                                'evidence': 'crawler/api_crawler.py 原 L684',
                                'verification_status': 'code_path_inferred'},
                'shares_count': {'status': 'unknown', 'reason': '采集代码 random.randint 生成',
                                 'evidence': 'crawler/api_crawler.py 原 L685',
                                 'verification_status': 'code_path_inferred'},
            }
        else:
            fields = {c: {'status': 'unknown', 'reason': '未识别来源，保守按未知处理',
                          'evidence': '', 'verification_status': 'unrecognized_source'} for c in ENG_COLS}
        records.append({'news_id': str(r['news_id']), 'source': src,
                        'crawl_time': str(r['crawl_time']), 'fields': fields})
    manifest = {
        'cutoff_time': cutoff,
        'generated_at': cutoff,
        'rule': 'crawl_time <= cutoff_time 的记录，字段未标记 verified_real 即视为未知，分析时置缺失',
        'note': '本清单只读生成，不修改任何历史记录；历史互动数值无原始响应可溯，不可逐条证实',
        'records': records,
    }
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'data', 'reports', 'engagement_provenance.json')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(f'已生成 {out}，共 {len(records)} 条记录')

if __name__ == '__main__':
    main()
