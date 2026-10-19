# -*- coding: utf-8 -*-
"""
MySQL 回滚式 NULL 写入验证（T2 验收，一次性脚本）

验证目标（阶段 A-2 v5 核心判据）：
  移除 ORM python 端 default=0 后，经 ORM 插入时——
    S1 显式赋 None   → 数据库落 SQL NULL（核心判据）
    S2 字段完全省略   → 记录该行为（防御性兼容：可能落 NULL 或走 server DEFAULT）
    S3 显式赋 0      → 落真实 0
    S4 显式赋正整数   → 落该值

全程在事务内执行，SELECT 验证后立即 ROLLBACK，不持久化任何写入。
"""
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import text
from database.db_manager import Base, NewsArticle, get_db_manager


def main():
    mgr = get_db_manager('mysql')
    tag = 'T2VERIFY_ROLLBACK'
    try:
        # 表结构事实：三列是否 nullable / 有无 server 端 DEFAULT（独立连接查 DDL，无事务问题）
        with mgr.engine.connect() as ddl_conn:
            cols = ddl_conn.execute(text(
                "SELECT COLUMN_NAME, IS_NULLABLE, COLUMN_DEFAULT "
                "FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA='news_hotspot' AND TABLE_NAME='news_articles' "
                "AND COLUMN_NAME IN ('comments_count','likes_count','shares_count')"
            )).fetchall()
        print('表结构事实:')
        for name, nullable, default in cols:
            print(f'  {name}: nullable={nullable}, server_default={default!r}')

        # 插入与验证必须走同一 session（同一事务/连接），否则读不到未提交数据
        sess = mgr.session

        # S1/S3/S4：显式赋值三种场景（ORM insert）
        rows = [
            NewsArticle(news_id=f'{tag}_S1', title='t', content='c', source='verify',
                        comments_count=None, likes_count=None, shares_count=None),
            NewsArticle(news_id=f'{tag}_S3', title='t', content='c', source='verify',
                        comments_count=0, likes_count=0, shares_count=0),
            NewsArticle(news_id=f'{tag}_S4', title='t', content='c', source='verify',
                        comments_count=7, likes_count=8, shares_count=9),
        ]
        # S2：字段完全省略（构造时不提及三列）
        rows.append(NewsArticle(news_id=f'{tag}_S2', title='t', content='c', source='verify'))

        sess.add_all(rows)
        sess.flush()  # 写入当前事务但不提交

        got = sess.execute(text(
            "SELECT news_id, comments_count, likes_count, shares_count "
            "FROM news_articles WHERE news_id LIKE :pat"
        ), {'pat': f'{tag}_%'}).fetchall()
        result = {r[0]: r[1:] for r in got}

        print('\n四种场景落库结果:')
        for sid in ['S1', 'S2', 'S3', 'S4']:
            print(f'  {sid}: {result.get(f"{tag}_{sid}")}')

        s1 = result.get(f'{tag}_S1')
        s2 = result.get(f'{tag}_S2')
        s3 = result.get(f'{tag}_S3')
        s4 = result.get(f'{tag}_S4')

        ok = True
        # 核心判据：显式 None → SQL NULL
        if s1 == (None, None, None):
            print('\n[核心判据] S1 显式 None → SQL NULL：通过')
        else:
            ok = False
            print(f'\n[核心判据] S1 显式 None → 期望 (None,None,None)，实际 {s1}：不通过')
        # S3/S4 防回归
        if s3 == (0, 0, 0) and s4 == (7, 8, 9):
            print('[防回归] S3 显式 0 → 0；S4 正整数原样：通过')
        else:
            ok = False
            print(f'[防回归] S3={s3} S4={s4}：不通过')
        # S2 记录行为（不计入通过/不通过）
        print(f'[记录] S2 省略字段落库值 = {s2}（防御性兼容说明用，非验收判据）')

        print('\n总体:', '通过' if ok else '不通过')
        return 0 if ok else 1
    finally:
        mgr.session.rollback()
        print('已回滚，数据库无持久化变更。')


if __name__ == '__main__':
    sys.exit(main())
