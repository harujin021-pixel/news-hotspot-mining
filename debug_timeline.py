# -*- coding: utf-8 -*-
"""
调试话题演化时间线
"""

import sys
import os
import pandas as pd
import logging

# 添加项目路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.db_manager import get_db_manager
from preprocessing.text_processor import DataCleaner
from mining.hotspot_miner import HotspotMiner
from visualization.visualizer import NewsVisualizer

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def debug_timeline():
    """调试话题演化时间线"""
    try:
        # 1. 获取数据
        logger.info("获取数据...")
        cleaner = DataCleaner()
        df = cleaner.clean_database_data()
        
        if df.empty:
            logger.error("没有数据")
            return
        
        logger.info(f"数据量: {len(df)}")
        logger.info(f"数据列: {df.columns.tolist()}")
        
        # 2. 热点挖掘
        logger.info("执行热点挖掘...")
        miner = HotspotMiner()
        hotspot_results = miner.mine_hotspots(df)
        
        logger.info(f"聚类标签数量: {len(hotspot_results['cluster_labels'])}")
        logger.info(f"聚类主题数量: {len(hotspot_results['cluster_topics'])}")
        
        # 3. 检查数据结构
        logger.info("检查数据结构...")
        df_with_cluster = df.copy()
        df_with_cluster['cluster'] = hotspot_results['cluster_labels']
        df_with_cluster['date'] = pd.to_datetime(df_with_cluster['publish_time']).dt.date
        
        logger.info(f"聚类标签范围: {df_with_cluster['cluster'].min()} - {df_with_cluster['cluster'].max()}")
        logger.info(f"日期范围: {df_with_cluster['date'].min()} - {df_with_cluster['date'].max()}")
        
        # 4. 测试分组
        logger.info("测试分组...")
        timeline_data = df_with_cluster.groupby(['cluster', 'date']).size().unstack(fill_value=0)
        
        logger.info(f"时间线数据形状: {timeline_data.shape}")
        logger.info(f"时间线数据列: {timeline_data.columns.tolist()}")
        logger.info(f"时间线数据索引: {timeline_data.index.tolist()}")
        
        # 5. 测试话题名称提取
        logger.info("测试话题名称提取...")
        for cluster_id in timeline_data.index:
            if cluster_id == -1:
                continue
                
            cluster_topic = hotspot_results.get('cluster_topics', {}).get(cluster_id, {})
            topic_words = cluster_topic.get('topic_words', [])
            
            logger.info(f"聚类 {cluster_id}: {topic_words[:3] if topic_words else '无主题词'}")
        
        # 6. 创建可视化
        logger.info("创建可视化...")
        visualizer = NewsVisualizer()
        
        # 单独测试话题演化时间线
        timeline = visualizer.create_topic_evolution_timeline(hotspot_results, df)
        
        logger.info("调试完成")
        
    except Exception as e:
        logger.error(f"调试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_timeline() 