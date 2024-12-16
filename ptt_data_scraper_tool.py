"""
主題：PTT 網頁爬蟲程式
"""
# -*- coding: utf-8 -*-
import time
import pandas as pd
import urllib
import datetime
import collections
import json
import random
import requests
from bs4 import BeautifulSoup



# exception自定義例外類別，用於處理程式中的特定錯誤

class Error(Exception):
    """所有自定義例外的基類"""
    pass


class InValidBeautifulSoupTag(Error):
    """無效的 BeautifulSoup 標籤，無法建立 ArticleSummary"""
    pass


class NoGivenURLForPage(Error):
    """未提供有效的 URL，無法建立頁面"""
    pass


class PageNotFound(Error):
    """無法通過給定的 URL 獲取頁面"""
    pass


class ArtitcleIsRemoved(Error):
    """文章已被移除，無法讀取"""
    pass


# utility實用工具函數
def parse_std_url(url):
    """
    解析 PTT 標準網址
    範例：
    >>> parse_std_url('https://www.ptt.cc/bbs/Gossiping/M.1512057611.A.16B.html')
    ('https://www.ptt.cc/bbs', 'Gossiping', 'M.1512057611.A.16B')
    """
    prefix, _, basename = url.rpartition('/')
    basename, _, _ = basename.rpartition('.')
    bbs, _, board = prefix.rpartition('/')
    bbs = bbs[1:]
    return bbs, board, basename


def parse_title(title):
    """
    解析文章標題以提取相關資訊
    範例：
    >>> parse_title('Re: [問卦] 睡覺到底可不可以穿襪子')
    ('問卦', True, False)
    """
    _, _, remain = title.partition('[')
    category, _, remain = remain.rpartition(']')
    category = category if category else None
    isreply = True if 'Re:' in title else False
    isforward = True if 'Fw:' in title else False
    return category, isreply, isforward


def parse_username(full_name):
    """
    解析使用者名稱，提取帳號和暱稱
    範例：
    >>> parse_username('seabox (歐陽盒盒)')
    ('seabox', '歐陽盒盒')
    """
    name, nickname = full_name.split(' (')
    nickname = nickname.rstrip(')')
    return name, nickname


# Msg is a namedtuple which used to model the info of one of the pushes使用 namedtuple 建模推文訊息的結構
Msg = collections.namedtuple('Msg', ['type', 'user', 'content', 'ipdatetime'])


class ArticleSummary:
    """用於建模文章列表頁中每篇文章的摘要資訊"""

    def __init__(self, title, url, score, date, author, mark, removeinfo):
        # title標題
        self.title = title
        self.category, self.isreply, self.isforward = parse_title(title)

        # url網址
        self.url = url
        _, self.board, self.aid = parse_std_url(url)

        # meta元數據
        self.score = score
        self.date = date
        self.author = author
        self.mark = mark

        # remove移除標記
        self.isremoved = True if removeinfo else False
        self.removeinfo = removeinfo

    @classmethod
    def from_bs_tag(cls, tag):
        """根據 BeautifulSoup 標籤建立 ArticleSummary 物件"""
        try:
            removeinfo = None
            title_tag = tag.find('div', class_='title')
            a_tag = title_tag.find('a')

            if not a_tag:
                removeinfo = title_tag.get_text().strip()

            if not removeinfo: 
                title = a_tag.get_text().strip()
                url = a_tag.get('href').strip()
                score = tag.find('div', class_='nrec').get_text().strip()
            else:
                title = '本文章已被刪除'
                url = ''
                score = ''

            date = tag.find('div', class_='date').get_text().strip()
            author = tag.find('div', class_='author').get_text().strip()
            mark = tag.find('div', class_='mark').get_text().strip()
        except Exception:
            raise InValidBeautifulSoupTag(tag)

        return cls(title, url, score, date, author, mark, removeinfo)

    def __repr__(self):
        return '<Summary of Article("{}")>'.format(self.url)

    def __str__(self):
        return self.title

    def read(self):
        """讀取文章內容並返回 ArticlePage 物件
        如果文章已被刪除，則拋出 ArtitcleIsRemoved 錯誤
        """
        if self.isremoved:
            raise ArtitcleIsRemoved(self.removeinfo)
        return ArticlePage(self.url)


class Page:
    """頁面的基類，負責通過 URL 獲取網頁內容"""
    ptt_domain = 'https://www.ptt.cc'

    def __init__(self, url):
        if not url:
            raise NoGivenURLForPage

        self.url = url

        url = urllib.parse.urljoin(self.ptt_domain, self.url)
        resp = requests.get(url=url, cookies={'over18': '1'}, verify=True, timeout=3)

        if resp.status_code == requests.codes.ok:
            self.html = resp.text
        else:
            raise PageNotFound


class ArticleListPage(Page):
    """用於建模文章列表頁的類別"""

    def __init__(self, url):
        super().__init__(url)

        # to set article_tags設置文章標籤
        soup = BeautifulSoup(self.html, 'lxml')
        self.article_summary_tags = soup.find_all('div', 'r-ent')
        self.article_summary_tags.reverse()

        # to set related urls設置相關頁面網址
        action_tags = soup.find('div', class_='action-bar').find_all('a')
        self.related_urls = {}
        url_names = 'board man oldest previous next newest'
        for idx, name in enumerate(url_names.split()):
            self.related_urls[name] = action_tags[idx].get('href')

        # to set board and idx設置看板名稱和索引
        _, self.board, basename = parse_std_url(url)
        _, _, idx = basename.partition('index')
        if idx:
            self.idx = int(idx)
        else:
            _, self.board, basename = parse_std_url(self.related_urls['previous'])
            _, _, idx = basename.partition('index')
            self.idx = int(idx) + 1

    @classmethod
    def from_board(cls, board, index=''):
        """根據看板名稱和索引建立 ArticleListPage 物件"""
        url = '/'.join(['/bbs', board, 'index' + str(index) + '.html'])
        return cls(url)

    def __repr__(self):
        return 'ArticleListPage("{}")'.format(self.url)

    def __iter__(self):
        return self.article_summaries

    def get_article_summary(self, index):
        return ArticleSummary.from_bs_tag(self.article_summary_tags[index])

    @property
    def article_summaries(self):
        return (ArticleSummary.from_bs_tag(tag) for tag in self.article_summary_tags)

    @property
    def previous(self):
        return ArticleListPage(self.related_urls['previous'])

    @property
    def next(self):
        return ArticleListPage(self.related_urls['next'])

    @property
    def oldest(self):
        return ArticleListPage(self.related_urls['oldest'])

    @property
    def newest(self):
        return ArticleListPage(self.related_urls['newest'])


class ArticlePage(Page):
    """用於建模文章詳情頁的類別"""

    default_attrs = ['board', 'aid', 'author', 'date', 'content', 'ip']
    default_csv_attrs = default_attrs + ['pushes.count.score']
    default_json_attrs = default_attrs + ['pushes.count', 'pushes.simple_expression']

    def __init__(self, url):
        super().__init__(url)

        _, _, self.aid = parse_std_url(url)

        # to set article_tags設置文章標籤
        soup = BeautifulSoup(self.html, 'lxml')
        main_tag = soup.find('div', id='main-content')
        meta_value_tags = main_tag.find_all('span', class_='article-meta-value')


        # dealing meta處理元數據
        try:
            self.author = meta_value_tags[0].get_text().strip()
            self.board = meta_value_tags[1].get_text().strip()
            self.title = meta_value_tags[2].get_text().strip()
            self.date = meta_value_tags[3].get_text().strip()

            self.category, self.isreply, self.isforward = parse_title(self.title)
            self.datetime = datetime.datetime.strptime(self.date, '%a %b %d %H:%M:%S %Y')
        except:
            self.author, self.board, self.title, self.date = '', '', '', ''
            self.category, self.isreply, self.isforward = '', False, False
            self.datetime = None

        # remove meta移除元數據
        for tag in main_tag.select('div.article-metaline'):
            tag.extract()
        for tag in main_tag.select('div.article-metaline-right'):
            tag.extract()

        # fetch pushes and remove them提取推文並移除推文區域
        self.pushes = Pushes(self)
        push_tags = main_tag.find_all('div', class_='push')
        for tag in push_tags:
            tag.extract()
        for tag in push_tags:
            if not tag.find('span', 'push-tag'):
                continue
            push_type = tag.find('span', class_='push-tag').string.strip(' \t\n\r')
            push_user = tag.find('span', class_='push-userid').string.strip(' \t\n\r')
            push_content = tag.find('span', class_='push-content').strings
            push_content = ' '.join(push_content)[1:].strip(' \t\n\r')
            push_ipdatetime = tag.find('span', class_='push-ipdatetime').string.strip(' \t\n\r')
            msg = Msg(type=push_type, user=push_user, content=push_content, ipdatetime=push_ipdatetime)
            self.pushes.addmsg(msg)
        self.pushes.countit()

        # handle special item處理特殊項目
        ip_tags = main_tag.find_all('span', class_='f2')
        dic = {}
        for tag in ip_tags:
            if '※' in tag.get_text():
                key, _, value = tag.get_text().partition(':')
                key = key.strip('※').strip()
                value = value.strip()
                if '引述' in key:
                    continue
                else:
                    dic.setdefault(key, []).append(value)
                    tag.extract()
        self.ip = dic['發信站'][0].split()[-1]

        # remove richcontent移除多媒體內容
        for tag in main_tag.find_all('div', class_='richcontent'):
            tag.extract()

        # handle trans處理轉錄資訊
        trans = []
        for tag in main_tag.find_all('span', class_='f2'):
            if '轉錄至看板' in tag.get_text():
                trans.append(tag.previous_element.parent)
                trans.append(tag.get_text())
                trans.append(tag.next_sibling)
                tag.previous_element.parent.extract()
                tag.next_sibling.extract()
                tag.extract()

        # split main content and signature拆分主要內容與簽名檔
        self.content, self.signature = str(main_tag).split('--')[:2]
        self.content = self.content.strip()

        contents = self.content.split('\n')
        self.content = '\n'.join(content for content in contents if not ('<div' in content and 'main-content' in content))

        contents = self.signature.split('\n')
        self.signature = '\n'.join(content for content in contents if not ('</div' in content))

    @classmethod
    def from_board_aid(cls, board, aid):
        url = '/'.join(['/bbs', board, aid+'.html'])
        return cls(url)

    def __repr__(self):
        return 'ArticlePage("{}")'.format(self.url)

    def __str__(self):
        return self.title

    @classmethod
    def _recur_getattr(cls, obj, attr):
        if not '.' in attr:
            try:
                return getattr(obj, attr)
            except:
                return obj[attr]
        attr1, _, attr2 = attr.partition('.')
        obj = cls._recur_getattr(obj, attr1)
        return cls._recur_getattr(obj, attr2)

    def dump_json(self, *attrs, flat=True):
        """dump json string of this article with specified attrs"""
        data = {}
        if not attrs:
            attrs = self.default_json_attrs
        for attr in attrs:
            data[attr] = self._recur_getattr(self, attr)
        if flat:
            return json.dumps(data, ensure_ascii=False)
        else:
            return json.dumps(data, indent=4, ensure_ascii=False)

    def dump_csv(self, *attrs, delimiter=','):
        """dump csv string of this article with specified attrs"""
        cols = []
        if not attrs:
            attrs = self.default_csv_attrs
        for attr in attrs:
            cols.append(self._recur_getattr(self, attr))
        cols = [repr(col) if '\n' in str(col) else str(col) for col in cols]
        return delimiter.join(cols)


class Pushes:
    """class used to model all pushes of an article"""

    def __init__(self, article):
        self.article = article
        self.msgs = []
        self.count = 0

    def __repr__(self):
        return 'Pushes({})'.format(repr(self.article))

    def __str__(self):
        return 'Pushes of Article {}'.format(self.Article)

    def addmsg(self, msg):
        self.msgs.append(msg)

    def countit(self):
        count_types = 'all abs like boo neutral'.split()
        self.count = dict(zip(count_types, [0, 0, 0, 0, 0]))
        for msg in self.msgs:
            if msg.type == '推':
                self.count['like'] += 1
            elif msg.type == '噓':
                self.count['boo'] += 1
            else:
                self.count['neutral'] += 1

        self.count['all'] = self.count['like'] + self.count['boo'] + self.count['neutral']
        self.count['score'] = self.count['like'] - self.count['boo']

    @property
    def simple_expression(self):
        msgs = []
        attrs = ['type', 'user', 'content', 'ipdatetime']
        for msg in self.msgs:
            msgs.append(dict(zip(attrs, list(msg))))
        return msgs


def ptt_crawl(Board_Name, start, page):
    Board = ArticleListPage.from_board
    # 抓該板首頁的文章
    latest_page = Board(Board_Name, start-page)

    # 抓取資料
    ptt_aid = []
    ptt_author = []
    ptt_board = []
    ptt_category = []
    ptt_title = []
    ptt_content = []
    ptt_url = []
    ptt_date = []
    ptt_ip = []
    ptt_all = []
    ptt_boo = []
    ptt_like = []
    ptt_neutral = []
    ptt_score = []
    ptt_comment = []

    for summary in latest_page: # 只要抓最新的頁面
        if summary.isremoved:
            continue
       
        print('正在抓資料中...'+summary.title)
        time.sleep(random.randint(1,3))
        try:
            article = summary.read()
            # 將所有內容儲存在一個[]
            ptt_aid.append( article.aid)
            ptt_author.append( article.author)
            ptt_board.append( article.board)
            ptt_category.append( article.category)
            ptt_title.append( article.title)
            ptt_content.append( article.content)
            ptt_url.append( article.url)
            ptt_date.append( article.date)
            ptt_ip.append( article.ip)
            ptt_all.append( article.pushes.count['all'])
            ptt_boo.append( article.pushes.count['boo'])
            ptt_like.append( article.pushes.count['like'])
            ptt_neutral.append( article.pushes.count['neutral'])
            ptt_score.append( article.pushes.count['score'])
            ptt_comment.append( article.pushes.simple_expression)
            
        except:
            pass
        
    # 將結果做成df
    dic = {
       '文章編碼':ptt_aid,
        '作者':ptt_author,
        '版名':ptt_board,
        '分類':ptt_category,
        '標題':ptt_title,
        '內文':ptt_content,
        '日期':ptt_date,
        'IP位置':ptt_ip,
        '總留言數':ptt_all,
        '噓':ptt_boo,
        '推':ptt_like,
        '中立':ptt_neutral,
        '文章分數（正-負）':ptt_score,
        '所有留言':ptt_comment
       }
    final_data = pd.DataFrame(dic)
    # 去除空白的標題
    final_data = final_data[final_data['標題'] !='']
    return final_data

def crawl_ptt_page(Board_Name ='Gossiping' , start ='' ,page_num= 5):
    tStart = time.time()#計時開始
    listt = []
    if start.isdigit():
        start = int(start)
    else:
        index = ArticleListPage('https://www.ptt.cc/bbs/'+Board_Name+'/index.html').previous.url
        start = int(index[index.find('index')+5:index.find('.html')])+1

    for i in range(page_num):
        listt.append(ptt_crawl(Board_Name= Board_Name, start=start , page = i))
    listtdf = pd.concat(listt)
    listtdf.to_csv(Board_Name + '.csv',encoding = 'utf-8') #存檔
    tEnd = time.time()#計時結束
    print('資料儲存完成，花費時間（約）： ' + str(int(tEnd - tStart)) + ' 秒。')
    
    return listtdf

def main():
    print('\n請輸入您想爬的板名（英文）：')
    Board_Name = input() 
    
    print('\n請輸入您想從第幾頁開始爬：')
    start = input()
    
    print('\n請輸入您想爬幾頁：')
    page_num = int(input())
    
    crawl_ptt_page(Board_Name =Board_Name , start =start ,page_num= page_num)
    



if __name__ == '__main__':
    main()