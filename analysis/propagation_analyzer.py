# -*- coding: utf-8 -*-
"""
传播分析模块
"""

import pandas as pd
import numpy as np
import networkx as nx
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import logging
try:
    from scipy import stats
except ImportError:
    stats = None
from sklearn.preprocessing import StandardScaler
from database.db_manager import get_db_manager

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PropagationAnalyzer:
    """传播分析器"""
    
    def __init__(self):
        self.propagation_graph = nx.DiGraph()
        self.time_series_data = {}
        
    def build_propagation_network(self, df):
        """构建传播网络"""
        logger.info("构建传播网络")
        
        # 清空之前的图
        self.propagation_graph.clear()
        
        # 按照发布时间排序
        df = df.sort_values('publish_time')

        # 归一化源名：同一媒体的不同采集通道（如"网易新闻API"）合并为同一新闻源，
        # 避免同源自相似被误算成"跨源传播关系"（仅影响本图，不改动数据库与其它报告）
        df = df.copy()
        df['source'] = df['source'].astype(str).str.replace(r'API$', '', regex=True)

        # 构建节点（新闻源）
        sources = df['source'].unique()
        for source in sources:
            source_news = df[df['source'] == source]
            
            # 计算源的属性（NaN-safe：全缺失源记 None=未知，不与真实 0 混淆）
            _eng_cols = ['comments_count', 'likes_count', 'shares_count']
            _total = source_news[_eng_cols].sum(min_count=1).sum(min_count=1)
            _avg = source_news[_eng_cols].sum(axis=1, min_count=1).mean()
            self.propagation_graph.add_node(source,
                                          type='news_source',
                                          news_count=len(source_news),
                                          total_engagement=None if pd.isna(_total) else float(_total),
                                          avg_engagement=None if pd.isna(_avg) else float(_avg))
        
        # 构建边（传播关系）
        # 这里简化处理，基于相似新闻和时间先后关系构建传播关系
        self._build_propagation_edges(df)
        
        logger.info(f"传播网络构建完成: {self.propagation_graph.number_of_nodes()} 个节点, {self.propagation_graph.number_of_edges()} 条边")
        
    def _build_propagation_edges(self, df):
        """构建传播边"""
        # 基于关键词相似度和时间先后关系构建传播边
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        
        # 计算新闻之间的相似度
        texts = (df['title_clean'] + ' ' + df['content_clean']).fillna('')
        
        if len(texts) < 2:
            return
        
        vectorizer = TfidfVectorizer(max_features=1000, min_df=1, stop_words=None)
        tfidf_matrix = vectorizer.fit_transform(texts)
        similarity_matrix = cosine_similarity(tfidf_matrix)
        
        # 设置相似度阈值（降低阈值以便跨源相似新闻能建边）
        similarity_threshold = 0.15
        time_window = timedelta(hours=72)  # 放宽到72小时内的相似新闻认为有传播关系
        
        for i in range(len(df)):
            for j in range(i + 1, len(df)):
                news_i = df.iloc[i]
                news_j = df.iloc[j]
                
                # 检查时间先后关系
                time_diff = news_j['publish_time'] - news_i['publish_time']
                if time_diff > timedelta(0) and time_diff <= time_window:
                    # 检查相似度
                    if similarity_matrix[i, j] > similarity_threshold:
                        # 添加传播边
                        source_i = news_i['source']
                        source_j = news_j['source']
                        
                        if source_i != source_j:  # 不同源之间才构建传播关系
                            weight = similarity_matrix[i, j] * (1 / (time_diff.total_seconds() / 3600))  # 时间越近权重越大
                            
                            if self.propagation_graph.has_edge(source_i, source_j):
                                self.propagation_graph[source_i][source_j]['weight'] += weight
                                self.propagation_graph[source_i][source_j]['count'] += 1
                            else:
                                self.propagation_graph.add_edge(source_i, source_j, 
                                                              weight=weight, 
                                                              count=1,
                                                              avg_time_delay=time_diff.total_seconds() / 3600)
    
    def analyze_propagation_paths(self):
        """分析传播路径"""
        logger.info("分析传播路径")
        
        paths_analysis = {
            'shortest_paths': {},
            'all_paths': {},
            'path_lengths': [],
            'key_nodes': {}
        }
        
        # 计算所有节点对之间的最短路径
        try:
            shortest_paths = dict(nx.all_pairs_shortest_path(self.propagation_graph))
            paths_analysis['shortest_paths'] = shortest_paths
            
            # 统计路径长度分布
            for source in shortest_paths:
                for target in shortest_paths[source]:
                    if source != target:
                        path_length = len(shortest_paths[source][target]) - 1
                        paths_analysis['path_lengths'].append(path_length)
            
        except Exception as e:
            logger.warning(f"计算最短路径失败: {e}")
        
        # 识别关键传播节点
        try:
            # 中心性分析
            betweenness_centrality = nx.betweenness_centrality(self.propagation_graph)
            closeness_centrality = nx.closeness_centrality(self.propagation_graph)
            pagerank = nx.pagerank(self.propagation_graph)
            
            paths_analysis['key_nodes'] = {
                'betweenness_centrality': sorted(betweenness_centrality.items(), key=lambda x: x[1], reverse=True)[:5],
                'closeness_centrality': sorted(closeness_centrality.items(), key=lambda x: x[1], reverse=True)[:5],
                'pagerank': sorted(pagerank.items(), key=lambda x: x[1], reverse=True)[:5]
            }
            
        except Exception as e:
            logger.warning(f"计算中心性指标失败: {e}")
        
        return paths_analysis
    
    def analyze_propagation_patterns(self, df):
        """分析传播模式"""
        logger.info("分析传播模式")
        
        patterns_analysis = {
            'temporal_patterns': {},
            'source_patterns': {},
            'engagement_patterns': {},
            'propagation_types': {}
        }
        
        # 时间传播模式分析
        patterns_analysis['temporal_patterns'] = self._analyze_temporal_patterns(df)
        
        # 来源传播模式分析
        patterns_analysis['source_patterns'] = self._analyze_source_patterns(df)
        
        # 互动传播模式分析
        patterns_analysis['engagement_patterns'] = self._analyze_engagement_patterns(df)
        
        # 传播类型识别
        patterns_analysis['propagation_types'] = self._identify_propagation_types(df)
        
        return patterns_analysis
    
    def _analyze_temporal_patterns(self, df):
        """分析时间传播模式"""
        # 按小时分析传播趋势
        df['hour'] = df['publish_time'].dt.hour
        # min_count=1：全缺失时段记 NaN（未知），不当真实 0
        hourly_stats = df.groupby('hour').agg(
            news_count=('id', 'count'),
            comments_count=('comments_count', lambda s: s.sum(min_count=1)),
            likes_count=('likes_count', lambda s: s.sum(min_count=1)),
            shares_count=('shares_count', lambda s: s.sum(min_count=1))
        )
        
        # 按天分析传播趋势
        df['date'] = df['publish_time'].dt.date
        daily_stats = df.groupby('date').agg(
            news_count=('id', 'count'),
            comments_count=('comments_count', lambda s: s.sum(min_count=1)),
            likes_count=('likes_count', lambda s: s.sum(min_count=1)),
            shares_count=('shares_count', lambda s: s.sum(min_count=1))
        )
        
        # 将date对象转换为字符串以避免JSON序列化问题
        daily_stats_dict = {}
        for date_key, row in daily_stats.iterrows():
            daily_stats_dict[date_key.strftime('%Y-%m-%d')] = row.to_dict()
        
        return {
            'hourly_distribution': hourly_stats.to_dict('index'),
            'daily_trend': daily_stats_dict,
            'peak_hours': hourly_stats.nlargest(3, 'news_count').index.tolist(),
            'peak_days': [date.strftime('%Y-%m-%d') for date in daily_stats.nlargest(3, 'news_count').index.tolist()]
        }
    
    def _analyze_source_patterns(self, df):
        """分析来源传播模式"""
        source_stats = df.groupby('source').agg({
            'id': 'count',
            'comments_count': ['sum', 'mean'],
            'likes_count': ['sum', 'mean'],
            'shares_count': ['sum', 'mean']
        })
        
        source_stats.columns = ['news_count', 'total_comments', 'avg_comments',
                              'total_likes', 'avg_likes', 'total_shares', 'avg_shares']

        # NaN-safe：某源互动全缺失时 sum 记 NaN（未知），不当真实 0
        for _col, _total_col in [('comments_count', 'total_comments'), ('likes_count', 'total_likes'), ('shares_count', 'total_shares')]:
            source_stats[_total_col] = df.groupby('source')[_col].sum(min_count=1)
        
        # 计算影响力指标
        source_stats['influence_score'] = (
            source_stats['total_comments'] * 0.3 +
            source_stats['total_likes'] * 0.3 +
            source_stats['total_shares'] * 0.4
        )
        
        return {
            'source_statistics': source_stats.to_dict('index'),
            'top_sources_by_volume': source_stats.nlargest(5, 'news_count').index.tolist(),
            'top_sources_by_influence': source_stats.nlargest(5, 'influence_score').index.tolist()
        }
    
    def _analyze_engagement_patterns(self, df):
        """分析互动传播模式"""
        # 计算总互动量（min_count=1：全缺失行保持 NaN=未知，不当作真实 0）
        eng_cols = ['comments_count', 'likes_count', 'shares_count']
        df['total_engagement'] = df[eng_cols].sum(axis=1, min_count=1)

        known = df['total_engagement'].dropna()
        if len(known) == 0:
            return {
                'status': 'insufficient_data',
                'note': '互动量数据缺失或来源未知，未进行互动统计（缺失≠零互动）',
                'known_records': 0,
                'coverage': 0.0
            }

        # 互动量分布（仅基于有真实数据的记录）
        engagement_stats = {
            'mean_engagement': known.mean(),
            'median_engagement': known.median(),
            'std_engagement': known.std(),
            'max_engagement': known.max(),
            'min_engagement': known.min(),
            'known_records': int(len(known)),
            'coverage': float(len(known) / len(df))
        }

        # 互动类型占比（全缺失列的列和为 NaN，按 0 处理后再判 total_all）
        total_comments = df['comments_count'].sum(min_count=1)
        total_likes = df['likes_count'].sum(min_count=1)
        total_shares = df['shares_count'].sum(min_count=1)
        _vals = [0 if pd.isna(v) else v for v in (total_comments, total_likes, total_shares)]
        total_all = sum(_vals)
        
        if total_all > 0:
            engagement_composition = {
                'comments_ratio': total_comments / total_all,
                'likes_ratio': total_likes / total_all,
                'shares_ratio': total_shares / total_all
            }
        else:
            engagement_composition = {
                'comments_ratio': 0,
                'likes_ratio': 0,
                'shares_ratio': 0
            }
        
        return {
            'engagement_statistics': engagement_stats,
            'engagement_composition': engagement_composition,
            'high_engagement_news': df[df['total_engagement'].notna()].nlargest(10, 'total_engagement')[['title', 'total_engagement']].to_dict('records')
        }
    
    def _identify_propagation_types(self, df):
        """识别传播类型"""
        propagation_types = {}
        
        # 基于时间序列分析传播模式
        df_sorted = df.sort_values('publish_time')
        
        # 计算时间间隔
        if len(df_sorted) > 1:
            time_diffs = df_sorted['publish_time'].diff().dt.total_seconds() / 3600  # 转换为小时
            time_diffs = time_diffs.dropna()
            
            # 爆发式传播：短时间内大量新闻
            if len(time_diffs) > 0:
                avg_time_interval = time_diffs.mean()
                if avg_time_interval < 2:  # 平均间隔小于2小时
                    propagation_types['burst_propagation'] = True
                else:
                    propagation_types['burst_propagation'] = False
                
                # 持续传播：长时间持续发布
                time_span = (df_sorted['publish_time'].max() - df_sorted['publish_time'].min()).total_seconds() / 3600
                if time_span > 72:  # 超过72小时
                    propagation_types['sustained_propagation'] = True
                else:
                    propagation_types['sustained_propagation'] = False
            else:
                propagation_types['burst_propagation'] = False
                propagation_types['sustained_propagation'] = False
        else:
            propagation_types['burst_propagation'] = False
            propagation_types['sustained_propagation'] = False
        
        # 病毒式传播：高互动量和快速传播（互动全部缺失时不做判定，不默认否定）
        if df['total_engagement'].notna().sum() == 0:
            propagation_types['viral_propagation'] = None  # 互动数据缺失，无法判定
        else:
            high_engagement_ratio = (df['total_engagement'] > df['total_engagement'].quantile(0.8)).sum() / len(df)
            propagation_types['viral_propagation'] = high_engagement_ratio > 0.3
        
        return propagation_types
    
    def calculate_influence_score(self, df):
        """计算传播影响力评估"""
        logger.info("计算传播影响力")
        
        influence_metrics = {}
        
        # 1. 覆盖度指标
        unique_sources = df['source'].nunique()
        total_news = len(df)
        influence_metrics['coverage_score'] = unique_sources * np.log(total_news + 1)
        
        # 2. 互动度指标（全部缺失时记 None，不参与综合分，避免把未知当 0）
        _eng_total = df[['comments_count', 'likes_count', 'shares_count']].sum(min_count=1).sum(min_count=1)
        if pd.isna(_eng_total):
            influence_metrics['engagement_score'] = None
        else:
            avg_engagement = _eng_total / total_news if total_news > 0 else 0
            influence_metrics['engagement_score'] = np.log(_eng_total + 1) * (1 + avg_engagement / 100)
        
        # 3. 传播深度指标
        if self.propagation_graph.number_of_nodes() > 0:
            try:
                avg_path_length = nx.average_shortest_path_length(self.propagation_graph)
                influence_metrics['depth_score'] = 1 / (avg_path_length + 0.1)  # 路径越短，传播越深入
            except:
                influence_metrics['depth_score'] = 0
        else:
            influence_metrics['depth_score'] = 0
        
        # 4. 传播速度指标
        if len(df) > 1:
            time_span = (df['publish_time'].max() - df['publish_time'].min()).total_seconds() / 3600
            speed_score = total_news / (time_span + 1)  # 单位时间内的新闻数量
            influence_metrics['speed_score'] = speed_score
        else:
            influence_metrics['speed_score'] = 0
        
        # 5. 综合影响力分数
        weights = {
            'coverage_score': 0.25,
            'engagement_score': 0.35,
            'depth_score': 0.2,
            'speed_score': 0.2
        }
        
        # 标准化各项指标（engagement_score 为 None 时剔除互动维度，按剩余权重归一）
        if influence_metrics.get('engagement_score') is None:
            influence_metrics['engagement_note'] = '互动量数据缺失或来源未知，综合影响力未计入互动维度'
        valid_weights = {k: w for k, w in weights.items() if influence_metrics.get(k) is not None}
        scaler = StandardScaler()
        scores = np.array([[influence_metrics[key] for key in valid_weights.keys()]])

        try:
            normalized_scores = scaler.fit_transform(scores)[0]
            influence_metrics['overall_influence'] = sum(
                normalized_scores[i] * weight
                for i, weight in enumerate(valid_weights.values())
            ) / sum(valid_weights.values())
        except:
            influence_metrics['overall_influence'] = sum(
                influence_metrics[key] * weight
                for key, weight in valid_weights.items()
            ) / sum(valid_weights.values())
        
        return influence_metrics
    
    def generate_propagation_report(self, df):
        """生成传播分析报告"""
        logger.info("生成传播分析报告")
        
        # 按标题去重：同一内容被多通道重复采集（如"网易新闻/网易新闻API"）时只保留一条，
        # 避免把重复采集误判为跨源传播边
        df = df[df['title'].notna()].copy()
        df['_title_norm'] = df['title'].astype(str).str.strip()
        _n_before = len(df)
        df = df.drop_duplicates(subset='_title_norm').drop(columns='_title_norm')
        if len(df) < _n_before:
            logger.info(f"传播分析前按标题去重: {_n_before} -> {len(df)}")

        # 构建传播网络
        self.build_propagation_network(df)
        
        # 分析传播路径
        paths_analysis = self.analyze_propagation_paths()
        
        # 分析传播模式
        patterns_analysis = self.analyze_propagation_patterns(df)
        
        # 计算影响力
        influence_metrics = self.calculate_influence_score(df)
        
        # 计算时间跨度，确保转换为数值类型
        try:
            time_span_hours = (df['publish_time'].max() - df['publish_time'].min()).total_seconds() / 3600
        except:
            time_span_hours = 0.0
        
        report = {
            'summary': {
                'total_news': len(df),
                'unique_sources': df['source'].nunique(),
                'time_span_hours': float(time_span_hours),  # 确保是浮点数
                'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            'network_analysis': {
                'nodes_count': self.propagation_graph.number_of_nodes(),
                'edges_count': self.propagation_graph.number_of_edges(),
                'density': float(nx.density(self.propagation_graph)) if self.propagation_graph.number_of_nodes() > 1 else 0.0
            },
            'paths_analysis': paths_analysis,
            'patterns_analysis': patterns_analysis,
            'influence_metrics': influence_metrics
        }

        return _nan_to_none(report)

def _nan_to_none(obj):
    """递归将 NaN/NaT 转为 None，避免报告把缺失输出为 0 或非法 JSON 值"""
    import math
    if isinstance(obj, dict):
        return {k: _nan_to_none(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_nan_to_none(v) for v in obj]
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if obj is pd.NaT:
        return None
    return obj

class PropagationVisualizer:
    """传播可视化器"""
    
    def __init__(self):
        pass
    
    def visualize_propagation_network(self, graph, output_path='data/visualizations/propagation_network.html'):
        """可视化传播网络"""
        try:
            import matplotlib.pyplot as plt
            import matplotlib
            matplotlib.rcParams['font.sans-serif'] = ['SimHei']  # 设置中文字体
            matplotlib.rcParams['axes.unicode_minus'] = False
            
            plt.figure(figsize=(12, 8))
            
            # 计算节点位置
            pos = nx.spring_layout(graph, k=1, iterations=50)
            
            # 绘制节点
            node_sizes = [graph.nodes[node].get('news_count', 1) * 100 for node in graph.nodes()]
            nx.draw_networkx_nodes(graph, pos, node_size=node_sizes, node_color='lightblue', alpha=0.7)
            
            # 绘制边
            edge_weights = [graph[u][v].get('weight', 1) for u, v in graph.edges()]
            nx.draw_networkx_edges(graph, pos, width=[w/max(edge_weights)*3 for w in edge_weights], 
                                 alpha=0.5, edge_color='gray', arrows=True)
            
            # 绘制标签
            nx.draw_networkx_labels(graph, pos, font_size=8, font_family='SimHei')
            
            plt.title('新闻传播网络图', fontsize=16, fontweight='bold')
            plt.axis('off')
            plt.tight_layout()
            
            # 保存图片
            plt.savefig(output_path.replace('.html', '.png'), dpi=300, bbox_inches='tight')
            plt.close()
            
            logger.info(f"传播网络图已保存到: {output_path.replace('.html', '.png')}")
            
        except Exception as e:
            logger.error(f"传播网络可视化失败: {e}")

if __name__ == "__main__":
    # 测试传播分析
    from database.db_manager import get_db_manager
    from preprocessing.text_processor import DataCleaner
    
    # 获取和清洗数据
    cleaner = DataCleaner()
    df = cleaner.clean_database_data()
    
    if not df.empty:
        # 执行传播分析
        analyzer = PropagationAnalyzer()
        report = analyzer.generate_propagation_report(df)
        
        print("传播分析报告:")
        print(f"总新闻数: {report['summary']['total_news']}")
        print(f"新闻源数: {report['summary']['unique_sources']}")
        print(f"时间跨度: {report['summary']['time_span_hours']:.1f} 小时")
        print(f"网络节点数: {report['network_analysis']['nodes_count']}")
        print(f"网络边数: {report['network_analysis']['edges_count']}")
        print(f"综合影响力: {report['influence_metrics']['overall_influence']:.2f}")
        
        # 可视化
        visualizer = PropagationVisualizer()
        visualizer.visualize_propagation_network(analyzer.propagation_graph)
        
    else:
        print("没有数据可供分析") 