# -*- coding: utf-8 -*-
"""
新闻热点挖掘系统主程序
"""

import sys
import argparse
import logging
from datetime import datetime
import os

# 添加项目路径到系统路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from crawler.news_crawler import NewsScheduler
from preprocessing.text_processor import DataCleaner, create_stopwords_file
from mining.hotspot_miner import HotspotMiner
from analysis.propagation_analyzer import PropagationAnalyzer
from visualization.visualizer import NewsVisualizer
from database.db_manager import get_db_manager

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('news_hotspot_mining.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class NewsHotspotMiningSystem:
    """新闻热点挖掘系统主类"""
    
    def __init__(self, db_type='mysql'):
        self.db_type = db_type
        self.scheduler = NewsScheduler(db_type)
        self.cleaner = DataCleaner(db_type)
        self.miner = HotspotMiner()
        self.analyzer = PropagationAnalyzer()
        self.visualizer = NewsVisualizer()
        
        logger.info("新闻热点挖掘系统初始化完成")
    
    def setup_environment(self):
        """设置环境"""
        logger.info("设置系统环境")
        
        # 创建必要的目录
        directories = ['data', 'data/visualizations', 'data/reports']
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
        
        # 创建停用词文件
        create_stopwords_file()
        
        logger.info("环境设置完成")
    
    def crawl_news(self, max_news_per_source=50):
        """爬取新闻数据"""
        logger.info(f"开始爬取新闻数据，每个源最多{max_news_per_source}条")
        
        try:
            from crawler.api_crawler import APIScheduler
            
            # 首先尝试网页爬虫
            web_count = self.scheduler.crawl_all_sources(max_news_per_source)
            logger.info(f"网页爬虫完成，获取 {web_count} 条新闻")
            
            # 使用API爬虫作为补充（减少数量避免重复）
            api_scheduler = APIScheduler(db_type=self.db_type)
            api_count = api_scheduler.crawl_all_apis(max_news_per_api=max(10, max_news_per_source//3))
            logger.info(f"API爬虫完成，获取 {api_count} 条新闻")
            
            total_crawled = web_count + api_count
            logger.info(f"新闻爬取完成，总计获取 {total_crawled} 条新闻")
            
            return total_crawled > 0
            
        except Exception as e:
            logger.error(f"新闻爬取失败: {e}")
            return False
    
    def preprocess_data(self, days=30):
        """数据预处理"""
        logger.info("开始数据预处理")

        try:
            cleaned_data = self.cleaner.clean_database_data()

            if not cleaned_data.empty:
                # 分析时间窗口过滤（默认近30天；发布时间缺失的记录按采集时间判断归属并披露）
                from preprocessing.text_processor import apply_analysis_window
                cleaned_data, win_stats = apply_analysis_window(cleaned_data, days=days)
                self.window_stats = win_stats

            if not cleaned_data.empty:
                # 导出清洗后的数据
                output_path = f'data/cleaned_news_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
                self.cleaner.export_cleaned_data(cleaned_data, output_path)
                
                logger.info(f"数据预处理完成，清洗后数据量: {len(cleaned_data)}")
                return cleaned_data
            else:
                logger.warning("没有数据需要处理")
                return None
                
        except Exception as e:
            logger.error(f"数据预处理失败: {e}")
            return None
    
    def mine_hotspots(self, df, clustering_method='kmeans'):
        """挖掘热点话题"""
        logger.info(f"开始热点话题挖掘，使用{clustering_method}方法")
        
        try:
            results = self.miner.mine_hotspots(df, clustering_method=clustering_method)
            
            # 生成热点报告
            report = self.miner.generate_hotspot_report(results)
            
            # 保存报告
            report_path = f'data/reports/hotspot_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
            import json
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2, default=str)
            
            logger.info(f"热点挖掘完成，发现{len(results['cluster_topics'])}个热点话题")
            logger.info(f"热点报告已保存到: {report_path}")
            
            return results
            
        except Exception as e:
            logger.error(f"热点挖掘失败: {e}")
            return None
    
    def analyze_propagation(self, df):
        """分析传播模式"""
        logger.info("开始传播分析")
        
        try:
            report = self.analyzer.generate_propagation_report(df)
            
            # 附加真实传播图对象供可视化使用（不写入 JSON 报告，避免污染报告内容）
            graph_obj = getattr(self.analyzer, 'propagation_graph', None)
            if graph_obj is not None:
                report['propagation_graph'] = graph_obj
            
            # 保存传播分析报告（过滤掉不可序列化的图对象）
            report_path = f'data/reports/propagation_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
            import json
            serializable_report = {k: v for k, v in report.items() if k != 'propagation_graph'}
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(serializable_report, f, ensure_ascii=False, indent=2, default=str)
            
            logger.info("传播分析完成")
            logger.info(f"传播分析报告已保存到: {report_path}")
            
            return report
            
        except Exception as e:
            logger.error(f"传播分析失败: {e}")
            return None
    
    def create_visualizations(self, hotspot_results, df, propagation_results=None):
        """创建可视化"""
        logger.info("开始创建可视化图表")
        
        try:
            dashboard_path = self.visualizer.create_comprehensive_dashboard(
                hotspot_results, df, propagation_results
            )
            
            logger.info(f"可视化仪表板已生成: {dashboard_path}")
            
            return dashboard_path
            
        except Exception as e:
            logger.error(f"可视化创建失败: {e}")
            return None
    
    def run_full_pipeline(self, crawl_news=True, max_news_per_source=50, clustering_method='kmeans', days=30, export_echomap=False):
        """运行完整流水线"""
        logger.info("="*50)
        logger.info("开始运行新闻热点挖掘完整流水线")
        logger.info("="*50)
        
        # 1. 设置环境
        self.setup_environment()
        
        # 2. 爬取新闻（可选）
        if crawl_news:
            success = self.crawl_news(max_news_per_source)
            if not success:
                logger.error("新闻爬取失败，终止流水线")
                return False
        
        # 3. 数据预处理
        cleaned_data = self.preprocess_data(days=days)
        if cleaned_data is None or cleaned_data.empty:
            logger.error("数据预处理失败，终止流水线")
            return False
        
        # 4. 热点挖掘
        hotspot_results = self.mine_hotspots(cleaned_data, clustering_method)
        if hotspot_results is None:
            logger.error("热点挖掘失败，终止流水线")
            return False
        
        # 5. 传播分析
        propagation_results = self.analyze_propagation(cleaned_data)
        
        # 6. 创建可视化
        dashboard_path = self.create_visualizations(hotspot_results, cleaned_data, propagation_results)

        # 6.5 可选：导出 EchoMap 兼容 CSV（仅显式开启时执行，不改变原有结果与流程）
        if export_echomap:
            try:
                from echomap_export import export_echomap_csv
                export_echomap_csv(cleaned_data, hotspot_results, days_note=f"近{days}天")
            except Exception as e:
                logger.error(f"EchoMap CSV 导出失败（不影响主流程）: {e}")
        
        # 7. 输出结果摘要
        self.print_results_summary(hotspot_results, propagation_results, dashboard_path)
        
        logger.info("="*50)
        logger.info("新闻热点挖掘流水线运行完成")
        logger.info("="*50)
        
        return True
    
    def print_results_summary(self, hotspot_results, propagation_results, dashboard_path):
        """打印结果摘要"""
        print("\n" + "="*60)
        print("新闻热点挖掘结果摘要")
        print("="*60)
        
        # 热点挖掘结果
        if hotspot_results:
            report = self.miner.generate_hotspot_report(hotspot_results)
            print(f"\n热点话题统计:")
            print(f"  - 总新闻数量: {report['summary']['total_news']}")
            print(f"  - 发现话题数: {report['summary']['total_clusters']}")
            print(f"  - 分析时间: {report['summary']['analysis_time']}")
            
            print(f"\n前5个热点话题:")
            for i, hotspot in enumerate(report['top_hotspots'][:5]):
                print(f"  {i+1}. {', '.join(hotspot['topic_words'])}")
                print(f"     新闻数量: {hotspot['news_count']}, 互动总数: {hotspot['total_engagement']}")
        
        # 传播分析结果
        if propagation_results:
            print(f"\n传播分析统计:")
            print(f"  - 新闻源数量: {propagation_results['summary']['unique_sources']}")
            print(f"  - 传播网络节点: {propagation_results['network_analysis']['nodes_count']}")
            print(f"  - 传播网络边数: {propagation_results['network_analysis']['edges_count']}")
            print(f"  - 综合影响力分数: {propagation_results['influence_metrics'].get('overall_influence', 'N/A'):.2f}")
        
        # 可视化结果
        if dashboard_path:
            print(f"\n可视化仪表板: {dashboard_path}")
            print("请在浏览器中打开上述路径查看详细的可视化分析结果")
        
        print("="*60)
    
    def run_scheduled_crawling(self):
        """运行定时爬取任务"""
        logger.info("启动定时爬取任务")
        self.scheduler.run_scheduled_crawl()

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='新闻热点挖掘系统')
    parser.add_argument('--mode', choices=['full', 'crawl', 'analyze', 'scheduled'], 
                       default='full', help='运行模式')
    parser.add_argument('--no-crawl', action='store_true', help='跳过新闻爬取')
    parser.add_argument('--max-news', type=int, default=50, help='每个源最大新闻数量')
    parser.add_argument('--clustering', choices=['kmeans', 'dbscan'], 
                       default='kmeans', help='聚类方法')
    parser.add_argument('--days', type=int, default=30,
                       help='分析时间窗口（天），默认仅分析近30天数据；<=0 表示不过滤')
    parser.add_argument('--export-echomap', action='store_true',
                       help='额外导出 EchoMap 兼容 CSV 到 data/exports/（不改变原有流程与结果）')
    parser.add_argument('--db-type', choices=['mysql', 'mongodb', 'sqlite'],
                       default='mysql', help='数据库类型')
    
    args = parser.parse_args()
    
    # 创建系统实例
    system = NewsHotspotMiningSystem(args.db_type)
    
    try:
        if args.mode == 'full':
            # 运行完整流水线
            system.run_full_pipeline(
                crawl_news=not args.no_crawl,
                max_news_per_source=args.max_news,
                clustering_method=args.clustering,
                days=args.days,
                export_echomap=args.export_echomap
            )

        elif args.mode == 'crawl':
            # 仅爬取新闻
            system.setup_environment()
            system.crawl_news(args.max_news)

        elif args.mode == 'analyze':
            # 仅分析已有数据
            system.setup_environment()
            cleaned_data = system.preprocess_data(days=args.days)
            if cleaned_data is not None and not cleaned_data.empty:
                hotspot_results = system.mine_hotspots(cleaned_data, args.clustering)
                propagation_results = system.analyze_propagation(cleaned_data)
                dashboard_path = system.create_visualizations(hotspot_results, cleaned_data, propagation_results)
                if args.export_echomap:
                    # 可选：导出 EchoMap 兼容 CSV（不改变原有分析结果）
                    from echomap_export import export_echomap_csv
                    export_echomap_csv(cleaned_data, hotspot_results, days_note=f"近{args.days}天")
                system.print_results_summary(hotspot_results, propagation_results, dashboard_path)
        
        elif args.mode == 'scheduled':
            # 运行定时任务
            system.run_scheduled_crawling()
    
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序运行出错: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 