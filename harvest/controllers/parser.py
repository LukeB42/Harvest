# This file implements routines for extracting links from response objects.
import re
import lxml
import urllib.parse
import feedparser
from goose3 import Goose

def extract_links(response):
    urls = []
    if ('content-type' in response.headers.keys()) and ('xml' in response.headers['content-type']):
        f = feedparser.parse(response.text)
        for entry in f.entries:
            urls.append({entry.link: entry.title})
        del f
    else:  # The following is a highly experimental feature.
        url = urllib.parse.urlparse(response.url)
        url = url.scheme + "://" + url.netloc
        p = Parser(response.text, url=url)
        urls = p.parse()
        del url, p
    return urls

class Parser(object):
    """
    Build a list of relevant links from an HTML string and the root URL.

    p = Parser(html_text, root_url)
    urls = p.parse()
    """
    def __init__(self, html=None, doc=None, url=None):
        self.html = html
        self.doc  = doc
        try:
            self.url = urllib.parse.urlparse(url).netloc
        except:
            self.url = url
        self.links = []

    def root_to_urls(self, doc, titles):
        """
        Return a list of urls from an lxml root.
        """
        if doc is None:
            return []

        a_tags = doc.xpath('//a')
        if titles:
            return [(a.get('href'), a.text) for a in a_tags if a.get('href')]
        return [a.get('href') for a in a_tags if a.get('href')]

    def get_urls(self, _input=None, titles=False, regex=False):
        if (not _input) and (not self.html):
            return []
        if not _input:
            _input = self.html
        if regex:
            text = re.sub('<[^<]+?>', ' ', _input)
            text = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', _input)
            text = [i.strip() for i in _input]
            return _input or []
        if isinstance(_input, str):
            doc = self.fromstring(_input)
        else:
            doc = _input
        return self.root_to_urls(doc, titles)

    def fromstring(self, html):
        try:
            self.doc = lxml.html.fromstring(html)
        except Exception as e:
            return None
        return self.doc

    def parse(self, html=None, url=None):
        """
        Whittle a list of urls into things we're interested in.
        """
        if self.links:
            self.links = []
        urls = self.get_urls(html)
        if not urls:
            return urls
        else:
            urls = set(urls)
        if url:
            url = "http://%s/" % urllib.parse.urlparse(url).netloc
        for u in urls:
            if url:
                if u == url: continue
            if self.url:
                if u == self.url: continue
            if u.startswith('#'): continue
            if not u.startswith('http'):
                if url:
                    if (url[-1] == '/') and (u[0] == '/'):
                        u = url + u[1:]
                    else:
                        u = url + u
                elif self.url:
                    if (self.url[-1] == '/') and (u[0] == '/'):
                        u = self.url + u[1:]
                    else:
                        u = self.url + u
                else:
                    continue
            self.links.append(u)
        return self.links

def extract_body(html):
    """
    Extract the body text of a web page.
    """
    g = Goose({'enable_image_fetching': False})
    article = g.extract(raw_html=html)
    del g
    return article.cleaned_text

def extract_title(html):
    """
    Extract the title of a web page.
    """
    g = Goose({'enable_image_fetching': False})
    article = g.extract(raw_html=html)
    del g
    return article.title

def summarise(article):
    stopnum = c = 0
    for i, v in enumerate(article.split()):
        if v.endswith('.'):
            if c >= 2:
                stopnum = i + 1
                break
            else:
                c += 1
    return ' '.join(article.split()[:stopnum])
