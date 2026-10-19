# -*- coding: utf-8 -*-
"""
API爬虫模块 - 使用免费API获取新闻数据
"""

import requests
import json
import logging
from datetime import datetime, timedelta
import time
import random
import hashlib
from database.db_manager import get_db_manager

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class APICrawler:
    """API爬虫基类"""
    
    def __init__(self, db_type='mysql'):
        self.db_manager = get_db_manager(db_type)
        self.session = requests.Session()
        self.setup_session()
    
    def setup_session(self):
        """设置会话"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
        self.session.headers.update(headers)
    
    def get_api_data(self, url, params=None, **kwargs):
        """获取API数据"""
        try:
            response = self.session.get(url, params=params, timeout=30, **kwargs)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"API请求失败: {url}, 错误: {e}")
            return None
    
    def save_news(self, news_data):
        """保存新闻数据"""
        try:
            if not news_data.get('title') or not news_data.get('content'):
                return False
            
            self.db_manager.insert_news(news_data)
            return True
        except Exception as e:
            logger.error(f"保存新闻失败: {e}")
            return False
    
    def delay(self):
        """延时"""
        time.sleep(random.uniform(0.5, 2))
    
    def generate_news_id(self, title, source, publish_time):
        """生成唯一的新闻ID"""
        # 使用标题、来源和时间生成MD5哈希作为唯一ID
        content = f"{title}_{source}_{publish_time}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()[:16]

class ToutiaoAPICrawler(APICrawler):
    """今日头条API爬虫（免费接口）"""
    
    def __init__(self, db_type='mysql'):
        super().__init__(db_type)
        self.source_name = "今日头条"
    
    def crawl(self, max_news=50):
        """爬取今日头条新闻"""
        logger.info(f"开始通过API爬取今日头条新闻，目标: {max_news} 条")
        
        try:
            # 今日头条真实API接口
            api_urls = [
                {
                    'url': 'https://www.toutiao.com/api/pc/list/feed',
                    'params': {
                        'category': 'news_hot',
                        'utm_source': 'toutiao',
                        'widen': 1,
                        'max_behot_time': 0,
                        'max_behot_time_tmp': 0,
                        'tadrequire': True,
                        'as': 'A1A5B',
                        'cp': 'E1F5D'
                    }
                },
                {
                    'url': 'https://is.snssdk.com/api/news/feed/v88/',
                    'params': {
                        'category': 'news',
                        'count': 20,
                        'device_platform': 'webapp',
                        'aid': 24
                    }
                }
            ]
            
            crawled_count = 0
            
            for api_config in api_urls:
                if crawled_count >= max_news:
                    break
                
                try:
                    response = self.session.get(
                        api_config['url'], 
                        params=api_config['params'],
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        try:
                            data = response.json()
                        except:
                            # 有些接口可能返回JSONP格式
                            text = response.text
                            if 'callback(' in text:
                                json_start = text.find('{')
                                json_end = text.rfind('}') + 1
                                if json_start >= 0 and json_end > json_start:
                                    data = json.loads(text[json_start:json_end])
                                else:
                                    continue
                            else:
                                continue
                        
                        if 'data' in data:
                            news_list = data['data']
                            if not isinstance(news_list, list) or not news_list:
                                logger.warning(f"API返回的data为空或非列表，跳过本次")
                                continue
                            for item in news_list[:max_news-crawled_count]:
                                news_data = self.process_toutiao_item(item)
                                if news_data and self.save_news(news_data):
                                    crawled_count += 1
                                    logger.info(f"已爬取: {crawled_count}/{max_news} - {news_data['title'][:50]}...")
                                    
                                self.delay()
                        else:
                            logger.warning(f"API响应无data字段，跳过本次接口")
                
                except Exception as e:
                    logger.error(f"今日头条API调用失败: {e}")
                    continue
            
            # 如果API失败，使用备用方案
            if crawled_count == 0:
                logger.info("API接口无响应，尝试备用数据源...")
                crawled_count = self.crawl_toutiao_backup(max_news)
            
            logger.info(f"今日头条API爬取完成，共获取 {crawled_count} 条新闻")
            return crawled_count
            
        except Exception as e:
            logger.error(f"今日头条API爬取失败: {e}")
            return 0
    
    def crawl_toutiao_backup(self, max_news):
        """备用今日头条数据获取方案"""
        try:
            # 使用今日头条移动端接口
            backup_urls = [
                'https://m.toutiao.com/list/?tag=news_hot&ac=wap&count=20&format=json_raw',
                'https://m.toutiao.com/list/?tag=news_finance&ac=wap&count=20&format=json_raw'
            ]
            
            crawled_count = 0
            
            for url in backup_urls:
                if crawled_count >= max_news:
                    break
                
                try:
                    response = self.session.get(url, timeout=30)
                    if response.status_code == 200:
                        data = response.json()
                        
                        if 'data' in data and isinstance(data['data'], list) and data['data']:
                            for item in data['data'][:max_news-crawled_count]:
                                news_data = self.process_toutiao_backup_item(item)
                                if news_data and self.save_news(news_data):
                                    crawled_count += 1
                                    logger.info(f"已爬取: {crawled_count}/{max_news} - {news_data['title'][:50]}...")
                                
                                self.delay()
                
                except Exception as e:
                    logger.error(f"备用接口调用失败: {e}")
                    continue
            
            return crawled_count
            
        except Exception as e:
            logger.error(f"备用方案失败: {e}")
            return 0
    
    def process_toutiao_backup_item(self, item):
        """处理备用接口的数据"""
        try:
            title = item.get('title', '')
            abstract = item.get('abstract', item.get('summary', ''))
            
            if not title or len(title) < 10:
                return None
            
            news_data = {
                'title': title,
                'content': abstract or title,
                'source': self.source_name,
                'author': item.get('media_name', '今日头条'),
                'publish_time': None,  # 备用数据无真实发布时间，置空（原为随机时间，已禁止）
                'url': item.get('article_url', item.get('url', '')),
                'comments_count': item.get('comment_count'),  # 无字段时缺失(None)，不再随机兜底
                'likes_count': item.get('digg_count'),
                'shares_count': item.get('share_count'),
                'crawl_time': datetime.now(),
                'category': item.get('category', '综合'),
                'tags': ','.join(item.get('keywords', []))
            }
            
            return news_data
            
        except Exception as e:
            logger.error(f"处理备用数据失败: {e}")
            return None
    
    def process_toutiao_item(self, item):
        """处理今日头条数据项"""
        try:
            title = item.get('title', '')
            abstract = item.get('abstract', '')
            
            if not title or len(title) < 10:
                return None
            
            # 处理发布时间
            publish_time_ts = item.get('publish_time', 0)
            if publish_time_ts:
                publish_time = datetime.fromtimestamp(publish_time_ts)
            else:
                publish_time = None  # 无真实发布时间时置空
            
            news_data = {
                'title': title,
                'content': abstract or '暂无详细内容',
                'source': self.source_name,
                'author': item.get('media_name', '今日头条'),
                'publish_time': publish_time,
                'url': item.get('article_url', ''),
                'comments_count': item.get('comment_count'),  # 缺失以 None 表示，不用 0 冒充真实零值
                'likes_count': item.get('digg_count'),
                'shares_count': item.get('share_count'),
                'crawl_time': datetime.now(),
                'category': item.get('category', '综合'),
                'tags': ','.join(item.get('keywords', []))
            }
            
            return news_data
            
        except Exception as e:
            logger.error(f"处理今日头条数据失败: {e}")
            return None

class TencentNewsAPICrawler(APICrawler):
    """腾讯新闻API爬虫（免费接口）"""
    
    def __init__(self, db_type='mysql'):
        super().__init__(db_type)
        self.source_name = "腾讯新闻"
    
    def crawl(self, max_news=50):
        """爬取腾讯新闻"""
        logger.info(f"开始通过腾讯新闻API爬取新闻，目标: {max_news} 条")
        
        try:
            # 腾讯新闻公开API
            api_urls = [
                "https://pacaio.match.qq.com/irs/rcd?cid=146&token=d0f13d594edfc180f5bf6b845456f3ea",  # 国内新闻
                "https://pacaio.match.qq.com/irs/rcd?cid=139&token=d0f13d594edfc180f5bf6b845456f3ea",  # 财经新闻
                "https://pacaio.match.qq.com/irs/rcd?cid=132&token=d0f13d594edfc180f5bf6b845456f3ea"   # 科技新闻
            ]
            
            crawled_count = 0
            
            for api_url in api_urls:
                if crawled_count >= max_news:
                    break
                
                try:
                    response = self.session.get(api_url, timeout=30)
                    if response.status_code == 200:
                        data = response.json()
                        
                        if 'data' in data and isinstance(data['data'], list) and data['data']:
                            news_list = data['data']
                            
                            for item in news_list[:max_news-crawled_count]:
                                news_data = self.process_tencent_news(item)
                                if news_data and self.save_news(news_data):
                                    crawled_count += 1
                                    logger.info(f"已爬取: {crawled_count}/{max_news} - {news_data['title'][:50]}...")
                                
                                self.delay()
                
                except Exception as e:
                    logger.error(f"腾讯新闻API调用失败: {e}")
                    continue
            
            logger.info(f"腾讯新闻API爬取完成，共获取 {crawled_count} 条新闻")
            return crawled_count
            
        except Exception as e:
            logger.error(f"腾讯新闻API爬取失败: {e}")
            return 0
    
    def process_tencent_news(self, item):
        """处理腾讯新闻数据"""
        try:
            title = item.get('title', '')
            abstract = item.get('abstract', '')
            
            if not title or len(title) < 10:
                return None
            
            # 处理发布时间
            pub_time = item.get('pub_time', '')
            if pub_time:
                try:
                    publish_time = datetime.fromtimestamp(int(pub_time))
                except:
                    publish_time = None  # 解析失败置空
            else:
                publish_time = None  # 无真实发布时间时置空
            
            news_data = {
                'title': title,
                'content': abstract or title,
                'source': self.source_name,
                'author': item.get('source', '腾讯新闻'),
                'publish_time': publish_time,
                'url': item.get('url', ''),
                'comments_count': None,  # 腾讯接口无真实互动字段，缺失以 None 表示（禁止随机生成）
                'likes_count': None,
                'shares_count': None,
                'crawl_time': datetime.now(),
                'category': item.get('category', '综合'),
                'tags': ''
            }
            
            return news_data
            
        except Exception as e:
            logger.error(f"处理腾讯新闻数据失败: {e}")
            return None
    


class CNNewsAPICrawler(APICrawler):
    """中新网API爬虫"""
    
    def __init__(self, db_type='mysql'):
        super().__init__(db_type)
        self.source_name = "中国新闻网"
    
    def crawl(self, max_news=50):
        """爬取中新网新闻"""
        logger.info(f"开始爬取中新网新闻，目标: {max_news} 条")
        
        try:
            # 中新网真实API接口
            api_urls = [
                "http://www.chinanews.com/scroll-news/news1.html",
                "http://app.chinanews.com.cn/news/index/20",  # 移动端接口
                "https://m.chinanews.com/wap/detail/zwzx/gn.shtml"  # 国内新闻
            ]
            
            crawled_count = 0
            
            # 首先尝试通过RSS获取
            rss_count = self.crawl_chinanews_rss(max_news // 2)
            crawled_count += rss_count
            
            # 然后尝试网页抓取
            if crawled_count < max_news:
                web_count = self.crawl_chinanews_web(max_news - crawled_count)
                crawled_count += web_count
            
            logger.info(f"中新网爬取完成，共获取 {crawled_count} 条新闻")
            return crawled_count
            
        except Exception as e:
            logger.error(f"中新网爬取失败: {e}")
            return 0
    
    def crawl_chinanews_rss(self, max_news):
        """通过RSS获取中新网新闻"""
        try:
            import feedparser
            
            rss_urls = [
                "http://www.chinanews.com/rss/scroll-news.xml",
                "http://www.chinanews.com/rss/gn.xml",
                "http://www.chinanews.com/rss/cj.xml"
            ]
            
            crawled_count = 0
            
            for rss_url in rss_urls:
                if crawled_count >= max_news:
                    break
                
                try:
                    feed = feedparser.parse(rss_url)
                    
                    for entry in feed.entries[:max_news-crawled_count]:
                        news_data = self.process_chinanews_rss_item(entry)
                        if news_data and self.save_news(news_data):
                            crawled_count += 1
                            logger.info(f"已爬取: {crawled_count}/{max_news} - {news_data['title'][:50]}...")
                        
                        self.delay()
                
                except Exception as e:
                    logger.error(f"中新网RSS解析失败 {rss_url}: {e}")
                    continue
            
            return crawled_count
            
        except Exception as e:
            logger.error(f"中新网RSS爬取失败: {e}")
            return 0
    
    def crawl_chinanews_web(self, max_news):
        """通过网页抓取中新网新闻"""
        try:
            from bs4 import BeautifulSoup
            
            web_urls = [
                "http://www.chinanews.com/scroll-news/news1.html",
                "http://www.chinanews.com/gn/",
                "http://www.chinanews.com/cj/"
            ]
            
            crawled_count = 0
            
            for url in web_urls:
                if crawled_count >= max_news:
                    break
                
                try:
                    response = self.session.get(url, timeout=30)
                    if response.status_code == 200:
                        response.encoding = 'utf-8'
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # 查找新闻链接
                        news_links = soup.select('a[href*="/gn/"], a[href*="/cj/"], a[href*="/sh/"]')
                        
                        for link in news_links[:max_news-crawled_count]:
                            if crawled_count >= max_news:
                                break
                            
                            href = link.get('href')
                            title = link.get_text(strip=True)
                            
                            if href and title and len(title) > 10:
                                if not href.startswith('http'):
                                    href = 'http://www.chinanews.com' + href
                                
                                news_data = {
                                    'title': title,
                                    'content': self.get_chinanews_content(href) or title,
                                    'source': self.source_name,
                                    'author': '中国新闻网',
                                    'publish_time': None,  # 列表页无真实发布时间，置空（原为随机时间，已禁止）
                                    'url': href,
                                    'comments_count': None,  # 无真实互动数据来源，缺失以 None 表示（禁止随机生成）
                                    'likes_count': None,
                                    'shares_count': None,
                                    'crawl_time': datetime.now(),
                                    'category': '综合',
                                    'tags': ''
                                }
                                
                                if self.save_news(news_data):
                                    crawled_count += 1
                                    logger.info(f"已爬取: {crawled_count}/{max_news} - {news_data['title'][:50]}...")
                            
                            self.delay()
                
                except Exception as e:
                    logger.error(f"中新网网页抓取失败 {url}: {e}")
                    continue
            
            return crawled_count
            
        except Exception as e:
            logger.error(f"中新网网页爬取失败: {e}")
            return 0
    
    def process_chinanews_rss_item(self, entry):
        """处理中新网RSS条目"""
        try:
            title = entry.title
            content = getattr(entry, 'description', '') or getattr(entry, 'summary', '') or title
            url = entry.link
            
            if not title or len(title) < 10:
                return None
            
            # 处理发布时间
            published = getattr(entry, 'published', '')
            if published:
                try:
                    import email.utils
                    pub_time = email.utils.parsedate_tz(published)
                    if pub_time:
                        publish_time = datetime.fromtimestamp(email.utils.mktime_tz(pub_time))
                    else:
                        publish_time = None  # 解析失败置空
                except:
                    publish_time = None  # 解析失败置空
            else:
                publish_time = None  # 无真实发布时间时置空
            
            news_data = {
                'news_id': self.generate_news_id(title, self.source_name, publish_time),
                'title': title,
                'content': content,
                'source': self.source_name,
                'author': '中国新闻网',
                'publish_time': publish_time,
                'url': url,
                'comments_count': None,  # 无真实互动数据来源，缺失以 None 表示（禁止随机生成）
                'likes_count': None,
                'shares_count': None,
                'crawl_time': datetime.now(),
                'category': '综合',
                'tags': ''
            }
            
            return news_data
            
        except Exception as e:
            logger.error(f"处理中新网RSS条目失败: {e}")
            return None
    
    def get_chinanews_content(self, url):
        """获取中新网文章内容"""
        try:
            response = self.session.get(url, timeout=30)
            if response.status_code == 200:
                from bs4 import BeautifulSoup
                response.encoding = 'utf-8'
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 查找文章内容
                content_selectors = [
                    '.left_zw', '.content', '#content', 
                    '.article-content', '.news-content'
                ]
                
                for selector in content_selectors:
                    content_elem = soup.select_one(selector)
                    if content_elem:
                        # 移除广告和脚本
                        for unwanted in content_elem.select('script, style, .ad'):
                            unwanted.decompose()
                        
                        content = content_elem.get_text(strip=True)
                        if len(content) > 50:
                            return content
                
                return None
                
        except Exception as e:
            logger.error(f"获取中新网内容失败: {e}")
            return None
    


class NeteaseNewsAPICrawler(APICrawler):
    """网易新闻API爬虫（真实接口）"""
    
    def __init__(self, db_type='mysql'):
        super().__init__(db_type)
        self.source_name = "网易新闻API"
    
    def crawl(self, max_news=50):
        """爬取网易新闻"""
        logger.info(f"开始通过网易新闻API爬取新闻，目标: {max_news} 条")
        
        try:
            # 网易新闻公开API接口
            api_urls = [
                "https://3g.163.com/touch/reconstruct/article/list/BBM54PGAwangning/0-20.html",  # 国内新闻
                "https://3g.163.com/touch/reconstruct/article/list/BA8EE5GMwangning/0-20.html",   # 财经新闻
                "https://3g.163.com/touch/reconstruct/article/list/BA8D4A3Rwangning/0-20.html"    # 科技新闻
            ]
            
            crawled_count = 0
            
            for api_url in api_urls:
                if crawled_count >= max_news:
                    break
                
                try:
                    response = self.session.get(api_url, timeout=30)
                    if response.status_code == 200:
                        # 网易接口返回的是包装在JS中的JSON
                        text = response.text
                        json_start = text.find('{')
                        json_end = text.rfind('}') + 1
                        
                        if json_start >= 0 and json_end > json_start:
                            json_text = text[json_start:json_end]
                            data = json.loads(json_text)
                            
                            # 获取新闻列表，根据不同接口的数据结构
                            news_list = []
                            for key, value in data.items():
                                if isinstance(value, list) and value:
                                    news_list = value
                                    break
                            
                            for item in news_list[:max_news-crawled_count]:
                                news_data = self.process_netease_api_item(item)
                                if news_data and self.save_news(news_data):
                                    crawled_count += 1
                                    logger.info(f"已爬取: {crawled_count}/{max_news} - {news_data['title'][:50]}...")
                                
                                self.delay()
                
                except Exception as e:
                    logger.error(f"网易新闻API调用失败: {e}")
                    continue
            
            logger.info(f"网易新闻API爬取完成，共获取 {crawled_count} 条新闻")
            return crawled_count
            
        except Exception as e:
            logger.error(f"网易新闻API爬取失败: {e}")
            return 0
    
    def process_netease_api_item(self, item):
        """处理网易新闻API数据"""
        try:
            title = item.get('title', '')
            digest = item.get('digest', '')
            url = item.get('url', '')
            
            if not title or len(title) < 10:
                return None
            
            # 处理发布时间
            ptime = item.get('ptime', '')
            if ptime:
                try:
                    publish_time = datetime.strptime(ptime, '%Y-%m-%d %H:%M:%S')
                except:
                    publish_time = None  # 解析失败置空
            else:
                publish_time = None  # 无真实发布时间时置空
            
            news_data = {
                'news_id': self.generate_news_id(title, self.source_name, publish_time),
                'title': title,
                'content': digest or title,
                'source': self.source_name,
                'author': item.get('source', '网易新闻'),
                'publish_time': publish_time,
                'url': url,
                'comments_count': item.get('replyCount'),  # 仅当响应含 replyCount 时取真实值，缺失为 None（不再随机兜底；字段真实性待核验）
                'likes_count': None,  # 接口无真实点赞字段，缺失以 None 表示（禁止随机生成）
                'shares_count': None,
                'crawl_time': datetime.now(),
                'category': '综合',
                'tags': ''
            }
            
            return news_data
            
        except Exception as e:
            logger.error(f"处理网易新闻API数据失败: {e}")
            return None

class BilibiliNewsAPICrawler(APICrawler):
    """哔哩哔哩资讯区爬虫（公开 API，含真实互动指标）

    数据性质（如实披露）：
      - 内容：B 站"资讯"分区（rid=202）最新视频资讯，子分区以"社会"为主，
        属于视频形态的社会新闻/热点资讯，含自媒体内容，非传统图文新闻。
      - 互动指标：stat.reply / stat.like / stat.share 为接口直接返回的真实值
        （含真实的 0），经 view API 抽查口径一致（2026-10-17 验证），禁止篡改。
      - 时间偏差：newlist 按最新发布排序，样本均为发布 24 小时内的内容，
        互动量处于积累初期，数值偏小属正常，分析时应注明该口径。
    """

    def __init__(self, db_type='mysql'):
        super().__init__(db_type)
        self.source_name = "哔哩哔哩资讯"

    def crawl(self, max_news=50):
        logger.info(f"开始通过API爬取哔哩哔哩资讯，目标: {max_news} 条")
        news_list = []
        try:
            session = requests.Session()
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
                'Referer': 'https://www.bilibili.com'
            }
            # 先访问主站获取 buvid3 cookie，否则 API 返回风控错误码 -352
            session.get('https://www.bilibili.com', headers=headers, timeout=15)

            page = 1
            while len(news_list) < max_news and page <= 3:
                resp = session.get(
                    'https://api.bilibili.com/x/web-interface/newlist',
                    params={'ps': 50, 'rid': 202, 'pn': page},
                    headers=headers, timeout=15
                )
                data = resp.json()
                if data.get('code') != 0:
                    logger.error(f"B站资讯API返回错误码: {data.get('code')} {data.get('message')}")
                    break

                for item in data.get('data', {}).get('archives', []):
                    if len(news_list) >= max_news:
                        break
                    news_data = self._parse_item(item)
                    if news_data:
                        news_list.append(news_data)

                page += 1
                time.sleep(1)

            saved_count = 0
            for news_data in news_list:
                if self.save_news(news_data):
                    saved_count += 1

            logger.info(f"哔哩哔哩资讯爬取完成，保存 {saved_count} 条")
            return saved_count

        except Exception as e:
            logger.error(f"爬取哔哩哔哩资讯失败: {e}")
            return 0

    def _parse_item(self, item):
        try:
            title = (item.get('title') or '').strip()
            desc = (item.get('desc') or '').strip()
            bvid = item.get('bvid')
            if not title or not bvid:
                return None

            stat = item.get('stat') or {}
            return {
                'news_id': f"bili_{bvid}",
                'title': title,
                'content': desc if desc else title,  # 简介为空时用标题兜底（save_news 要求 content 非空）
                'source': self.source_name,
                'author': (item.get('owner') or {}).get('name', ''),
                'publish_time': datetime.fromtimestamp(item['pubdate']) if item.get('pubdate') else None,
                'url': f"https://www.bilibili.com/video/{bvid}",
                # 接口直接返回的真实互动值（含真实的 0，0 是实测值而非缺失）
                'comments_count': stat.get('reply'),
                'likes_count': stat.get('like'),
                'shares_count': stat.get('share'),
                'crawl_time': datetime.now(),
                'category': item.get('tname', '资讯'),
                'tags': item.get('tname', '')
            }
        except Exception as e:
            logger.error(f"处理B站资讯数据失败: {e}")
            return None

class APIScheduler:
    """API爬虫调度器"""
    
    def __init__(self, db_type='mysql'):
        self.crawlers = {
            'toutiao_api': ToutiaoAPICrawler(db_type),
            'tencent_api': TencentNewsAPICrawler(db_type),
            'netease_api': NeteaseNewsAPICrawler(db_type),
            'chinanews_api': CNNewsAPICrawler(db_type),
            'bilibili_api': BilibiliNewsAPICrawler(db_type)
        }
    
    def crawl_all_apis(self, max_news_per_api=30):
        """爬取所有API源"""
        logger.info("开始执行API新闻爬取任务")
        
        total_crawled = 0
        
        for api_name, crawler in self.crawlers.items():
            try:
                logger.info(f"开始爬取 {api_name}")
                crawled_count = crawler.crawl(max_news_per_api)
                total_crawled += crawled_count
                
                time.sleep(3)  # API之间休息
                
            except Exception as e:
                logger.error(f"爬取 {api_name} 失败: {e}")
        
        logger.info(f"API新闻爬取任务完成，共获取 {total_crawled} 条新闻")
        return total_crawled

if __name__ == "__main__":
    # 测试API爬虫
    scheduler = APIScheduler()
    total = scheduler.crawl_all_apis(max_news_per_api=20)
    print(f"API爬虫测试完成，共爬取 {total} 条新闻") 