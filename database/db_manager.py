# -*- coding: utf-8 -*-
"""
数据库管理模块
"""

import os
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import pandas as pd
from datetime import datetime
import logging
from config.settings import DATABASE_CONFIG

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

Base = declarative_base()

class NewsArticle(Base):
    """新闻文章数据模型"""
    __tablename__ = 'news_articles'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    news_id = Column(String(100), unique=True, nullable=False)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    source = Column(String(100), nullable=False)
    author = Column(String(100))
    publish_time = Column(DateTime)
    url = Column(String(500))
    comments_count = Column(Integer)  # 缺失=NULL，不用默认0冒充真实零值
    likes_count = Column(Integer)
    shares_count = Column(Integer)
    crawl_time = Column(DateTime, default=datetime.now)
    category = Column(String(100))
    tags = Column(String(500))

class _SQLAlchemyManager:
    """SQLAlchemy 关系型库通用操作，供 MySQL / SQLite 复用（子类负责 connect）"""

    def insert_news(self, news_data):
        """插入新闻数据（跳过已存在的news_id，避免重复插入导致整批失败）"""
        try:
            if isinstance(news_data, dict):
                news_data = [news_data]

            existing_ids = {row[0] for row in self.session.query(NewsArticle.news_id).all()}
            new_data = [d for d in news_data if d.get('news_id') not in existing_ids]
            skipped = len(news_data) - len(new_data)

            for data in new_data:
                news = NewsArticle(**data)
                self.session.add(news)

            if new_data:
                self.session.commit()
            logger.info(f"成功插入 {len(new_data)} 条新闻数据，跳过重复 {skipped} 条")

        except Exception as e:
            self.session.rollback()
            logger.error(f"插入新闻数据失败: {e}")
            raise

    def get_news_by_date(self, start_date, end_date):
        """根据日期范围获取新闻"""
        try:
            news_list = self.session.query(NewsArticle).filter(
                NewsArticle.publish_time >= start_date,
                NewsArticle.publish_time <= end_date
            ).all()

            return news_list

        except Exception as e:
            logger.error(f"查询新闻数据失败: {e}")
            raise

    def get_all_news_df(self):
        """获取所有新闻数据并返回DataFrame"""
        try:
            query = "SELECT * FROM news_articles"
            df = pd.read_sql(query, self.engine)
            return df

        except Exception as e:
            logger.error(f"获取新闻DataFrame失败: {e}")
            raise

    def close(self):
        """关闭数据库连接"""
        if self.session:
            self.session.close()
        if self.engine:
            self.engine.dispose()

class MySQLManager(_SQLAlchemyManager):
    """MySQL数据库管理器"""

    def __init__(self):
        self.config = DATABASE_CONFIG['mysql']
        self.engine = None
        self.session = None
        self.connect()

    def connect(self):
        """连接数据库"""
        try:
            import mysql.connector  # noqa: F401  惰性导入：SQLite 部署环境无需安装 MySQL 驱动
            # 创建数据库引擎
            connection_string = f"mysql+mysqlconnector://{self.config['user']}:{self.config['password']}@{self.config['host']}:{self.config['port']}/{self.config['database']}?charset={self.config['charset']}"
            self.engine = create_engine(connection_string, echo=False)

            # 创建表
            Base.metadata.create_all(self.engine)

            # 创建会话
            Session = sessionmaker(bind=self.engine)
            self.session = Session()

            logger.info("MySQL数据库连接成功")

        except Exception as e:
            logger.error(f"MySQL数据库连接失败: {e}")
            raise

class SQLiteManager(_SQLAlchemyManager):
    """SQLite数据库管理器（云端部署用，数据库文件随应用分发）"""

    def __init__(self, db_path='data/news.db'):
        self.db_path = db_path
        self.engine = None
        self.session = None
        self.connect()

    def connect(self):
        """连接 SQLite（文件不存在时自动建库建表）"""
        try:
            db_dir = os.path.dirname(self.db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
            self.engine = create_engine(f'sqlite:///{self.db_path}', echo=False)

            Base.metadata.create_all(self.engine)

            Session = sessionmaker(bind=self.engine)
            self.session = Session()

            logger.info(f"SQLite数据库连接成功: {self.db_path}")

        except Exception as e:
            logger.error(f"SQLite数据库连接失败: {e}")
            raise

class MongoDBManager:
    """MongoDB数据库管理器"""
    
    def __init__(self):
        self.config = DATABASE_CONFIG['mongodb']
        self.client = None
        self.db = None
        self.connect()
    
    def connect(self):
        """连接MongoDB"""
        try:
            from pymongo import MongoClient  # 惰性导入：非 MongoDB 环境无需安装驱动
            self.client = MongoClient(
                host=self.config['host'],
                port=self.config['port']
            )
            self.db = self.client[self.config['database']]
            
            logger.info("MongoDB数据库连接成功")
            
        except Exception as e:
            logger.error(f"MongoDB数据库连接失败: {e}")
            raise
    
    def insert_news(self, news_data, collection_name='news_articles'):
        """插入新闻数据"""
        try:
            collection = self.db[collection_name]
            
            if isinstance(news_data, dict):
                result = collection.insert_one(news_data)
                logger.info(f"成功插入新闻数据，ID: {result.inserted_id}")
            else:
                result = collection.insert_many(news_data)
                logger.info(f"成功插入 {len(result.inserted_ids)} 条新闻数据")
            
            return result
            
        except Exception as e:
            logger.error(f"插入新闻数据失败: {e}")
            raise
    
    def get_news_by_query(self, query, collection_name='news_articles'):
        """根据查询条件获取新闻"""
        try:
            collection = self.db[collection_name]
            cursor = collection.find(query)
            return list(cursor)
            
        except Exception as e:
            logger.error(f"查询新闻数据失败: {e}")
            raise
    
    def get_all_news_df(self, collection_name='news_articles'):
        """获取所有新闻数据并返回DataFrame"""
        try:
            collection = self.db[collection_name]
            cursor = collection.find()
            data = list(cursor)
            
            if data:
                df = pd.DataFrame(data)
                return df
            else:
                return pd.DataFrame()
                
        except Exception as e:
            logger.error(f"获取新闻DataFrame失败: {e}")
            raise
    
    def update_news(self, query, update_data, collection_name='news_articles'):
        """更新新闻数据"""
        try:
            collection = self.db[collection_name]
            result = collection.update_many(query, {'$set': update_data})
            logger.info(f"更新了 {result.modified_count} 条新闻数据")
            
            return result
            
        except Exception as e:
            logger.error(f"更新新闻数据失败: {e}")
            raise
    
    def close(self):
        """关闭数据库连接"""
        if self.client:
            self.client.close()

# 数据库管理器工厂
def get_db_manager(db_type='mysql'):
    """获取数据库管理器"""
    if db_type.lower() == 'mysql':
        return MySQLManager()
    elif db_type.lower() == 'mongodb':
        return MongoDBManager()
    elif db_type.lower() == 'sqlite':
        return SQLiteManager()
    else:
        raise ValueError(f"不支持的数据库类型: {db_type}") 