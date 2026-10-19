# -*- coding: utf-8 -*-
"""
新闻爬虫模块 - 真正实现版本
"""

import requests
from bs4 import BeautifulSoup
import time
import random
import logging
from datetime import datetime, timedelta
import re
import hashlib
import json
import feedparser
from urllib.parse import urljoin, urlparse, quote
from config.settings import CRAWLER_CONFIG, NEWS_SOURCES
from database.db_manager import get_db_manager

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaseCrawler:
    """基础爬虫类"""
    
    def __init__(self, db_type='mysql'):
        self.config = CRAWLER_CONFIG
        self.session = requests.Session()
        self.db_manager = get_db_manager(db_type)
        self.setup_session()
    
    def setup_session(self):
        """设置会话"""
        headers = {
            'User-Agent': random.choice(self.config['user_agents']),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Cache-Control': 'max-age=0',
        }
        self.session.headers.update(headers)
    
    def get_page(self, url, **kwargs):
        """获取网页内容"""
        try:
            response = self.session.get(
                url,
                timeout=self.config['timeout'],
                **kwargs
            )
            response.raise_for_status()
            response.encoding = 'utf-8'
            return response
            
        except Exception as e:
            logger.error(f"获取页面失败: {url}, 错误: {e}")
            return None
    
    def extract_text(self, element):
        """提取文本内容"""
        if element:
            text = element.get_text(strip=True)
            # 清理文本
            text = re.sub(r'\s+', ' ', text)
            text = re.sub(r'[^\w\s\u4e00-\u9fff，。！？；：""''（）【】《》]', '', text)
            return text.strip()
        return ""
    
    def extract_publish_time(self, text_content, soup=None):
        """提取发布时间"""
        time_patterns = [
            r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})',
            r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})',
            r'(\d{4}年\d{1,2}月\d{1,2}日\s*\d{1,2}:\d{2})',
            r'(\d{4}年\d{1,2}月\d{1,2}日)',
            r'(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2})',
            r'(\d{4}/\d{2}/\d{2})',
        ]
        
        # 先从soup中查找特定的时间元素
        if soup:
            time_selectors = [
                '.time', '.date', '.pub-time', '.publish-time',
                '[class*="time"]', '[class*="date"]', 
                'time', '.article-time', '.news-time'
            ]
            
            for selector in time_selectors:
                time_elem = soup.select_one(selector)
                if time_elem:
                    time_text = self.extract_text(time_elem)
                    if time_text:
                        text_content = time_text + " " + text_content
                        break
        
        for pattern in time_patterns:
            match = re.search(pattern, text_content)
            if match:
                time_str = match.group(1)
                try:
                    if '年' in time_str and '月' in time_str:
                        if ':' in time_str:
                            return datetime.strptime(time_str, '%Y年%m月%d日 %H:%M')
                        else:
                            return datetime.strptime(time_str, '%Y年%m月%d日')
                    elif '/' in time_str:
                        if ':' in time_str:
                            return datetime.strptime(time_str, '%Y/%m/%d %H:%M')
                        else:
                            return datetime.strptime(time_str, '%Y/%m/%d')
                    elif ':' in time_str:
                        if len(time_str) > 16:
                            return datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
                        else:
                            return datetime.strptime(time_str, '%Y-%m-%d %H:%M')
                    else:
                        return datetime.strptime(time_str, '%Y-%m-%d')
                except:
                    continue
        
        return None  # 时间解析失败时置空，不用采集时间冒充
    
    def generate_news_id(self, title, url):
        """生成新闻ID"""
        unique_string = f"{title}_{url}"
        return hashlib.md5(unique_string.encode('utf-8')).hexdigest()
    
    def save_news(self, news_data):
        """保存新闻数据"""
        try:
            # 检查必要字段
            if not news_data.get('title') or not news_data.get('content'):
                logger.warning("新闻数据缺少必要字段，跳过保存")
                return False
            
            # 去重检查
            news_id = self.generate_news_id(news_data['title'], news_data.get('url', ''))
            news_data['news_id'] = news_id
            
            self.db_manager.insert_news(news_data)
            return True
            
        except Exception as e:
            logger.error(f"保存新闻数据失败: {e}")
            return False
    
    def delay(self):
        """随机延时"""
        time.sleep(random.uniform(0.5, self.config['delay']))

class XinhuaCrawler(BaseCrawler):
    """新华网爬虫"""
    
    def __init__(self, db_type='mysql'):
        super().__init__(db_type)
        self.source_config = NEWS_SOURCES['xinhua']
    
    def crawl_news_list(self):
        """爬取新华网新闻列表"""
        try:
            # 首先尝试RSS源
            rss_url = self.source_config.get('rss_url')
            if rss_url:
                news_links = self.parse_rss_feed(rss_url)
                if news_links:
                    logger.info(f"从新华网RSS获取到 {len(news_links)} 条新闻")
                    return news_links
            
            # RSS失败，尝试网页抓取
            return self.crawl_web_news_list()
            
        except Exception as e:
            logger.error(f"新华网新闻列表获取失败: {e}")
            return []
    
    def parse_rss_feed(self, rss_url):
        """解析RSS订阅源"""
        try:
            feed = feedparser.parse(rss_url)
            news_links = []
            
            for entry in feed.entries[:50]:  # 限制数量
                news_links.append({
                    'title': entry.title,
                    'url': entry.link,
                    'description': getattr(entry, 'description', ''),
                    'published': getattr(entry, 'published', '')
                })
            
            return news_links
            
        except Exception as e:
            logger.error(f"RSS解析失败: {e}")
            return []
    
    def crawl_web_news_list(self):
        """抓取网页新闻列表"""
        news_urls = [
            'http://www.news.cn/politics/',
            'http://www.news.cn/local/',
            'http://www.news.cn/finance/'
        ]
        
        all_news = []
        
        for url in news_urls:
            try:
                response = self.get_page(url)
                if not response:
                    continue
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 查找新闻链接
                news_selectors = [
                    'a[href*="/c_"]',  # 新华网文章链接模式
                    '.tit a', '.title a', '.news-title a',
                    'a[href*="xinhuanet.com"]'
                ]
                
                for selector in news_selectors:
                    links = soup.select(selector)
                    for link in links:
                        href = link.get('href')
                        title = self.extract_text(link)
                        
                        if href and title and len(title) > 10:
                            full_url = urljoin(self.source_config['base_url'], href)
                            if self.is_valid_news_url(full_url):
                                all_news.append({
                                    'title': title,
                                    'url': full_url
                                })
                
                self.delay()
                
            except Exception as e:
                logger.error(f"抓取新华网页面失败 {url}: {e}")
                continue
        
        # 去重
        seen_urls = set()
        unique_news = []
        for news in all_news:
            if news['url'] not in seen_urls:
                seen_urls.add(news['url'])
                unique_news.append(news)
        
        logger.info(f"从新华网网页获取到 {len(unique_news)} 条新闻")
        return unique_news[:50]  # 限制数量
    
    def is_valid_news_url(self, url):
        """判断是否为有效新闻URL"""
        invalid_patterns = [
            'javascript:', 'mailto:', '#', 'index.htm',
            'login', 'register', 'search', 'about', 'contact'
        ]
        
        for pattern in invalid_patterns:
            if pattern in url.lower():
                return False
        
        # 检查是否包含新闻特征
        news_patterns = ['/c_', '/politics/', '/local/', '/finance/']
        return any(pattern in url for pattern in news_patterns)
    
    def crawl_news_detail(self, news_item):
        """爬取新闻详情"""
        url = news_item['url']
        response = self.get_page(url)
        
        if not response:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        try:
            title = news_item['title']
            
            # 查找正文内容
            content_selectors = [
                '.article-content', '.content', '#content', 
                '.news-content', 'article', '.main-content',
                '.detail-content', '[class*="content"]'
            ]
            
            content = ""
            for selector in content_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    # 移除广告和无关元素
                    for unwanted in content_elem.select('script, style, .ad, .advertisement'):
                        unwanted.decompose()
                    
                    content = self.extract_text(content_elem)
                    if len(content) > 100:  # 确保内容足够长
                        break
            
            if not content:
                # 备用方案：查找段落
                paragraphs = soup.find_all('p')
                content_parts = []
                for p in paragraphs:
                    text = self.extract_text(p)
                    if len(text) > 20:  # 过滤太短的段落
                        content_parts.append(text)
                content = ' '.join(content_parts)
            
            if len(content) < 50:  # 内容太短
                logger.warning(f"新闻内容太短，跳过: {title}")
                return None
            
            # 提取发布时间
            publish_time = self.extract_publish_time(soup.get_text(), soup)
            
            # 提取作者
            author = self.extract_author(soup)
            
            news_data = {
                'title': title,
                'content': content,
                'source': self.source_config['name'],
                'author': author,
                'publish_time': publish_time,
                'url': url,
                                'comments_count': None,  # 无真实互动数据来源，缺失以 None 表示（禁止随机生成）
                'likes_count': None,
                'shares_count': None,
                'crawl_time': datetime.now(),
                'category': '政治',
                'tags': ''
            }
            
            return news_data
            
        except Exception as e:
            logger.error(f"解析新华网新闻详情失败: {url}, 错误: {e}")
            return None
    
    def extract_author(self, soup):
        """提取作者"""
        author_selectors = [
            '.author', '.by-author', '.news-author',
            '[class*="author"]', '[id*="author"]',
            '.source', '.editor'
        ]
        
        for selector in author_selectors:
            author_elem = soup.select_one(selector)
            if author_elem:
                author = self.extract_text(author_elem)
                if author and len(author) < 50:
                    return author
        
        return "新华网"
    
    def crawl(self, max_news=50):
        """执行爬取任务"""
        logger.info(f"开始爬取新华网新闻，目标: {max_news} 条")
        
        # 获取新闻列表
        news_list = self.crawl_news_list()
        
        if not news_list:
            logger.warning("未获取到新华网新闻列表")
            return 0
        
        crawled_count = 0
        for news_item in news_list[:max_news]:
            if crawled_count >= max_news:
                break
            
            # 爬取详情
            news_data = self.crawl_news_detail(news_item)
            
            if news_data and len(news_data['content']) > 100:
                if self.save_news(news_data):
                    crawled_count += 1
                    logger.info(f"已爬取: {crawled_count}/{max_news} - {news_data['title'][:50]}...")
            
            self.delay()
        
        logger.info(f"新华网爬取完成，共获取 {crawled_count} 条新闻")
        return crawled_count

class SinaCrawler(BaseCrawler):
    """新浪新闻爬虫"""
    
    def __init__(self, db_type='mysql'):
        super().__init__(db_type)
        self.source_config = NEWS_SOURCES['sina']
    
    def crawl(self, max_news=50):
        """新浪新闻爬取"""
        logger.info(f"开始爬取新浪新闻，目标: {max_news} 条")
        
        try:
            # 尝试RSS源
            rss_url = self.source_config.get('rss_url')
            if rss_url:
                news_list = self.parse_rss_feed(rss_url)
            else:
                news_list = []
            
            if not news_list:
                # RSS失败，尝试API
                news_list = self.crawl_sina_api()
            
            crawled_count = 0
            for news_item in news_list[:max_news]:
                if crawled_count >= max_news:
                    break
                
                news_data = self.process_sina_news(news_item)
                if news_data and self.save_news(news_data):
                    crawled_count += 1
                    logger.info(f"已爬取: {crawled_count}/{max_news} - {news_data['title'][:50]}...")
                
                self.delay()
            
            logger.info(f"新浪新闻爬取完成，共获取 {crawled_count} 条新闻")
            return crawled_count
            
        except Exception as e:
            logger.error(f"新浪新闻爬取失败: {e}")
            return 0
    
    def parse_rss_feed(self, rss_url):
        """解析RSS订阅源"""
        try:
            feed = feedparser.parse(rss_url)
            news_links = []
            
            for entry in feed.entries[:50]:
                news_links.append({
                    'title': entry.title,
                    'url': entry.link,
                    'description': getattr(entry, 'description', ''),
                    'published': getattr(entry, 'published', '')
                })
            
            return news_links
            
        except Exception as e:
            logger.error(f"新浪RSS解析失败: {e}")
            return []
    
    def crawl_sina_api(self):
        """通过新浪API获取新闻"""
        try:
            # 新浪新闻接口（简化版）
            api_url = "https://interface.sina.cn/news/wap/fymap_data.d.html"
            params = {
                'col': 'news',
                'level': '1,2',
                'show_num': '50'
            }
            
            response = self.get_page(api_url, params=params)
            if response:
                data = response.json()
                news_list = []
                
                if 'result' in data and 'data' in data['result']:
                    for item in data['result']['data']:
                        news_list.append({
                            'title': item.get('title', ''),
                            'url': item.get('url', ''),
                            'description': item.get('intro', ''),
                            'published': item.get('ctime', '')
                        })
                
                return news_list
                
        except Exception as e:
            logger.error(f"新浪API调用失败: {e}")
            
        return []
    
    def process_sina_news(self, news_item):
        """处理新浪新闻数据"""
        try:
            title = news_item.get('title', '')
            url = news_item.get('url', '')
            content = news_item.get('description', '')
            
            if not title or len(title) < 10:
                return None
            
            # 如果有URL，尝试获取完整内容
            if url and len(content) < 100:
                detailed_content = self.get_detailed_content(url)
                if detailed_content:
                    content = detailed_content
            
            # 处理发布时间
            published = news_item.get('published', '')
            if published:
                publish_time = self.parse_time_string(published)
            else:
                publish_time = None  # 无法获取真实发布时间时置空，不用采集时间冒充
            
            news_data = {
                'title': title,
                'content': content,
                'source': self.source_config['name'],
                'author': '新浪新闻',
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
            logger.error(f"处理新浪新闻失败: {e}")
            return None
    
    def get_detailed_content(self, url):
        """获取详细内容"""
        try:
            response = self.get_page(url)
            if response:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                content_selectors = [
                    '.article-content', '.content', '#artibody',
                    '.news-content', 'article'
                ]
                
                for selector in content_selectors:
                    content_elem = soup.select_one(selector)
                    if content_elem:
                        return self.extract_text(content_elem)
                        
        except Exception as e:
            logger.error(f"获取详细内容失败: {e}")
            
        return None
    
    def parse_time_string(self, time_str):
        """解析时间字符串"""
        try:
            # 尝试多种时间格式
            formats = [
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d %H:%M',
                '%Y-%m-%d',
                '%a, %d %b %Y %H:%M:%S %Z'
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(time_str, fmt)
                except:
                    continue
                    
        except Exception as e:
            logger.error(f"时间解析失败: {e}")
            
        return None  # 时间解析失败时置空

class NeteaseCrawler(BaseCrawler):
    """网易新闻爬虫"""
    
    def __init__(self, db_type='mysql'):
        super().__init__(db_type)
        self.source_config = NEWS_SOURCES['netease']
    
    def crawl(self, max_news=50):
        """网易新闻爬取"""
        logger.info(f"开始爬取网易新闻，目标: {max_news} 条")
        
        try:
            # 网易新闻API
            api_url = "https://3g.163.com/touch/reconstruct/article/list/BBM54PGAwangning/0-20.html"
            
            response = self.get_page(api_url)
            crawled_count = 0
            
            if response:
                # 尝试解析JSON响应
                try:
                    # 网易接口返回的是包装在JS中的JSON
                    text = response.text
                    json_start = text.find('{')
                    json_end = text.rfind('}') + 1
                    
                    if json_start >= 0 and json_end > json_start:
                        json_text = text[json_start:json_end]
                        data = json.loads(json_text)
                        
                        if 'BBM54PGAwangning' in data:
                            news_list = data['BBM54PGAwangning']
                            
                            for item in news_list[:max_news]:
                                news_data = self.process_netease_news(item)
                                if news_data and self.save_news(news_data):
                                    crawled_count += 1
                                    logger.info(f"已爬取: {crawled_count}/{max_news} - {news_data['title'][:50]}...")
                                
                                self.delay()
                
                except Exception as e:
                    logger.error(f"网易新闻JSON解析失败: {e}")
            
            logger.info(f"网易新闻爬取完成，共获取 {crawled_count} 条新闻")
            return crawled_count
            
        except Exception as e:
            logger.error(f"网易新闻爬取失败: {e}")
            return 0
    
    def process_netease_news(self, item):
        """处理网易新闻数据"""
        try:
            title = item.get('title', '')
            url = item.get('url', '')
            digest = item.get('digest', '')
            
            if not title or len(title) < 10:
                return None
            
            # 获取详细内容
            content = digest
            if url:
                detailed_content = self.get_netease_content(url)
                if detailed_content and len(detailed_content) > len(content):
                    content = detailed_content
            
            # 处理时间
            ptime = item.get('ptime', '')
            if ptime:
                publish_time = datetime.strptime(ptime, '%Y-%m-%d %H:%M:%S')
            else:
                publish_time = None  # 无法获取真实发布时间时置空
            
            news_data = {
                'title': title,
                'content': content,
                'source': self.source_config['name'],
                'author': item.get('source', '网易新闻'),
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
            logger.error(f"处理网易新闻失败: {e}")
            return None
    
    def get_netease_content(self, url):
        """获取网易新闻详细内容"""
        try:
            response = self.get_page(url)
            if response:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                content_selectors = [
                    '.post_content_main', '.post_body', '.content',
                    '#endText', '.article-content'
                ]
                
                for selector in content_selectors:
                    content_elem = soup.select_one(selector)
                    if content_elem:
                        return self.extract_text(content_elem)
                        
        except Exception as e:
            logger.error(f"获取网易详细内容失败: {e}")
            
        return None

class PeopleCrawler(BaseCrawler):
    """人民网爬虫"""
    
    def __init__(self, db_type='mysql'):
        super().__init__(db_type)
        self.source_config = NEWS_SOURCES['people']
    
    def crawl(self, max_news=50):
        """人民网爬取"""
        logger.info(f"开始爬取人民网新闻，目标: {max_news} 条")
        
        try:
            # 尝试RSS源（主源 + 备用源）
            news_list = []
            
            rss_urls = [self.source_config.get('rss_url')] + self.source_config.get('rss_backup_urls', [])
            for rss_url in rss_urls:
                if not rss_url:
                    continue
                feed = feedparser.parse(rss_url)
                for entry in feed.entries[:max_news - len(news_list)]:
                    news_list.append({
                        'title': entry.title,
                        'url': entry.link,
                        'description': getattr(entry, 'description', ''),
                        'published': getattr(entry, 'published', '')
                    })
                if len(news_list) >= max_news:
                    break
            
            if not news_list:
                # 所有RSS都失败，使用网页抓取
                logger.warning("人民网RSS源均无数据，尝试网页抓取")
                news_list = self.crawl_people_web()
            
            crawled_count = 0
            for news_item in news_list[:max_news]:
                if crawled_count >= max_news:
                    break
                
                news_data = self.process_people_news(news_item)
                if news_data and self.save_news(news_data):
                    crawled_count += 1
                    logger.info(f"已爬取: {crawled_count}/{max_news} - {news_data['title'][:50]}...")
                
                self.delay()
            
            logger.info(f"人民网爬取完成，共获取 {crawled_count} 条新闻")
            return crawled_count
            
        except Exception as e:
            logger.error(f"人民网爬取失败: {e}")
            return 0
    
    def crawl_people_web(self):
        """抓取人民网网页"""
        try:
            response = self.get_page(self.source_config['news_list_url'])
            if not response:
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            news_list = []
            
            # 查找新闻链接
            links = soup.select('a[href*="people.com.cn"]')
            for link in links:
                href = link.get('href')
                title = self.extract_text(link)
                
                if href and title and len(title) > 10:
                    news_list.append({
                        'title': title,
                        'url': href,
                        'description': '',
                        'published': ''
                    })
            
            return news_list[:50]
            
        except Exception as e:
            logger.error(f"人民网网页抓取失败: {e}")
            return []
    
    def process_people_news(self, news_item):
        """处理人民网新闻"""
        try:
            title = news_item.get('title', '')
            url = news_item.get('url', '')
            content = news_item.get('description', '')
            
            if not title or len(title) < 10:
                return None
            
            # 获取详细内容
            if url and len(content) < 100:
                detailed_content = self.get_people_content(url)
                if detailed_content:
                    content = detailed_content
            
            news_data = {
                'title': title,
                'content': content or '暂无详细内容',
                'source': self.source_config['name'],
                'author': '人民网',
                'publish_time': None,  # 人民网列表无真实发布时间，置空而非采集时间
                'url': url,
                                'comments_count': None,  # 无真实互动数据来源，缺失以 None 表示（禁止随机生成）
                'likes_count': None,
                'shares_count': None,
                'crawl_time': datetime.now(),
                'category': '政治',
                'tags': ''
            }
            
            return news_data
            
        except Exception as e:
            logger.error(f"处理人民网新闻失败: {e}")
            return None
    
    def get_people_content(self, url):
        """获取人民网详细内容"""
        try:
            response = self.get_page(url)
            if response:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                content_selectors = [
                    '.rm_txt_con', '.box_con', '.article_box',
                    '.content', '#rwb_zw'
                ]
                
                for selector in content_selectors:
                    content_elem = soup.select_one(selector)
                    if content_elem:
                        return self.extract_text(content_elem)
                        
        except Exception as e:
            logger.error(f"获取人民网详细内容失败: {e}")
            
        return None

class NewsScheduler:
    """新闻采集调度器"""
    
    def __init__(self, db_type='mysql'):
        self.crawlers = {
            'xinhua': XinhuaCrawler(db_type),
            'sina': SinaCrawler(db_type),
            'netease': NeteaseCrawler(db_type),
            'people': PeopleCrawler(db_type)
        }
    
    def crawl_all_sources(self, max_news_per_source=50):
        """爬取所有新闻源"""
        logger.info("开始执行全量新闻爬取任务")
        
        total_crawled = 0
        
        for source_name, crawler in self.crawlers.items():
            try:
                logger.info(f"开始爬取 {source_name}")
                crawled_count = crawler.crawl(max_news_per_source)
                total_crawled += crawled_count
                
                # 每个源之间稍作休息
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"爬取 {source_name} 失败: {e}")
        
        logger.info(f"全量新闻爬取任务完成，共获取 {total_crawled} 条新闻")
        return total_crawled
    
    def run_scheduled_crawl(self):
        """定时爬取任务"""
        import schedule
        
        # 每15分钟执行一次爬取
        schedule.every(CRAWLER_CONFIG['crawl_frequency']).minutes.do(
            self.crawl_all_sources, max_news_per_source=20
        )
        
        logger.info(f"定时爬取任务已启动，频率: 每 {CRAWLER_CONFIG['crawl_frequency']} 分钟")
        
        while True:
            schedule.run_pending()
            time.sleep(60)

if __name__ == "__main__":
    # 测试爬虫
    from crawler.api_crawler import APIScheduler
    
    # 首先尝试网页爬虫
    web_scheduler = NewsScheduler()
    web_total = web_scheduler.crawl_all_sources(max_news_per_source=20)
    print(f"网页爬虫完成，共爬取 {web_total} 条新闻")
    
    # 然后使用API爬虫作为补充
    api_scheduler = APIScheduler()
    api_total = api_scheduler.crawl_all_apis(max_news_per_api=15)
    print(f"API爬虫完成，共爬取 {api_total} 条新闻")
    
    print(f"总计爬取 {web_total + api_total} 条新闻") 