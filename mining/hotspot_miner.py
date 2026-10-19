# -*- coding: utf-8 -*-
"""
热点话题挖掘模块
"""

import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans, DBSCAN
from sklearn.decomposition import LatentDirichletAllocation
from sklearn.metrics import silhouette_score
from gensim import corpora, models
from gensim.models import LdaModel
import jieba
import logging
from collections import Counter
from config.settings import CLUSTERING_CONFIG, LDA_CONFIG
from preprocessing.text_processor import TextProcessor

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HotspotMiner:
    """热点话题挖掘器"""
    
    def __init__(self):
        self.clustering_config = CLUSTERING_CONFIG
        self.lda_config = LDA_CONFIG
        self.text_processor = TextProcessor()
        self.vectorizer = None
        self.feature_matrix = None
        
    def prepare_text_data(self, df):
        """准备文本数据"""
        logger.info("准备文本数据用于挖掘")
        
        # 合并标题和内容
        df['combined_text'] = df['title_clean'] + ' ' + df['content_clean']
        
        # 分词处理
        texts = []
        for text in df['combined_text']:
            words = self.text_processor.segment_text(text)
            texts.append(' '.join(words))
        
        df['processed_text'] = texts
        
        return df
    
    def build_feature_matrix(self, texts, max_features=5000):
        """构建特征矩阵"""
        logger.info("构建TF-IDF特征矩阵")
        
        # 使用TF-IDF向量化
        self.vectorizer = TfidfVectorizer(
            max_features=max_features,
            min_df=2,
            max_df=0.8,
            ngram_range=(1, 2)
        )
        
        self.feature_matrix = self.vectorizer.fit_transform(texts)
        
        logger.info(f"特征矩阵形状: {self.feature_matrix.shape}")
        
        return self.feature_matrix
    
    def kmeans_clustering(self, n_clusters=None):
        """K-Means聚类"""
        if n_clusters is None:
            n_clusters = self.clustering_config['kmeans']['n_clusters']
        
        logger.info(f"执行K-Means聚类，聚类数: {n_clusters}")
        
        kmeans = KMeans(
            n_clusters=n_clusters,
            max_iter=self.clustering_config['kmeans']['max_iter'],
            random_state=self.clustering_config['kmeans']['random_state'],
            n_init=10
        )
        
        cluster_labels = kmeans.fit_predict(self.feature_matrix)
        
        # 计算聚类质量
        if self.feature_matrix.shape[0] > n_clusters:
            silhouette_avg = silhouette_score(self.feature_matrix, cluster_labels)
            logger.info(f"K-Means聚类轮廓系数: {silhouette_avg:.3f}")
        
        return cluster_labels, kmeans
    
    def dbscan_clustering(self, eps=None, min_samples=None):
        """DBSCAN聚类"""
        if eps is None:
            eps = self.clustering_config['dbscan']['eps']
        if min_samples is None:
            min_samples = self.clustering_config['dbscan']['min_samples']
        
        logger.info(f"执行DBSCAN聚类，eps: {eps}, min_samples: {min_samples}")
        
        dbscan = DBSCAN(eps=eps, min_samples=min_samples)
        cluster_labels = dbscan.fit_predict(self.feature_matrix.toarray())
        
        n_clusters = len(set(cluster_labels)) - (1 if -1 in cluster_labels else 0)
        n_noise = list(cluster_labels).count(-1)
        
        logger.info(f"DBSCAN聚类结果: {n_clusters} 个聚类, {n_noise} 个噪声点")
        
        return cluster_labels, dbscan
    
    def optimize_kmeans_clusters(self, max_clusters=15):
        """优化K-Means聚类数"""
        logger.info("使用肘部法则优化聚类数")
        
        inertias = []
        silhouette_scores = []
        K_range = range(2, max_clusters + 1)
        
        for k in K_range:
            kmeans = KMeans(
                n_clusters=k,
                random_state=self.clustering_config['kmeans']['random_state'],
                n_init=10
            )
            cluster_labels = kmeans.fit_predict(self.feature_matrix)
            
            inertias.append(kmeans.inertia_)
            
            if len(set(cluster_labels)) > 1:
                silhouette_avg = silhouette_score(self.feature_matrix, cluster_labels)
                silhouette_scores.append(silhouette_avg)
            else:
                silhouette_scores.append(0)
        
        # 找到最优聚类数（轮廓系数最高）
        optimal_k = K_range[np.argmax(silhouette_scores)]
        logger.info(f"最优聚类数: {optimal_k}")
        
        return optimal_k, inertias, silhouette_scores
    
    def extract_cluster_topics(self, df, cluster_labels, top_words=10):
        """提取聚类主题词"""
        logger.info("提取聚类主题词")
        
        cluster_topics = {}
        feature_names = self.vectorizer.get_feature_names_out()
        
        # 为每个聚类提取主题词
        unique_labels = set(cluster_labels)
        
        for label in unique_labels:
            if label == -1:  # 跳过噪声点
                continue
                
            # 获取该聚类的文档索引
            cluster_indices = [i for i, l in enumerate(cluster_labels) if l == label]
            
            if len(cluster_indices) == 0:
                continue
            
            # 计算该聚类的TF-IDF均值
            cluster_tfidf = self.feature_matrix[cluster_indices].mean(axis=0).A1
            
            # 获取最高TF-IDF分数的词汇
            top_indices = cluster_tfidf.argsort()[-top_words:][::-1]
            top_words_scores = [(feature_names[i], cluster_tfidf[i]) for i in top_indices]
            
            cluster_topics[label] = {
                'topic_words': top_words_scores,
                'doc_count': len(cluster_indices),
                'sample_titles': df.iloc[cluster_indices]['title'].head(3).tolist()
            }
        
        return cluster_topics
    
    def lda_topic_modeling(self, df, num_topics=None):
        """LDA主题模型"""
        if num_topics is None:
            num_topics = self.lda_config['num_topics']
        
        logger.info(f"执行LDA主题建模，主题数: {num_topics}")
        
        # 准备文档
        documents = []
        for _, row in df.iterrows():
            words = self.text_processor.segment_text(row['combined_text'])
            if len(words) > 5:  # 过滤太短的文档
                documents.append(words)
        
        # 构建词典和语料库
        dictionary = corpora.Dictionary(documents)
        dictionary.filter_extremes(no_below=2, no_above=0.8)
        
        corpus = [dictionary.doc2bow(doc) for doc in documents]
        
        # 训练LDA模型
        lda_model = LdaModel(
            corpus=corpus,
            id2word=dictionary,
            num_topics=num_topics,
            passes=self.lda_config['passes'],
            alpha=self.lda_config['alpha'],
            eta=self.lda_config['eta'],
            random_state=self.lda_config['random_state']
        )
        
        # 提取主题
        topics = []
        for topic_id in range(num_topics):
            topic_words = lda_model.show_topic(topic_id, topn=10)
            topics.append({
                'topic_id': topic_id,
                'words': topic_words,
                'coherence': self.calculate_topic_coherence(topic_words, documents)
            })
        
        # 为每个文档分配主题
        doc_topics = []
        for doc in corpus:
            doc_topic_probs = lda_model.get_document_topics(doc)
            if doc_topic_probs:
                main_topic = max(doc_topic_probs, key=lambda x: x[1])
                doc_topics.append(main_topic[0])
            else:
                doc_topics.append(-1)
        
        logger.info("LDA主题建模完成")
        
        return lda_model, topics, doc_topics, dictionary
    
    def calculate_topic_coherence(self, topic_words, documents):
        """计算主题一致性"""
        # 简化的一致性计算
        words = [word for word, _ in topic_words]
        coherence_score = 0
        
        for doc in documents:
            word_count = sum(1 for word in words if word in doc)
            if word_count > 1:
                coherence_score += word_count / len(words)
        
        return coherence_score / len(documents)
    
    def rank_hotspots(self, df, cluster_labels, method='engagement'):
        """对热点话题进行排序"""
        logger.info(f"使用{method}方法对热点话题排序")
        
        hotspot_rankings = {}
        
        # 按聚类分组
        df['cluster'] = cluster_labels
        cluster_groups = df.groupby('cluster')
        
        for cluster_id, group in cluster_groups:
            if cluster_id == -1:  # 跳过噪声点
                continue
            
            # NaN-safe 互动聚合：min_count=1 使全缺失组保持 NaN（未知），不与真实 0 混淆
            c_sum = group['comments_count'].sum(min_count=1)
            l_sum = group['likes_count'].sum(min_count=1)
            s_sum = group['shares_count'].sum(min_count=1)
            has_engagement = not (pd.isna(c_sum) and pd.isna(l_sum) and pd.isna(s_sum))
            eng_val = lambda x: 0 if pd.isna(x) else x
            engagement_coverage = float(group[['comments_count', 'likes_count', 'shares_count']].notna().any(axis=1).mean())

            if method == 'engagement':
                # 基于互动量排序（互动全部缺失时记 NaN，排最后）
                engagement_score = (
                    eng_val(c_sum) * 0.4 +
                    eng_val(l_sum) * 0.3 +
                    eng_val(s_sum) * 0.3
                ) if has_engagement else float('nan')
            elif method == 'frequency':
                # 基于新闻数量排序
                engagement_score = len(group)
            elif method == 'recency':
                # 基于时间新近度排序
                recent_hours = (pd.Timestamp.now() - group['publish_time'].max()).total_seconds() / 3600
                engagement_score = 1 / (1 + recent_hours)  # 越新分数越高
            else:
                # 综合评分（互动项仅在存在真实数据时计入；缺失时不计入，也不视为真实 0）
                engagement_score = (
                    len(group) * 0.3 +  # 新闻数量
                    (eng_val(c_sum) * 0.2 + eng_val(l_sum) * 0.2 + eng_val(s_sum) * 0.2 if has_engagement else 0) +  # 互动量
                    (1 / (1 + (pd.Timestamp.now() - group['publish_time'].max()).total_seconds() / 3600)) * 0.1  # 时间因子
                )
            
            hotspot_rankings[cluster_id] = {
                'score': engagement_score,
                'news_count': len(group),
                'total_engagement': (eng_val(c_sum) + eng_val(l_sum) + eng_val(s_sum)) if has_engagement else None,
                'engagement_coverage': round(engagement_coverage, 3),
                'engagement_status': 'available' if has_engagement else 'unknown',
                'latest_time': group['publish_time'].max(),
                'sample_titles': group['title'].head(3).tolist()
            }
        
        # 按分数排序
        # NaN 分数（互动全缺失）排最后
        sorted_hotspots = sorted(hotspot_rankings.items(), key=lambda x: (x[1]['score'] if pd.notna(x[1]['score']) else float('-inf')), reverse=True)
        
        return sorted_hotspots
    
    def mine_hotspots(self, df, clustering_method='kmeans', topic_modeling=True, n_clusters=None):
        """综合热点挖掘

        Args:
            df: 清洗后的 DataFrame
            clustering_method: 'kmeans' 或 'dbscan'
            topic_modeling: 是否执行 LDA
            n_clusters: 显式指定聚类数（仅 kmeans），传入则跳过肘部法则自动选择；None 时使用配置值或自动选择
        """
        logger.info(f"开始热点话题挖掘，聚类方法: {clustering_method}, n_clusters={n_clusters}")

        # 1. 准备数据
        df = self.prepare_text_data(df)

        # 2. 构建特征矩阵
        self.build_feature_matrix(df['processed_text'].tolist())

        # 3. 聚类分析
        if clustering_method == 'kmeans':
            if n_clusters is not None:
                logger.info(f"使用显式指定的 n_clusters={n_clusters}")
                cluster_labels, clustering_model = self.kmeans_clustering(n_clusters=n_clusters)
            else:
                # 优化聚类数
                optimal_k, _, _ = self.optimize_kmeans_clusters()
                cluster_labels, clustering_model = self.kmeans_clustering(optimal_k)
        elif clustering_method == 'dbscan':
            cluster_labels, clustering_model = self.dbscan_clustering()
        else:
            raise ValueError(f"不支持的聚类方法: {clustering_method}")
        
        # 4. 提取聚类主题
        cluster_topics = self.extract_cluster_topics(df, cluster_labels)
        
        # 5. LDA主题建模
        lda_results = None
        if topic_modeling:
            lda_model, lda_topics, doc_topics, dictionary = self.lda_topic_modeling(df)
            lda_results = {
                'model': lda_model,
                'topics': lda_topics,
                'doc_topics': doc_topics,
                'dictionary': dictionary
            }
        
        # 6. 热点排序
        hotspot_rankings = self.rank_hotspots(df, cluster_labels, method='comprehensive')
        
        results = {
            'cluster_labels': cluster_labels,
            'cluster_topics': cluster_topics,
            'hotspot_rankings': hotspot_rankings,
            'lda_results': lda_results,
            'clustering_model': clustering_model,
            'processed_data': df
        }
        
        logger.info("热点话题挖掘完成")
        
        return results
    
    def generate_hotspot_report(self, results, top_k=10):
        """生成热点报告"""
        logger.info(f"生成前{top_k}个热点话题报告")
        
        report = {
            'summary': {
                'total_clusters': len(results['cluster_topics']),
                'total_news': len(results['processed_data']),
                'analysis_time': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            'top_hotspots': []
        }
        
        # 获取前K个热点
        for i, (cluster_id, hotspot_info) in enumerate(results['hotspot_rankings'][:top_k]):
            cluster_topic = results['cluster_topics'].get(cluster_id, {})
            
            hotspot = {
                'rank': i + 1,
                'cluster_id': cluster_id,
                'hotspot_score': hotspot_info['score'],
                'news_count': hotspot_info['news_count'],
                'total_engagement': hotspot_info['total_engagement'],
                'engagement_coverage': hotspot_info.get('engagement_coverage'),
                'engagement_status': hotspot_info.get('engagement_status'),
                'latest_time': (hotspot_info['latest_time'].strftime('%Y-%m-%d %H:%M:%S')
                                if pd.notna(hotspot_info['latest_time']) else '未知'),
                'topic_words': [word for word, _ in cluster_topic.get('topic_words', [])[:5]],
                'sample_titles': hotspot_info['sample_titles']
            }
            
            report['top_hotspots'].append(hotspot)
        
        return report

if __name__ == "__main__":
    # 测试热点挖掘
    from database.db_manager import get_db_manager
    from preprocessing.text_processor import DataCleaner
    
    # 获取和清洗数据
    cleaner = DataCleaner()
    df = cleaner.clean_database_data()
    
    if not df.empty:
        # 执行热点挖掘
        miner = HotspotMiner()
        results = miner.mine_hotspots(df)
        
        # 生成报告
        report = miner.generate_hotspot_report(results)
        
        print("热点话题挖掘报告:")
        print(f"总聚类数: {report['summary']['total_clusters']}")
        print(f"总新闻数: {report['summary']['total_news']}")
        print("\n前10个热点话题:")
        
        for hotspot in report['top_hotspots']:
            print(f"第{hotspot['rank']}名: {', '.join(hotspot['topic_words'])}")
            print(f"  新闻数量: {hotspot['news_count']}")
            print(f"  互动总数: {hotspot['total_engagement']}")
            print(f"  示例标题: {hotspot['sample_titles'][0] if hotspot['sample_titles'] else '无'}")
            print()
    else:
        print("没有数据可供分析")