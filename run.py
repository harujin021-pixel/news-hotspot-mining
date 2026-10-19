# -*- coding: utf-8 -*-
"""
新闻热点挖掘系统快速启动脚本
"""

import os
import sys
import subprocess

def install_requirements():
    """安装依赖包"""
    print("正在安装依赖包...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("依赖包安装完成！")
        return True
    except subprocess.CalledProcessError:
        print("依赖包安装失败，请手动安装！")
        return False

def create_sample_data():
    """创建示例数据（当数据库不可用时）。

    警告：本函数生成的是虚构演示数据（含编造的互动量与发布时间），仅写入
    data/sample_news.csv，不进入数据库。任何正式分析或演示中使用
    该数据都必须明确标注为"示例数据"，不得冒充真实采集结果。
    """
    print("警告：正在创建虚构示例数据，不得作为真实新闻数据展示")
    import pandas as pd
    from datetime import datetime, timedelta
    import json
    
    print("创建示例数据...")
    
    # 创建示例新闻数据
    sample_news = []
    topics = [
        ["经济", "发展", "GDP", "增长", "投资"],
        ["科技", "人工智能", "创新", "研发", "技术"],
        ["环保", "绿色", "节能", "环境", "生态"],
        ["教育", "学校", "学生", "改革", "素质"],
        ["医疗", "健康", "病毒", "疫苗", "治疗"]
    ]
    
    sources = ["新华网", "人民网", "央视网"]
    
    for i in range(100):
        topic = topics[i % len(topics)]
        source = sources[i % len(sources)]
        
        title = f"{topic[0]}{topic[1]}取得重大突破，{topic[2]}水平显著提升"
        content = f"据{source}报道，{topic[0]}领域在{topic[1]}方面取得重大进展。" + \
                 f"专家表示，{topic[2]}和{topic[3]}的结合将推动{topic[4]}事业的发展。" + \
                 "这一成果将对未来产生深远影响，值得持续关注。"
        
        news_item = {
            'id': i + 1,
            'title': title,
            'content': content,
            'title_clean': title,
            'content_clean': content,
            'source': source,
            'author': f"记者{i % 10 + 1}",
            'publish_time': datetime.now() - timedelta(days=i//10, hours=i%24),
            'comments_count': (i * 7) % 100,
            'likes_count': (i * 11) % 200,
            'shares_count': (i * 3) % 50,
            'crawl_time': datetime.now(),
            'category': topic[0],
            'tags': ','.join(topic[:3])
        }
        sample_news.append(news_item)
    
    # 保存为CSV文件
    os.makedirs('data', exist_ok=True)
    df = pd.DataFrame(sample_news)
    df.to_csv('data/sample_news.csv', index=False, encoding='utf-8')
    
    print(f"示例数据已保存到 data/sample_news.csv，共{len(sample_news)}条记录")
    return df

def run_real_data_analysis():
    """使用真实数据运行完整分析"""
    print("开始使用真实数据进行分析...")
    
    try:
        from crawler.news_crawler import NewsScheduler
        from crawler.api_crawler import APIScheduler
        from preprocessing.text_processor import DataCleaner, create_stopwords_file
        from mining.hotspot_miner import HotspotMiner
        from analysis.propagation_analyzer import PropagationAnalyzer
        from visualization.visualizer import NewsVisualizer
        
        # 创建停用词文件
        create_stopwords_file()
        
        # 1. 真实数据爬取
        print("=" * 50)
        print("第1步：爬取真实新闻数据")
        print("=" * 50)
        
        # 网页爬虫
        print("启动网页爬虫...")
        web_scheduler = NewsScheduler()
        web_count = web_scheduler.crawl_all_sources(max_news_per_source=30)
        print(f"✓ 网页爬虫完成，获取 {web_count} 条新闻")
        
        # API爬虫作为补充
        print("启动API爬虫...")
        api_scheduler = APIScheduler()
        api_count = api_scheduler.crawl_all_apis(max_news_per_api=20)
        print(f"✓ API爬虫完成，获取 {api_count} 条新闻")
        
        total_crawled = web_count + api_count
        print(f"✓ 数据爬取完成，总计获取 {total_crawled} 条真实新闻")
        
        if total_crawled == 0:
            print("✗ 未获取到真实数据，请检查网络连接")
            return False
        
        # 2. 数据预处理
        print("\n" + "=" * 50)
        print("第2步：数据预处理")
        print("=" * 50)
        
        cleaner = DataCleaner()
        df = cleaner.clean_database_data()
        
        if df.empty:
            print("✗ 数据预处理失败，没有可用数据")
            return False
        
        print(f"✓ 数据预处理完成，处理了 {len(df)} 条新闻")
        
        # 3. 热点挖掘
        print("\n" + "=" * 50)
        print("第3步：热点话题挖掘")
        print("=" * 50)
        
        miner = HotspotMiner()
        hotspot_results = miner.mine_hotspots(df, clustering_method='kmeans', topic_modeling=True)
        
        if not hotspot_results:
            print("✗ 热点挖掘失败")
            return False
        
        print("✓ 热点挖掘完成")
        
        # 4. 传播分析
        print("\n" + "=" * 50)
        print("第4步：传播模式分析")
        print("=" * 50)
        
        analyzer = PropagationAnalyzer()
        propagation_results = analyzer.generate_propagation_report(df)
        
        if propagation_results:
            print("✓ 传播分析完成")
        else:
            print("! 传播分析部分失败，但继续执行")
        
        # 5. 生成报告和可视化
        print("\n" + "=" * 50)
        print("第5步：生成报告和可视化")
        print("=" * 50)
        
        # 生成热点报告
        report = miner.generate_hotspot_report(hotspot_results)
        
        # 可视化
        visualizer = NewsVisualizer()
        dashboard_path = visualizer.create_comprehensive_dashboard(
            hotspot_results, df, propagation_results
        )
        
        # 6. 输出结果摘要
        print("\n" + "=" * 60)
        print("真实数据分析结果摘要")
        print("=" * 60)
        print(f"数据来源: 真实爬取的中国新闻网站")
        print(f"总新闻数: {report['summary']['total_news']}")
        print(f"发现话题数: {report['summary']['total_clusters']}")
        print(f"分析时间: {report['summary']['analysis_time']}")
        
        print(f"\n前10个热点话题:")
        for i, hotspot in enumerate(report['top_hotspots'][:10]):
            topic_words = ', '.join(hotspot['topic_words'])
            print(f"{i+1:2d}. {topic_words}")
            print(f"     新闻数量: {hotspot['news_count']}, 互动总数: {hotspot['total_engagement']}")
        
        if propagation_results:
            print(f"\n传播网络分析:")
            print(f"  - 新闻源数量: {propagation_results['summary']['unique_sources']}")
            print(f"  - 网络节点数: {propagation_results['network_analysis']['nodes_count']}")
            print(f"  - 网络边数: {propagation_results['network_analysis']['edges_count']}")
        
        print(f"\n可视化仪表板: {dashboard_path}")
        print("请在浏览器中打开上述文件查看详细的可视化分析结果")
        
        print("=" * 60)
        print("✓ 真实数据分析完成！")
        
        return True
        
    except Exception as e:
        print(f"✗ 分析过程出错: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    print("="*60)
    print("新闻热点挖掘系统 - 真实数据分析")
    print("="*60)
    
    # 检查是否需要安装依赖
    try:
        import pandas, jieba, sklearn, gensim, pyecharts, requests, feedparser
        from bs4 import BeautifulSoup
        print("✓ 依赖包检查通过")
    except ImportError:
        print("! 检测到缺少依赖包")
        if input("是否自动安装依赖包？(y/n): ").lower() == 'y':
            if not install_requirements():
                return
        else:
            print("请手动安装依赖包: pip install -r requirements.txt")
            return
    
    print("\n选择运行模式:")
    print("1. 真实数据完整分析（推荐）")
    print("2. 快速测试爬虫功能")
    print("3. 调用主程序完整流水线")
    
    choice = input("请选择 (1/2/3): ").strip()
    
    if choice == "1":
        print("\n开始真实数据完整分析...")
        print("将从中国新闻网站爬取最新数据进行分析")
        print("请确保网络连接正常和数据库配置正确")
        
        success = run_real_data_analysis()
        
        if success:
            print("\n✓ 真实数据分析完成！")
            print("已生成详细的热点分析报告和可视化结果")
        else:
            print("\n✗ 分析失败，请检查错误信息")
    
    elif choice == "2":
        print("\n开始快速测试...")
        
        try:
            from crawler.news_crawler import NewsScheduler
            from crawler.api_crawler import APIScheduler
            
            print("测试网页爬虫...")
            web_scheduler = NewsScheduler()
            web_count = web_scheduler.crawl_all_sources(max_news_per_source=5)
            print(f"✓ 网页爬虫测试完成，获取 {web_count} 条新闻")
            
            print("测试API爬虫...")
            api_scheduler = APIScheduler()
            api_count = api_scheduler.crawl_all_apis(max_news_per_api=5)
            print(f"✓ API爬虫测试完成，获取 {api_count} 条新闻")
            
            print(f"✓ 爬虫测试完成，总计获取 {web_count + api_count} 条真实新闻")
            
        except Exception as e:
            print(f"✗ 爬虫测试失败: {e}")
    
    elif choice == "3":
        print("\n启动主程序完整流水线...")
        print("请确保已配置好数据库连接")
        
        try:
            from main import main as main_func
            import sys
            
            # 设置参数使用真实数据
            sys.argv = ['main.py', '--mode', 'full', '--max-news', '50']
            main_func()
            
        except Exception as e:
            print(f"运行出错: {e}")
            print("请检查数据库配置和网络连接")
    
    else:
        print("无效选择")

if __name__ == "__main__":
    main() 