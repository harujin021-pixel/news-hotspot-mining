# -*- coding: utf-8 -*-
"""
配置文件。敏感凭据请通过环境变量或 config/local_settings.py（已 .gitignore）覆盖。
"""
import os

# 数据库配置：密码等敏感字段优先从环境变量读取，未设置时使用占位空值
DATABASE_CONFIG = {
    'mysql': {
        'host': os.environ.get('MYSQL_HOST', 'localhost'),
        'port': int(os.environ.get('MYSQL_PORT', '3306')),
        'user': os.environ.get('MYSQL_USER', 'root'),
        'password': os.environ.get('MYSQL_PASSWORD', ''),
        'database': os.environ.get('MYSQL_DB', 'news_hotspot'),
        'charset': 'utf8mb4'
    },
    'mongodb': {
        'host': os.environ.get('MONGO_HOST', 'localhost'),
        'port': int(os.environ.get('MONGO_PORT', '27017')),
        'database': os.environ.get('MONGO_DB', 'news_hotspot')
    }
}

# 允许本地覆盖（不入库）
try:
    from config.local_settings import *  # noqa: F401,F403
except ImportError:
    pass

# 爬虫配置
CRAWLER_CONFIG = {
    'user_agents': [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15'
    ],
    'delay': 1,  # 请求间隔（秒）
    'timeout': 30,  # 超时时间（秒）
    'retry_times': 3,  # 重试次数
    'crawl_frequency': 15  # 采集频率（分钟）
}

# 新闻源配置
NEWS_SOURCES = {
    'xinhua': {
        'name': '新华网',
        'base_url': 'http://www.news.cn',
        'news_list_url': 'http://www.news.cn/politics/index.htm',
        'rss_url': 'http://www.news.cn/politics/news_politics.xml',
        'type': 'news_website'
    },
    'people': {
        'name': '人民网',
        'base_url': 'http://www.people.com.cn',
        'news_list_url': 'http://politics.people.com.cn',
        'rss_url': 'http://www.people.com.cn/rss/politics.xml',
        'rss_backup_urls': [
            'http://www.people.com.cn/rss/society.xml',
        ],
        'type': 'news_website'
    },
    'sina': {
        'name': '新浪新闻',
        'base_url': 'https://news.sina.com.cn',
        'news_list_url': 'https://news.sina.com.cn/china/',
        'rss_url': 'https://rss.sina.com.cn/news/china/focus15.xml',
        'type': 'news_website'
    },
    'netease': {
        'name': '网易新闻',
        'base_url': 'https://news.163.com',
        'news_list_url': 'https://news.163.com/domestic/',
        'rss_url': 'https://news.163.com/special/00011K6L/rss_newstop.xml',
        'type': 'news_website'
    },
    'cctv': {
        'name': '央视网',
        'base_url': 'https://news.cctv.com',
        'news_list_url': 'https://news.cctv.com/2019/07/gaiban/cmsdatainterface/page/news_1.jsonp',
        'type': 'news_website'
    },
    'chinanews': {
        'name': '中国新闻网',
        'base_url': 'http://www.chinanews.com',
        'news_list_url': 'http://www.chinanews.com/scroll-news/news1.html',
        'type': 'news_website'
    },
    'toutiao_api': {
        'name': '今日头条API',
        'api_url': 'https://is.snssdk.com/api/news/feed/v88/',
        'type': 'api'
    }
}

# 文本处理配置
TEXT_PROCESSING_CONFIG = {
    'min_text_length': 10,  # 最小文本长度
    'max_text_length': 10000,  # 最大文本长度
    'stopwords_file': 'data/stopwords.txt',  # 停用词文件路径
    'jieba_dict_file': 'data/jieba_dict.txt'  # 自定义词典文件路径
}

# 聚类配置
CLUSTERING_CONFIG = {
    'kmeans': {
        'n_clusters': 10,  # 聚类数
        'max_iter': 300,
        'random_state': 42
    },
    'dbscan': {
        'eps': 0.5,
        'min_samples': 5
    }
}

# LDA主题模型配置
LDA_CONFIG = {
    'num_topics': 10,  # 主题数
    'passes': 10,  # 迭代次数
    'alpha': 'auto',
    'eta': 'auto',
    'random_state': 42
}

# 可视化配置
VISUALIZATION_CONFIG = {
    'output_dir': 'data/visualizations/',
    'figure_size': (12, 8),
    'dpi': 300,
    'font_family': 'SimHei'  # 中文字体
} 