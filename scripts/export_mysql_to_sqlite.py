# -*- coding: utf-8 -*-
"""一次性迁移脚本：把 MySQL news_articles 全量复制到 data/news.db（SQLite）。

用途：云端部署环境无 MySQL，SQLite 数据库文件随仓库分发。
互动字段的缺失值（NaN/NaT）由 pandas.to_sql 自动转为 NULL，不做任何填充。
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import get_db_manager


def main():
    mysql_mgr = get_db_manager('mysql')
    df = mysql_mgr.get_all_news_df()
    mysql_mgr.close()
    print(f"MySQL 读取 {len(df)} 条，列: {list(df.columns)}")

    sqlite_mgr = get_db_manager('sqlite')
    # if_exists='replace'：重复执行时整表重建，保证与 MySQL 当前内容一致
    df.to_sql('news_articles', sqlite_mgr.engine, if_exists='replace', index=False)

    import pandas as pd
    back = pd.read_sql("SELECT COUNT(*) AS n FROM news_articles", sqlite_mgr.engine)
    eng = pd.read_sql(
        "SELECT "
        "SUM(comments_count IS NULL) AS c_null, "
        "SUM(likes_count IS NULL) AS l_null, "
        "SUM(shares_count IS NULL) AS s_null, "
        "SUM(publish_time IS NULL) AS p_null "
        "FROM news_articles", sqlite_mgr.engine)
    sqlite_mgr.close()

    print(f"SQLite 写入 {int(back['n'][0])} 条 -> data/news.db")
    print(f"NULL 统计: comments={int(eng['c_null'][0])}, likes={int(eng['l_null'][0])}, "
          f"shares={int(eng['s_null'][0])}, publish_time={int(eng['p_null'][0])}")


if __name__ == '__main__':
    main()
