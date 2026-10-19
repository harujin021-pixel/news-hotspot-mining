# -*- coding: utf-8 -*-
"""
数据可视化模块
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
try:
    import seaborn as sns
except ImportError:
    sns = None
from pyecharts import options as opts
from pyecharts.charts import Bar, Line, Pie, WordCloud, Graph, Timeline, Scatter
from pyecharts.globals import ThemeType, CurrentConfig
try:
    from wordcloud import WordCloud as WC
except ImportError:
    WC = None
import networkx as nx
from datetime import datetime
import os
import logging
from config.settings import VISUALIZATION_CONFIG

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 设置matplotlib中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

# 图表与仪表板文案（中/英双语）
_T = {
    'zh': {
        'wc_series': '热点话题词云',
        'wc_title': '热点话题词云图',
        'rank_score': '热度分数',
        'rank_count': '新闻数量',
        'rank_title': '热点话题排行榜',
        'rank_subtitle': '综合评分=新闻数量+互动量(仅真实数据计入)+时间因子\n互动缺失时不计入(缺失≠0)',
        'rank_yaxis': '分数',
        'topic_fallback': '话题{cluster_id}',
        'trend_count': '新闻数量',
        'trend_eng': '总互动量',
        'trend_title_eng': '新闻发布和互动趋势',
        'trend_sub_eng': '按日期统计（离散采集日期，非连续时间序列）',
        'trend_title_noeng': '新闻发布趋势',
        'trend_sub_noeng': '互动量数据缺失或来源未知，仅展示新闻数量（缺失≠0）\n离散采集日期，非连续时间序列',
        'trend_xaxis': '日期',
        'trend_yaxis_eng': '互动量',
        'src_series': '新闻源分布',
        'src_title': '新闻源分布',
        'eng_comments': '评论',
        'eng_likes': '点赞',
        'eng_shares': '分享',
        'eng_title': '新闻互动量TOP{n}',
        'eng_scope': '口径=评论+点赞+分享（采集时刻快照值），仅互动字段完整的真实记录参与排名',
        'eng_subtitle': '数据来源：{src}；其余新闻源互动字段全部缺失（缺失≠0）',
        'eng_src_join': '、',
        'eng_xaxis': '互动量',
        'eng_empty_cat': '无有效互动数据',
        'eng_empty_series': '有效互动记录数',
        'eng_empty_title': '互动量数据不足',
        'eng_empty_text': '当前样本的互动字段全部缺失或来源未知（缺失≠0），无真实互动量可绘制图表',
        'net_title': '新闻源相似关系网络',
        'net_subtitle': '边=跨源新闻文本余弦相似度(>0.15 且 72 小时内)，表示内容相似与时间先后，非已证实的转载路径',
        'net_empty_cat': '无有效传播边',
        'net_empty_series': '有效传播边数量',
        'net_empty_title': '传播关系数据不足',
        'net_empty_text': '当前样本未检测到满足条件(跨源、文本余弦相似度>0.15、72小时内)的相似新闻对，无真实传播关系可展示',
        'evo_series': '新闻数量',
        'evo_title': '话题热度演化 - {date}',
        'evo_yaxis': '新闻数量',
        'evo_err_cat': '错误',
        'evo_err_series': '提示',
        'evo_err_title': '话题演化时间线生成失败',
        'dash_title': '新闻热点挖掘可视化仪表板',
        'dash_sub': '基于机器学习的新闻热点话题挖掘与传播分析系统',
    },
    'en': {
        'wc_series': 'Hot Topics',
        'wc_title': 'Hot Topic Word Cloud',
        'rank_score': 'Hotness Score',
        'rank_count': 'News Count',
        'rank_title': 'Hot Topic Ranking',
        'rank_subtitle': 'Score = news count + engagement (real data only) + time factor\nMissing engagement is excluded (missing ≠ 0)',
        'rank_yaxis': 'Score',
        'topic_fallback': 'Topic {cluster_id}',
        'trend_count': 'News Count',
        'trend_eng': 'Total Engagement',
        'trend_title_eng': 'News Publication & Engagement Trend',
        'trend_sub_eng': 'Daily counts (discrete collection dates, not a continuous time series)',
        'trend_title_noeng': 'News Publication Trend',
        'trend_sub_noeng': 'Engagement data missing or source unknown; news count only (missing ≠ 0)\nDiscrete collection dates, not a continuous time series',
        'trend_xaxis': 'Date',
        'trend_yaxis_eng': 'Engagement',
        'src_series': 'Source Distribution',
        'src_title': 'News Source Distribution',
        'eng_comments': 'Comments',
        'eng_likes': 'Likes',
        'eng_shares': 'Shares',
        'eng_title': 'Top {n} News by Engagement',
        'eng_scope': 'Metric = comments + likes + shares (snapshot at collection time);\nonly records with all three fields present are ranked',
        'eng_subtitle': 'Data sources: {src}; all other sources lack engagement fields (missing ≠ 0)',
        'eng_src_join': ', ',
        'eng_xaxis': 'Engagement',
        'eng_empty_cat': 'No valid engagement data',
        'eng_empty_series': 'Valid engagement records',
        'eng_empty_title': 'Insufficient Engagement Data',
        'eng_empty_text': 'All engagement fields in the current sample are missing or from unknown sources (missing ≠ 0); no real engagement to plot',
        'net_title': 'News Source Similarity Network',
        'net_subtitle': 'Edges = cross-source text cosine similarity (>0.15 within 72h); indicate content similarity and temporal order, not proven reprint paths',
        'net_empty_cat': 'No valid propagation edges',
        'net_empty_series': 'Valid propagation edges',
        'net_empty_title': 'Insufficient Propagation Data',
        'net_empty_text': 'No cross-source news pairs meeting the criteria (cosine similarity > 0.15, within 72h) detected in the current sample; no real propagation relations to display',
        'evo_series': 'News Count',
        'evo_title': 'Topic Evolution - {date}',
        'evo_yaxis': 'News Count',
        'evo_err_cat': 'Error',
        'evo_err_series': 'Note',
        'evo_err_title': 'Failed to Generate Topic Evolution Timeline',
        'dash_title': 'News Hotspot Mining Dashboard',
        'dash_sub': 'A Machine-Learning-Based System for News Hotspot Mining and Propagation Analysis',
    },
}

class NewsVisualizer:
    """新闻数据可视化器"""
    
    def __init__(self):
        self.config = VISUALIZATION_CONFIG
        self.output_dir = self.config['output_dir']
        os.makedirs(self.output_dir, exist_ok=True)
        # 让 pyecharts 生成的 HTML 引用本地 ECharts JS（离线化，避免 CDN 证书/网络问题）
        CurrentConfig.ONLINE_HOST = "assets/"
    
    def _lang_file(self, filename, lang):
        """按语言生成图表输出路径：中文版沿用原名，其余语言加 _{lang} 后缀"""
        if lang != 'zh':
            filename = filename.replace('.html', f'_{lang}.html')
        return os.path.join(self.output_dir, filename)

    def create_hotspot_wordcloud(self, hotspot_results, output_path=None, lang='zh'):
        """创建热点话题词云图"""
        if output_path is None:
            output_path = self._lang_file('hotspot_wordcloud.html', lang)
        t = _T[lang]

        logger.info("生成热点话题词云图")
        
        # 收集所有热点话题的关键词
        word_freq = {}
        
        for cluster_id, topic_info in hotspot_results['cluster_topics'].items():
            for word, score in topic_info['topic_words'][:10]:
                # 跳过多词短语（ngram_range=(1,2) 产生的 bigram），避免与其成分单词重复出现
                if len(word.split()) > 1:
                    continue
                if word in word_freq:
                    word_freq[word] += score * topic_info['doc_count']
                else:
                    word_freq[word] = score * topic_info['doc_count']
        
        # 转换为PyEcharts WordCloud格式
        word_data = [(word, int(freq * 1000)) for word, freq in sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:50]]
        
        # 创建词云图
        wordcloud = (
            WordCloud(init_opts=opts.InitOpts(width="100%", height="380px"))
            .add(t['wc_series'], word_data, word_size_range=[20, 100])
            .set_global_opts(
                title_opts=opts.TitleOpts(title=t['wc_title'], title_textstyle_opts=opts.TextStyleOpts(font_size=20)),
                tooltip_opts=opts.TooltipOpts(is_show=True)
            )
        )
        
        wordcloud.render(output_path)
        logger.info(f"词云图已保存到: {output_path}")
        
        return wordcloud
    
    def create_hotspot_ranking_chart(self, hotspot_results, output_path=None, top_k=10, lang='zh'):
        """创建热点话题排行图"""
        if output_path is None:
            output_path = self._lang_file('hotspot_ranking.html', lang)
        t = _T[lang]
        
        logger.info(f"生成前{top_k}个热点话题排行图")
        
        # 获取排行数据
        rankings = hotspot_results['hotspot_rankings'][:top_k]
        
        topics = []
        scores = []
        news_counts = []
        
        for cluster_id, info in rankings:
            cluster_topic = hotspot_results['cluster_topics'].get(cluster_id, {})
            topic_words = [word for word, _ in cluster_topic.get('topic_words', [])[:3]]
            topic_name = ', '.join(topic_words) if topic_words else t['topic_fallback'].format(cluster_id=cluster_id)
            
            topics.append(topic_name)
            scores.append(round(info['score'], 2))
            news_counts.append(info['news_count'])
        
        # 创建柱状图
        bar = (
            Bar(init_opts=opts.InitOpts(width="100%", height="380px"))
            .add_xaxis(topics)
            .add_yaxis(t['rank_score'], scores, color="#5470c6")
            .add_yaxis(t['rank_count'], news_counts, color="#91cc75")
            .set_global_opts(
                title_opts=opts.TitleOpts(title=t['rank_title'], subtitle=t['rank_subtitle']),
                xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45)),
                yaxis_opts=opts.AxisOpts(name=t['rank_yaxis']),
                tooltip_opts=opts.TooltipOpts(trigger="axis", axis_pointer_type="cross"),
                datazoom_opts=[opts.DataZoomOpts(range_start=0, range_end=100)],
                legend_opts=opts.LegendOpts(pos_right="3%", pos_top="18%")
            )
        )
        # 顶部留足两行副标题空间，图例下移避免与副标题重叠
        bar.options["grid"] = {"left": 10, "right": 10, "top": 100, "containLabel": True}
        
        bar.render(output_path)
        logger.info(f"排行图已保存到: {output_path}")
        
        return bar
    
    def create_time_trend_chart(self, df, output_path=None, lang='zh'):
        """创建时间趋势图"""
        if output_path is None:
            output_path = self._lang_file('time_trend.html', lang)
        t = _T[lang]
        
        logger.info("生成时间趋势图")
        
        # 按日期分组统计
        df['date'] = pd.to_datetime(df['publish_time']).dt.date
        daily_stats = df.groupby('date').agg({
            'id': 'count',
            'comments_count': 'sum',
            'likes_count': 'sum',
            'shares_count': 'sum'
        }).reset_index()
        
        daily_stats.columns = ['date', 'news_count', 'comments', 'likes', 'shares']

        # 互动量是否存在真实数据（缺失不画成 0 折线）
        eng_cols = ['comments_count', 'likes_count', 'shares_count']
        has_engagement = all(c in df.columns for c in eng_cols) and bool(df[eng_cols].notna().any().any())

        # 转换日期格式
        dates = [str(date) for date in daily_stats['date']]

        # 创建折线图（离散采集日期，不用平滑曲线伪装连续趋势）
        line = Line(init_opts=opts.InitOpts(width="100%", height="380px")).add_xaxis(dates)
        line = line.add_yaxis(t['trend_count'], daily_stats['news_count'].tolist(), is_smooth=False, color="#5470c6")
        if has_engagement:
            daily_stats['total_engagement'] = daily_stats['comments'] + daily_stats['likes'] + daily_stats['shares']
            line = line.add_yaxis(t['trend_eng'], daily_stats['total_engagement'].tolist(), is_smooth=False, color="#91cc75", yaxis_index=1)
            title, subtitle = t['trend_title_eng'], t['trend_sub_eng']
        else:
            title, subtitle = t['trend_title_noeng'], t['trend_sub_noeng']
        line = line.set_global_opts(
            title_opts=opts.TitleOpts(title=title, subtitle=subtitle),
            xaxis_opts=opts.AxisOpts(type_="category", name=t['trend_xaxis']),
            tooltip_opts=opts.TooltipOpts(trigger="axis"),
            legend_opts=opts.LegendOpts(pos_bottom="2%", pos_left="center")
        )
        # 图例放底部居中，避免与副标题及右侧互动量轴名称重叠；底部留出图例与轴名空间
        line.options["grid"] = {"left": 10, "right": 50, "top": 85, "bottom": 75, "containLabel": True}
        if has_engagement:
            line = line.extend_axis(yaxis=opts.AxisOpts(name=t['trend_yaxis_eng'], position="right"))
        
        line.render(output_path)
        logger.info(f"时间趋势图已保存到: {output_path}")
        
        return line
    
    def create_source_distribution_chart(self, df, output_path=None, lang='zh'):
        """创建新闻源分布饼图"""
        if output_path is None:
            output_path = self._lang_file('source_distribution.html', lang)
        t = _T[lang]
        
        logger.info("生成新闻源分布图")
        
        # 统计各新闻源的新闻数量
        source_counts = df['source'].value_counts()
        
        # 准备饼图数据
        pie_data = [(source, count) for source, count in source_counts.items()]
        
        # 创建饼图
        pie = (
            Pie(init_opts=opts.InitOpts(width="100%", height="380px"))
            .add(t['src_series'], pie_data, radius=["40%", "70%"])
            .set_global_opts(
                title_opts=opts.TitleOpts(title=t['src_title'], pos_left="center"),
                legend_opts=opts.LegendOpts(pos_left="left", orient="vertical")
            )
            .set_series_opts(label_opts=opts.LabelOpts(formatter="{b}: {c} ({d}%)"))
        )
        
        pie.render(output_path)
        logger.info(f"新闻源分布图已保存到: {output_path}")
        
        return pie
    
    def create_engagement_top(self, df, output_path=None, top_n=10, lang='zh'):
        """创建互动量TOP榜（横向堆叠条形图：评论+点赞+分享）"""
        if output_path is None:
            output_path = self._lang_file('engagement_top.html', lang)
        t = _T[lang]

        logger.info("生成互动量TOP榜")

        eng_cols = ['comments_count', 'likes_count', 'shares_count']
        # 仅使用三个互动字段完整的真实记录（部分缺失则真实总量未知，不参与排名；缺失≠0）
        eng_df = df.dropna(subset=eng_cols, how='any').copy()

        # 无任何有效互动数据时，不以空白网格冒充图表，生成数据不足提示
        if eng_df.empty:
            logger.warning("互动量数据全部缺失，生成数据不足提示图")
            return self._create_empty_engagement(output_path, lang)

        eng_df['total_engagement'] = eng_df[eng_cols].sum(axis=1)
        top_df = eng_df.nlargest(top_n, 'total_engagement')

        # 标注候选数据的来源构成（哪些新闻站提供了真实互动字段）
        src_desc = t['eng_src_join'].join(f"{s}×{c}" for s, c in eng_df['source'].value_counts().items())

        # 标题截断，避免纵轴标签过长
        titles = [str(x) if len(str(x)) <= 20 else str(x)[:20] + '…' for x in top_df['title']]
        series = {col: [float(v) for v in top_df[col]] for col in eng_cols}
        # 副标题行数决定图例与绘图区下移量（英文口径拆成两行，共三行副标题）
        subtitle_text = t['eng_scope'] + "\n" + t['eng_subtitle'].format(src=src_desc)
        top_pad = 115 + 18 * (subtitle_text.count("\n") - 1)
        # 倒序传入配合 reversal_axis，使互动量最高的新闻排在最上方
        bar = (
            Bar(init_opts=opts.InitOpts(width="100%", height="380px"))
            .add_xaxis(titles[::-1])
            .add_yaxis(t['eng_comments'], series['comments_count'][::-1], stack="engagement")
            .add_yaxis(t['eng_likes'], series['likes_count'][::-1], stack="engagement")
            .add_yaxis(t['eng_shares'], series['shares_count'][::-1], stack="engagement")
            .reversal_axis()
            .set_global_opts(
                title_opts=opts.TitleOpts(
                    title=t['eng_title'].format(n=len(top_df)),
                    subtitle=subtitle_text
                ),
                tooltip_opts=opts.TooltipOpts(trigger="axis", axis_pointer_type="shadow"),
                xaxis_opts=opts.AxisOpts(name=t['eng_xaxis']),
                legend_opts=opts.LegendOpts(pos_top=f"{top_pad - 40}px")
            )
        )
        # 纵轴为新闻标题：containLabel 自动留足标签宽度；顶部留给副标题与图例
        bar.options["grid"] = {"left": 10, "top": top_pad, "bottom": 30, "containLabel": True}

        bar.render(output_path)
        logger.info(f"互动量TOP榜已保存到: {output_path}")

        return bar

    def _create_empty_engagement(self, output_path, lang='zh'):
        """互动量数据全部缺失时的提示图（不填充任何虚构数值，不以空白网格冒充图表）"""
        t = _T[lang]
        plot = (
            Bar(init_opts=opts.InitOpts(width="100%", height="380px"))
            .add_xaxis([t['eng_empty_cat']])
            .add_yaxis(t['eng_empty_series'], [0])
            .set_global_opts(
                title_opts=opts.TitleOpts(title=t['eng_empty_title']),
                xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(font_size=13)),
                yaxis_opts=opts.AxisOpts(name=t['eng_empty_series']),
                legend_opts=opts.LegendOpts(is_show=False)
            )
        )
        # 说明文字置于图表中央（不用 title 副标题，避免窄 iframe 内主副标题重叠）
        plot.options['graphic'] = [{
            'type': 'text', 'left': 'center', 'top': '40%',
            'style': {
                'text': t['eng_empty_text'],
                'fontSize': 14, 'fill': '#666'
            }
        }]
        plot.render(output_path)
        logger.info(f"互动数据不足提示图已保存到: {output_path}")
        return plot
    
    def create_propagation_network_chart(self, propagation_graph=None, output_path=None, lang='zh'):
        """创建传播网络图"""
        if output_path is None:
            output_path = self._lang_file('propagation_network.html', lang)
        t = _T[lang]

        logger.info("生成传播网络图")

        try:
            # 无传播图、无节点或无有效边时，显示"数据不足"提示，绝不填充虚构节点/边
            if (propagation_graph is None
                    or len(propagation_graph.nodes()) == 0
                    or len(propagation_graph.edges()) == 0):
                logger.warning("传播关系数据不足（无节点或无有效边），生成数据不足提示图")
                return self._create_default_propagation_network(output_path, lang)
            
            # 准备节点数据（按 news_count 归一化到 24~64，避免个别大源撑满画布、遮住连线）
            counts = [propagation_graph.nodes[n].get('news_count') or 1
                      for n in propagation_graph.nodes()]
            c_min, c_max = min(counts), max(counts)

            def _size(c):
                if c_max == c_min:
                    return 40
                return 24 + (c - c_min) / (c_max - c_min) * 40

            nodes = []
            for node in propagation_graph.nodes():
                node_data = propagation_graph.nodes[node]
                nodes.append({
                    "name": node,
                    "symbolSize": _size(node_data.get('news_count') or 1),
                    "value": node_data.get('total_engagement', 0)
                })

            # 准备边数据
            links = []
            for edge in propagation_graph.edges():
                edge_data = propagation_graph.edges[edge]
                links.append({
                    "source": edge[0],
                    "target": edge[1],
                    "value": edge_data.get('weight', 1)
                })

            # 创建网络图（边线加粗半透明保证可见；标签放在节点右侧）
            graph = (
                Graph(init_opts=opts.InitOpts(width="100%", height="560px"))
                .add(
                    "",
                    nodes,
                    links,
                    repulsion=6000,
                    layout="force",
                    is_rotate_label=True,
                    linestyle_opts=opts.LineStyleOpts(
                        color="source", width=2.5, opacity=0.65, curve=0.2),
                    label_opts=opts.LabelOpts(position="right")
                )
                .set_global_opts(
                    title_opts=opts.TitleOpts(
                        title=t['net_title'],
                        subtitle=t['net_subtitle']
                    ),
                    legend_opts=opts.LegendOpts(is_show=False)
                )
            )
            
            graph.render(output_path)
            logger.info(f"传播网络图已保存到: {output_path}")
            
            return graph
            
        except Exception as e:
            logger.error(f"创建传播网络图失败: {e}")
            return self._create_default_propagation_network(output_path, lang)
    
    def _create_default_propagation_network(self, output_path, lang='zh'):
        """传播关系数据不足时的提示图（不填充任何虚构节点、边或数值）"""
        t = _T[lang]
        plot = (
            Bar(init_opts=opts.InitOpts(width="100%", height="380px"))
            .add_xaxis([t['net_empty_cat']])
            .add_yaxis(t['net_empty_series'], [0])
            .set_global_opts(
                title_opts=opts.TitleOpts(title=t['net_empty_title']),
                xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(font_size=13)),
                yaxis_opts=opts.AxisOpts(name=t['net_empty_series']),
                legend_opts=opts.LegendOpts(is_show=False)
            )
        )
        # 说明文字置于图表中央（不用 title 副标题，避免窄 iframe 内主副标题重叠）
        plot.options['graphic'] = [{
            'type': 'text', 'left': 'center', 'top': '40%',
            'style': {
                'text': t['net_empty_text'],
                'fontSize': 14, 'fill': '#666'
            }
        }]
        plot.render(output_path)
        logger.info(f"传播关系数据不足提示图已保存到: {output_path}")
        return plot
    
    def create_topic_evolution_timeline(self, hotspot_results, df, output_path=None, lang='zh'):
        """创建话题演化时间线"""
        if output_path is None:
            output_path = self._lang_file('topic_evolution.html', lang)
        t = _T[lang]
        
        logger.info("生成话题演化时间线")
        
        try:
            # 按聚类和时间分组
            df_with_cluster = df.copy()
            df_with_cluster['cluster'] = hotspot_results['cluster_labels']
            df_with_cluster['date'] = pd.to_datetime(df_with_cluster['publish_time']).dt.date
            
            # 获取每个话题在不同时间的新闻数量
            timeline_data = df_with_cluster.groupby(['cluster', 'date']).size().unstack(fill_value=0)
            
            # 创建时间线
            timeline = Timeline(init_opts=opts.InitOpts(width="100%", height="420px"))
            
            for date in timeline_data.columns:
                bar_data = []
                for cluster_id in timeline_data.index:
                    if cluster_id == -1:  # 跳过噪声点
                        continue
                    
                    # 获取话题名称
                    cluster_topic = hotspot_results.get('cluster_topics', {}).get(cluster_id, {})
                    topic_words = cluster_topic.get('topic_words', [])
                    
                    if topic_words:
                        # 提取前2个关键词作为话题名称
                        topic_name = ', '.join([word for word, _ in topic_words[:2]])
                    else:
                        # 如果没有主题词，使用聚类ID
                        topic_name = t['topic_fallback'].format(cluster_id=cluster_id)
                    
                    # 获取该话题在该日期的新闻数量
                    news_count = int(timeline_data.loc[cluster_id, date])
                    
                    if news_count > 0:  # 只添加有新闻的话题
                        bar_data.append((topic_name, news_count))
                
                # 排序并取前10个
                bar_data.sort(key=lambda x: x[1], reverse=True)
                bar_data = bar_data[:10]
                
                if bar_data:
                    topics, counts = zip(*bar_data)
                    
                    bar = (
                        Bar(init_opts=opts.InitOpts(width="100%", height="420px"))
                        .add_xaxis(list(topics))
                        .add_yaxis(t['evo_series'], list(counts))
                        .set_global_opts(
                            title_opts=opts.TitleOpts(title=t['evo_title'].format(date=date)),
                            xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45)),
                            yaxis_opts=opts.AxisOpts(name=t['evo_yaxis']),
                            tooltip_opts=opts.TooltipOpts(trigger="axis")
                        )
                    )
                    
                    timeline.add(bar, str(date))
            
            # Timeline对象没有set_global_opts方法，直接渲染
            timeline.render(output_path)
            logger.info(f"话题演化时间线已保存到: {output_path}")
            
            return timeline
            
        except Exception as e:
            logger.error(f"创建话题演化时间线失败: {e}")
            # 创建一个简单的错误提示图表
            error_bar = (
                Bar(init_opts=opts.InitOpts(width="100%", height="420px"))
                .add_xaxis([t['evo_err_cat']])
                .add_yaxis(t['evo_err_series'], [1])
                .set_global_opts(
                    title_opts=opts.TitleOpts(title=t['evo_err_title']),
                    xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45))
                )
            )
            
            timeline = Timeline(init_opts=opts.InitOpts(width="100%", height="420px"))
            timeline.add(error_bar, t['evo_err_cat'])
            timeline.render(output_path)
            
            return timeline
    
    def create_comprehensive_dashboard(self, hotspot_results, df, propagation_results=None, langs=('zh', 'en')):
        """创建综合仪表板（默认同时生成中、英两套图表与页面）"""
        logger.info("生成综合可视化仪表板")

        # 创建传播网络图（无论是否有传播分析结果）
        propagation_graph = None
        if propagation_results and 'propagation_graph' in propagation_results:
            propagation_graph = propagation_results['propagation_graph']

        dashboard_path = None
        for lang in langs:
            # 创建各个图表（中文版沿用原文件名，英文版自动加 _en 后缀）
            self.create_hotspot_wordcloud(hotspot_results, lang=lang)
            self.create_hotspot_ranking_chart(hotspot_results, lang=lang)
            self.create_time_trend_chart(df, lang=lang)
            self.create_source_distribution_chart(df, lang=lang)
            self.create_engagement_top(df, lang=lang)
            self.create_propagation_network_chart(propagation_graph, lang=lang)
            self.create_topic_evolution_timeline(hotspot_results, df, lang=lang)

            # 创建HTML仪表板页面
            dashboard_html = self._create_dashboard_html(lang)

            filename = 'dashboard.html' if lang == 'zh' else f'dashboard_{lang}.html'
            path = os.path.join(self.output_dir, filename)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(dashboard_html)
            logger.info(f"综合仪表板({lang})已保存到: {path}")

            if lang == 'zh':
                dashboard_path = path

        return dashboard_path

    def _create_dashboard_html(self, lang='zh'):
        """创建仪表板HTML页面（iframe 引用同语言版本的图表文件）"""
        t = _T[lang]
        suffix = '' if lang == 'zh' else f'_{lang}'
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>__DASH_TITLE__</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }
                .header { text-align: center; margin-bottom: 30px; }
                .header h1 { color: #333; font-size: 2.5em; margin-bottom: 10px; }
                .header p { color: #666; font-size: 1.2em; }
                .dashboard { display: grid; grid-template-columns: repeat(auto-fit, minmax(500px, 1fr)); gap: 20px; }
                .chart-container { background: white; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); padding: 20px; }
                iframe { width: 100%; height: 400px; border: none; }
                .full-width { grid-column: 1 / -1; }
                .half-width { height: 300px; }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>__DASH_TITLE__</h1>
                <p>__DASH_SUB__</p>
            </div>

            <div class="dashboard">
                <div class="chart-container full-width">
                    <iframe src="hotspot_wordcloud__SUFFIX__.html"></iframe>
                </div>

                <div class="chart-container">
                    <iframe src="hotspot_ranking__SUFFIX__.html"></iframe>
                </div>

                <div class="chart-container">
                    <iframe src="time_trend__SUFFIX__.html"></iframe>
                </div>

                <div class="chart-container">
                    <iframe src="source_distribution__SUFFIX__.html"></iframe>
                </div>

                <div class="chart-container">
                    <iframe src="engagement_top__SUFFIX__.html"></iframe>
                </div>

                <div class="chart-container full-width">
                    <iframe src="propagation_network__SUFFIX__.html" style="height:580px;"></iframe>
                </div>

                <div class="chart-container full-width">
                    <iframe src="topic_evolution__SUFFIX__.html" style="height:440px;"></iframe>
                </div>
            </div>
        </body>
        </html>
        """

        return (html_template
                .replace('__DASH_TITLE__', t['dash_title'])
                .replace('__DASH_SUB__', t['dash_sub'])
                .replace('__SUFFIX__', suffix))

if __name__ == "__main__":
    # 测试可视化
    from database.db_manager import get_db_manager
    from preprocessing.text_processor import DataCleaner
    from mining.hotspot_miner import HotspotMiner
    
    # 获取和清洗数据
    cleaner = DataCleaner()
    df = cleaner.clean_database_data()
    
    if not df.empty:
        # 执行热点挖掘
        miner = HotspotMiner()
        hotspot_results = miner.mine_hotspots(df)
        
        # 创建可视化
        visualizer = NewsVisualizer()
        dashboard_path = visualizer.create_comprehensive_dashboard(hotspot_results, df)
        
        print(f"可视化仪表板已生成: {dashboard_path}")
        print("请在浏览器中打开查看可视化结果")
        
    else:
        print("没有数据可供可视化") 