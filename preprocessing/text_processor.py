# -*- coding: utf-8 -*-
"""
文本预处理模块
"""

import re
import jieba
import pandas as pd
import numpy as np
from collections import Counter
import logging
from datetime import datetime
from config.settings import TEXT_PROCESSING_CONFIG
from database.db_manager import get_db_manager

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 新闻正文常见无意义模板词组（图片说明、编辑/转载标注、APP导流语等）。
# 仅匹配高置信度模板文本；"图为"按短句整体截除（至首个分句符，上限40字），
# 标题中正常词（如"举报电话"）不受影响——"举报/反馈"仅在成对出现时去除。
NOISE_PATTERNS = [
    re.compile(r"图为[^，。；！？\n]{0,40}[，。；！？]?"),
    re.compile(r"图片来源[:：][^，。；！？\n]{0,40}"),
    re.compile(r"原标题[:：][^\n]{0,80}"),
    re.compile(r"原题[:：][^\n]{0,80}"),
    re.compile(r"【?责任编辑[:：][^\】\n]{0,20}】?"),
    re.compile(r"(?<![主小副总])编辑[:：][^\s，。；！？\n]{1,15}"),
    re.compile(r"来源[:：][^，。；！？\n]{1,25}"),
    re.compile(r"点击进入专题[^\n]{0,40}"),
    re.compile(r"免责声明[:：]?[^\n]{0,100}"),
    re.compile(r"海量资讯、精准解读[^。！？\n]{0,40}[。！？]?"),
    re.compile(r"(下载|打开)[^，。；！？\n]{0,10}APP[^，。；！？\n]{0,30}"),
    re.compile(r"（?本文(?:来自|转载于|首发于)[^）\n]{0,50}）?"),
    re.compile(r"【?纠错】?"),
    re.compile(r"举报/反馈"),
]


def remove_noise_phrases(text):
    """去除新闻文本中无意义模板词组，返回 (清洗后文本, 命中数)。"""
    if not text or not isinstance(text, str):
        return text, 0
    hits = 0
    for pat in NOISE_PATTERNS:
        text, k = pat.subn("", text)
        hits += k
    return text, hits


class TextProcessor:
    """文本预处理器"""
    
    def __init__(self):
        self.config = TEXT_PROCESSING_CONFIG
        self._stopwords = None  # 惰性加载：停用词文件在 setup_environment 中才重建，需保证用时取最新
        self.setup_jieba()

    @property
    def stopwords(self):
        if self._stopwords is None:
            self._stopwords = self.load_stopwords()
        return self._stopwords
    
    def load_stopwords(self):
        """加载停用词"""
        try:
            with open(self.config['stopwords_file'], 'r', encoding='utf-8') as f:
                stopwords = set(line.strip() for line in f if line.strip())
            logger.info(f"加载停用词 {len(stopwords)} 个")
            return stopwords
        except FileNotFoundError:
            logger.warning("停用词文件不存在，使用默认停用词")
            return self.get_default_stopwords()
    
    def get_default_stopwords(self):
        """获取默认停用词"""
        default_stopwords = {
            '的', '了', '在', '是', '我', '有', '和', '就', '不', '人',
            '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去',
            '你', '会', '着', '没有', '看', '好', '自己', '这', '那', '他',
            '她', '它', '我们', '你们', '他们', '这个', '那个', '什么', '怎么',
            '为什么', '因为', '所以', '但是', '可以', '应该', '或者', '如果',
            '虽然', '然而', '而且', '以及', '对于', '关于', '通过', '根据'
        }
        return default_stopwords
    
    def setup_jieba(self):
        """设置jieba分词"""
        try:
            # 加载自定义词典
            if hasattr(self.config, 'jieba_dict_file'):
                jieba.load_userdict(self.config['jieba_dict_file'])
                logger.info("加载自定义词典成功")
        except:
            logger.warning("自定义词典加载失败，使用默认词典")
        
        # 添加常用词汇
        custom_words = [
            '新冠肺炎', '疫情防控', '经济发展', '民生改善',
            '科技创新', '绿色发展', '数字化转型', '人工智能'
        ]
        
        for word in custom_words:
            jieba.add_word(word)
    
    def clean_text(self, text):
        """清洗文本"""
        if not text or not isinstance(text, str):
            return ""
        
        # 去除HTML标签
        text = re.sub(r'<[^>]+>', '', text)

        # 去除无意义模板词组（图为/编辑标注/导流语等）
        text, _ = remove_noise_phrases(text)

        # 去除特殊字符，保留中文、英文、数字和常用标点
        text = re.sub(r'[^\w\s\u4e00-\u9fff，。！？；：""''（）【】《》\-\+\*\/\=]', '', text)
        
        # 去除多余空白字符
        text = re.sub(r'\s+', ' ', text)
        
        # 去除过短或过长的文本
        if len(text) < self.config['min_text_length'] or len(text) > self.config['max_text_length']:
            return ""
        
        return text.strip()
    
    def segment_text(self, text):
        """分词"""
        if not text:
            return []
        
        # 使用jieba分词
        words = jieba.lcut(text)
        
        # 过滤停用词和无效词
        filtered_words = []
        for word in words:
            word = word.strip()
            if (len(word) > 1 and 
                word not in self.stopwords and
                not word.isdigit() and
                not re.match(r'^[a-zA-Z]+$', word)):
                filtered_words.append(word)
        
        return filtered_words
    
    def extract_keywords(self, text, top_k=10):
        """提取关键词"""
        import jieba.analyse

        # 使用TF-IDF提取关键词（多取一倍再按停用词过滤，保证结果数足够）
        keywords = jieba.analyse.extract_tags(text, topK=top_k * 2, withWeight=True)
        keywords = [(w, s) for w, s in keywords if w not in self.stopwords][:top_k]

        return keywords
    
    def remove_duplicates(self, df, columns=['title', 'content']):
        """去重"""
        logger.info(f"去重前数据量: {len(df)}")
        
        # 基于标题和内容去重
        df_clean = df.drop_duplicates(subset=columns, keep='first')
        
        logger.info(f"去重后数据量: {len(df_clean)}")
        logger.info(f"删除重复数据: {len(df) - len(df_clean)} 条")
        
        return df_clean
    
    def handle_missing_values(self, df):
        """处理缺失值"""
        logger.info("开始处理缺失值")
        
        # 检查缺失值
        missing_info = df.isnull().sum()
        logger.info(f"缺失值统计:\n{missing_info}")
        
        # 删除关键字段缺失的记录
        critical_columns = ['title', 'content']
        for col in critical_columns:
            if col in df.columns:
                df = df.dropna(subset=[col])
        
        # 填充其他字段的缺失值
        # 注意：comments/likes/shares 不填充——缺失(NaN)表示未知，不得用 0 冒充真实零值
        fill_values = {
            'author': '未知',
            'category': '未分类',
            'tags': ''
        }
        
        for col, value in fill_values.items():
            if col in df.columns:
                df[col] = df[col].fillna(value)
        
        # 时间字段：仅做类型统一，缺失保持 NaT（不用当前时间冒充真实发布时间）
        if 'publish_time' in df.columns:
            df['publish_time'] = pd.to_datetime(df['publish_time'], errors='coerce')
        
        logger.info(f"缺失值处理完成，剩余数据: {len(df)} 条")
        return df
    
    def detect_outliers(self, df, columns=['comments_count', 'likes_count', 'shares_count']):
        """检测异常值"""
        logger.info("开始检测异常值")
        
        outliers_info = {}
        
        for col in columns:
            if col in df.columns and df[col].dtype in ['int64', 'float64']:
                if df[col].notna().sum() == 0:
                    logger.info(f"{col} 全部缺失，跳过异常值检测")
                    continue
                Q1 = df[col].quantile(0.25)
                Q3 = df[col].quantile(0.75)
                IQR = Q3 - Q1
                
                lower_bound = Q1 - 1.5 * IQR
                upper_bound = Q3 + 1.5 * IQR
                
                outliers = df[(df[col] < lower_bound) | (df[col] > upper_bound)]
                outliers_info[col] = len(outliers)
                
                logger.info(f"{col} 异常值数量: {len(outliers)}")
        
        return outliers_info
    
    def process_batch(self, df):
        """批量处理数据"""
        logger.info(f"开始批量处理数据，原始数据量: {len(df)}")
        
        # 1. 处理缺失值
        df = self.handle_missing_values(df)
        
        # 2. 清洗文本
        logger.info("开始清洗文本数据")
        noise_hits = int(df['content'].fillna('').astype(str).str.count(
            '图为|图片来源|原标题|原题|责任编辑|点击进入专题|免责声明|举报/反馈|来源[:：]|编辑[:：]').sum())
        if noise_hits:
            logger.info(f"将去除模板词组（图为/编辑标注/导流语等），共命中 {noise_hits} 处")
        df['title_clean'] = df['title'].apply(self.clean_text)
        df['content_clean'] = df['content'].apply(self.clean_text)
        
        # 3. 过滤无效数据
        df = df[(df['title_clean'] != '') & (df['content_clean'] != '')]
        
        # 4. 去重
        df = self.remove_duplicates(df, ['title_clean', 'content_clean'])
        
        # 5. 文本分词
        logger.info("开始文本分词")
        df['title_words'] = df['title_clean'].apply(self.segment_text)
        df['content_words'] = df['content_clean'].apply(self.segment_text)
        
        # 6. 提取关键词
        logger.info("开始提取关键词")
        df['keywords'] = df['content_clean'].apply(
            lambda x: [kw[0] for kw in self.extract_keywords(x, top_k=10)]
        )
        
        # 7. 计算文本长度
        df['title_length'] = df['title_clean'].str.len()
        df['content_length'] = df['content_clean'].str.len()
        df['word_count'] = df['content_words'].apply(len)
        
        # 8. 检测异常值
        self.detect_outliers(df)
        
        logger.info(f"批量处理完成，最终数据量: {len(df)}")
        
        return df


def apply_engagement_provenance(df, manifest_path='data/reports/engagement_provenance.json'):
    """按外部数据质量清单将"未知/未验证"互动字段置为 NaN（fail-closed）。

    规则：crawl_time <= cutoff_time 的历史记录，凡字段未显式标记 verified_real，
    一律置 NaN（不修改数据库，仅作用于内存分析数据流）；清单不存在时原样返回。
    """
    import json, os
    if not os.path.exists(manifest_path):
        return df
    try:
        with open(manifest_path, encoding='utf-8') as f:
            manifest = json.load(f)
        cutoff = pd.Timestamp(manifest.get('cutoff_time'))
        field_map = {r['news_id']: r.get('fields', {}) for r in manifest.get('records', [])}
        eng_cols = ['comments_count', 'likes_count', 'shares_count']
        ct = pd.to_datetime(df['crawl_time'], errors='coerce')
        mask_old = ct <= cutoff
        n_affected = 0
        for idx in df.index[mask_old.fillna(False)]:
            fields = field_map.get(df.at[idx, 'news_id'], {})
            for col in eng_cols:
                if col in df.columns and fields.get(col, {}).get('status') != 'verified_real':
                    if pd.notna(df.at[idx, col]):
                        df.at[idx, col] = np.nan
                        n_affected += 1
        logger.info(f"互动数据质量清单已应用：{int(mask_old.sum())} 条历史记录，{n_affected} 个字段置为缺失")
    except Exception as e:
        logger.error(f"加载互动数据质量清单失败（保守处理：历史互动全部置缺失）: {e}")
        ct = pd.to_datetime(df['crawl_time'], errors='coerce')
        df.loc[ct.notna(), ['comments_count', 'likes_count', 'shares_count']] = np.nan
    return df

def apply_analysis_window(df, days=30):
    """分析时间窗口过滤：仅保留近 days 天的记录（days<=0 时不过滤）。

    publish_time 已知按发布时间判断；publish_time 缺失的记录按 crawl_time 判断
    窗口归属（仅用于过滤，不填充发布时间字段本身，统计中单独披露）。
    返回 (过滤后df, 统计dict)，调用方应如实披露统计信息。
    """
    stats = {'enabled': bool(days and days > 0), 'days': days}
    if not stats['enabled'] or len(df) == 0:
        return df, stats
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=days)
    pt = pd.to_datetime(df['publish_time'], errors='coerce')
    if 'crawl_time' in df.columns:
        ct = pd.to_datetime(df['crawl_time'], errors='coerce')
    else:
        ct = pd.Series(pd.NaT, index=df.index)
    in_pt = pt >= cutoff
    fallback = pt.isna() & (ct >= cutoff)
    keep = in_pt | fallback
    stats.update({
        'cutoff': str(cutoff),
        'before': int(len(df)),
        'after': int(keep.sum()),
        'by_publish_time': int(in_pt.sum()),
        'by_crawl_time_fallback': int(fallback.sum()),
        'excluded': int((~keep).sum()),
    })
    logger.info(
        f"分析时间窗口: 近{days}天（>= {cutoff.date()}），{stats['before']} -> {stats['after']} 条"
        f"（其中 {stats['by_crawl_time_fallback']} 条发布时间缺失、按采集时间判断归属；"
        f"排除 {stats['excluded']} 条）"
    )
    return df[keep].copy(), stats

class DataCleaner:
    """数据清洗器"""
    
    def __init__(self, db_type='mysql'):
        self.db_manager = get_db_manager(db_type)
        self.text_processor = TextProcessor()
    
    def clean_database_data(self):
        """清洗数据库中的数据"""
        try:
            # 从数据库获取数据
            logger.info("从数据库获取原始数据")
            df = self.db_manager.get_all_news_df()
            
            if df.empty:
                logger.warning("数据库中没有数据")
                return pd.DataFrame()
            
            # 应用互动数据质量清单：历史未知互动在内存中置为缺失（不修改数据库）
            df = apply_engagement_provenance(df)

            # 处理数据
            df_processed = self.text_processor.process_batch(df)
            
            # 保存处理后的数据（可以保存到新表或更新原表）
            logger.info("数据清洗完成")
            
            return df_processed
            
        except Exception as e:
            logger.error(f"数据清洗失败: {e}")
            raise
    
    def export_cleaned_data(self, df, output_path='data/cleaned_news.csv'):
        """导出清洗后的数据"""
        try:
            df.to_csv(output_path, index=False, encoding='utf-8')
            logger.info(f"清洗后的数据已导出到: {output_path}")
            
        except Exception as e:
            logger.error(f"数据导出失败: {e}")

def create_stopwords_file():
    """创建停用词文件（通用虚词 + 新闻领域泛指词）"""
    stopwords = [
        '的', '了', '在', '是', '我', '有', '和', '就', '不', '人',
        '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去',
        '你', '会', '着', '没有', '看', '好', '自己', '这', '那', '他',
        '她', '它', '我们', '你们', '他们', '这个', '那个', '什么', '怎么',
        '为什么', '因为', '所以', '但是', '可以', '应该', '或者', '如果',
        '虽然', '然而', '而且', '以及', '对于', '关于', '通过', '根据',
        '同时', '另外', '此外', '总之', '首先', '其次', '最后', '然后',
        '接着', '于是', '因此', '由于', '鉴于', '考虑到', '基于', '根据',
        # ---- 新闻领域泛指词：高频但无话题区分度，不删正文、仅挖掘时过滤 ----
        # 人物泛指（如"男子偷电瓶"换任何主体都不变话题）
        '男子', '女子', '男孩', '女孩', '老人', '市民', '网友', '司机',
        '乘客', '家长', '人员', '一名', '一位',
        # 媒体流程词（每条新闻都带）
        '记者', '报道', '新闻', '消息', '视频', '图片', '通讯员',
        '中新社', '中新网', '日电', '网讯', '责编', '原标题',
        # 时间泛指
        '近日', '今日', '昨日', '昨天', '今天', '目前', '当天', '日前',
        '近期', '上午', '下午',
        # 泛义动词/名词（任何题材都可能出现）
        '发生', '引发', '表示', '认为', '指出', '进行', '出现', '成为',
        '发现', '介绍', '提醒', '透露', '回应', '强调', '带来', '提供',
        '情况', '问题', '相关', '有关', '方面', '内容', '服务', '支持',
        '及时', '工作', '已经', '正在',
        # ---- 敏感词：按用户要求在数据处理时剔除，仅作用于分词/关键词层，不删正文 ----
        # 低俗色情类
        '色情', '情色', '裸体', '情妇', '情夫', '小三', '出轨', '偷情',
        '屁股', '胸部', '性感', '美女', '性爱', '嫖娼', '卖淫', '包养',
        '开房', '床照', '艳照', '走光',
        # 辱骂攻击类
        '傻逼', '煞笔', '废物', '垃圾', '贱人', '婊子', '王八蛋', '混蛋',
        '滚蛋', '白痴', '智障', '脑残', '变态', '畜牲', '狗屁', '他妈的',
        '草泥马', '尼玛', '卧槽',
        # 负面伤亡类
        '死亡', '身亡', '遇难', '罹难', '惨死', '致死', '丧生', '自杀',
        '自焚', '遇害', '被害', '谋杀', '命案', '尸体', '血腥', '惨剧',
        '坠亡', '溺亡', '烧死',
        # 政治人物类（国内外政治人物姓名及职务称谓）
        '习近平', '李克强', '李强', '王沪宁', '赵乐际', '蔡奇', '丁薛祥',
        '李希', '韩正', '王岐山', '胡锦涛', '江泽民', '毛泽东', '邓小平',
        '特朗普', '拜登', '普京', '泽连斯基', '金正恩', '蔡英文', '赖清德',
        '马英九', '总书记', '国家主席', '总统', '总理', '首相', '委员长',
        '元首',
    ]
    
    import os
    os.makedirs('data', exist_ok=True)
    
    with open('data/stopwords.txt', 'w', encoding='utf-8') as f:
        for word in stopwords:
            f.write(word + '\n')
    
    logger.info("停用词文件创建完成")

if __name__ == "__main__":
    # 创建停用词文件
    create_stopwords_file()
    
    # 测试数据清洗
    cleaner = DataCleaner()
    cleaned_data = cleaner.clean_database_data()
    
    if not cleaned_data.empty:
        cleaner.export_cleaned_data(cleaned_data) 