import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import time
import progressbar


class PTTScraper:
    base_url = "https://www.ptt.cc"

    def __init__(self, _board):
        self.base_url = PTTScraper.base_url
        self.url = self.base_url + f"/bbs/{_board}/index.html"

    def get_post_content(self, post_url):
        soup = PTTScraper.get_soup(self.base_url + post_url)
        content = soup.find(id='main-content').text

        # 抓取推文
        pushes = soup.find_all('div', class_='push')

        with ThreadPoolExecutor() as executor:
            push_list = list(executor.map(self.get_push, pushes))

        return content, push_list

    def get_push(self, push):
        try:
            if push.find('span', class_='push-tag') is None:
                return dict()
            push_tag = push.find('span', class_='push-tag').text.strip()
            push_userid = push.find('span', class_='push-userid').text.strip()
            push_content = push.find('span', class_='push-content').text.strip().lstrip(":")
            push_ipdatetime = push.find('span', class_='push-ipdatetime').text.strip()
            push_dict = {
                "Tag": push_tag,
                "Userid": push_userid,
                "Content": push_content,
                "Ipdatetime": push_ipdatetime
            }
        except Exception as e:
            print(e)
        return push_dict

    @staticmethod
    def get_soup(url):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/58.0.3029.110 Safari/537.3", }
        cookies = {"over18": "1"}
        response = requests.get(url, headers=headers, cookies=cookies)
        return BeautifulSoup(response.text, 'html.parser')

    def fetch_post(self, url):
        soup = PTTScraper.get_soup(self.base_url + url)

        # Extract post information
        try:
            if soup.find(id='main-content') is not None:
                content = soup.find(id='main-content').text
                content = content.split('※ 發信站')[0]
            if soup.find(class_='article-meta-value') is not None:
                author = soup.find(class_='article-meta-value').text
                title = soup.find_all(class_='article-meta-value')[-2].text
                date_str = soup.find_all(class_='article-meta-value')[-1].text
                date = datetime.strptime(date_str, '%a %b %d %H:%M:%S %Y')
            else:
                author = None
                title = None
                date_str = None
                date = None
        except Exception as e:
            print(self.base_url + url)
            print(e)
        # Extract comments
        pushes = soup.find_all('div', class_='push')

        with ThreadPoolExecutor() as executor:
            push_list = list(executor.map(self.get_push, pushes))
        return {'Title': title, 'Author': author, 'Date': date, 'Content': content,
                'Link': url, 'Pushes': push_list}

    def get_data_current_page(self, soup=None, until_date=datetime.now(), *args,
                              max_posts=100, links_num=0):
        reach = False
        until_date = until_date.replace(hour=0, minute=0, second=0, microsecond=0)

        if soup is None:
            soup = PTTScraper.get_soup(self.url)
        links = []
        div_element = soup.find('div', {'class': 'r-list-sep'})
        if div_element is None:
            for entry in reversed(soup.select('.r-ent')):
                try:
                    title = entry.find("div", "title").text.strip()
                    if entry.find("div", "title").a is None:
                        continue
                    # print(title)
                    if len(args) == 2:
                        if not (args[0] in title and args[1] in title):
                            continue
                    elif len(args) == 1:
                        if args[0] not in title:
                            print("1")
                            # continue
                    else:
                        pass
                    date = entry.select('.date')[0].text.strip()

                    post_date = datetime.strptime(date, '%m/%d').replace(year=until_date.year)
                    # print(len(links))
                    if len(links) + links_num >= max_posts or post_date < until_date:
                        reach = True
                        break
                    links.append(entry.select('.title a')[0]['href'])
                except Exception as e:
                    print(e)
        else:
            previous_elements = [element for element in div_element.previous_siblings if
                                 element.name == 'div' and 'r-ent' in element.get('class', [])]
            for element in reversed(previous_elements):

                # 找到標題和連結的元素
                title_link_element = element.find('a')
                if title_link_element:
                    # 取得標題和連結
                    title = title_link_element.text.strip()
                    if len(args) == 2:
                        if not (args[0] in title and args[1] in title):
                            continue
                    links.append(title_link_element.get('href'))
                date_element = element.find('div', {'class': 'date'})
                if date_element:
                    # 取得發文日期
                    date = date_element.text.strip()
                post_date = datetime.strptime(date, '%m/%d').replace(year=until_date.year)
                if len(links) + links_num >= max_posts or post_date < until_date:
                    reach = True
                    break
        if 'post_date' not in locals():
            return [], False, 0
        print(post_date)
        # print(len(links))
        with ThreadPoolExecutor() as executor:
            data = list(executor.map(self.fetch_post, links))
        return data, reach, len(links)

    def get_data_until(self, until_date, *args, max_posts=100):
        """
        取得到 until_date 之後的所有文章
        :param until_date:  日期
        :param max_posts: 最多抓取文章
        :return: 文章串列
        """
        data = []
        if not isinstance(until_date, datetime):
            date = datetime.strptime(until_date, '%m/%d').replace(year=datetime.now().year)
        else:
            date = until_date
        links_num = 0
        while True:
            soup = PTTScraper.get_soup(self.url)
            data_curr, date_end, num = self.get_data_current_page(soup, date, *args,
                                                                  max_posts=max_posts, links_num=links_num)
            data.extend(data_curr)
            print("文章總篇數:", len(data))
            if date_end:
                return data
            links_num += num

            # 找到上一頁的連結
            prev_link = soup.find('a', string='‹ 上頁')['href']
            self.url = self.base_url + prev_link
        return data

    def get_data_days_before(self, delta_days, *args, max_posts=100):
        """
        取得 delat_days 天之前的文章
        :param delta_days: 間隔天數
        :param max_posts: 最多回抓取幾篇PO文
        :return: 文章 list
        """
        after_date = datetime.now() - timedelta(days=delta_days)
        # print(args)
        return self.get_data_until(after_date, *args, max_posts=max_posts)

    def get_title_and_before_days(self, *args, delta_days, max_posts=100):
        return self.get_data_days_before(delta_days, *args, max_posts=max_posts)


# 使用方式
if __name__ == "__main__":
    board = "Gossiping"
    scraper = PTTScraper(board)
    begin = time.time()
    data = scraper.get_data_days_before(1)
    # data = scraper.get_title_and_before_days("盤中", "[閒聊]", delta_days=10, max_posts=2)
    end = time.time()
    print(end - begin)
    if data is not None:
        df = pd.DataFrame(data)
        print(df.Title)
    # print(pd.DataFrame(df.Pushes[1]))
