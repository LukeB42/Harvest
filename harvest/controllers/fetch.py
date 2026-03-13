import time
import urllib.parse
import requests
import feedparser
from harvest import app, db
from sqlalchemy import and_, or_
from harvest.controllers import parser
from harvest.controllers.utils import uid, tconv

requests.packages.urllib3.disable_warnings()

snappy = None
if app.config['COMPRESS_ARTICLES']:
    try:
        import snappy
    except ImportError:
        pass

# This is a globally-available dictionary of urls we've already visited.
# It permits us to only try a url four times every half an hour.
seen = {}

def get(url, timeout=30):
    headers = {"User-Agent": "Harvest " + app.version}
    return requests.get(url, headers=headers, verify=False, timeout=timeout)

def fetch_feed(feed_id, log):
    """
    Fetch a feed by id. Runs in a thread via asyncio.to_thread(), so pushes
    its own app context to get a clean Flask-SQLAlchemy session.
    """
    with app.app_context():
        from harvest.models import Feed, Article

        feed = Feed.query.get(feed_id)
        if not feed:
            return

        if feed.group:
            log("%s: %s: Fetching %s." % \
                (feed.key.name, feed.group.name, feed.name))
        else:
            log("%s: Fetching %s." % (feed.key.name, feed.name))

        try:
            r = get(feed.url)
        except Exception as e:
            log("%s: %s: Error fetching %s: %s" % \
                (feed.key.name, feed.group.name, feed.name, str(e)))
            return

        links = parser.extract_links(r)
        for link in links:
            fetch_and_store(link, feed, log)

def fetch_and_store(link, feed, log, key=None, overwrite=False):
    """
    Fetches, extracts and stores a URL.
    link can be a list of urls or a dictionary of url/title pairs.
    """
    from harvest.models import Article

    then = int(time.time())

    if type(link) == dict:
        for url, title in link.items(): continue
    else:
        url   = link
        title = None

    if Article.query.filter(and_(Article.url == url, Article.feed == feed)).first():
        if overwrite:
            log("%s: %s/%s: Preparing to overwrite existing copy of %s" % \
                (feed.key.name, feed.group.name, feed.name, url), "debug")
        else:
            log("%s: %s/%s: Already storing %s" % (feed.key.name, feed.group.name, feed.name, url), "debug")
            return

    if "://" not in url:
        url = "http://" + url

    if url not in seen:
        seen[url] = [1, int(time.time())]
    else:
        now = int(time.time())
        if (now - seen[url][1]) > 60 * 30:
            seen[url] = [1, int(time.time())]
        if seen[url][0] >= 4:
            return
        seen[url][0] += 1
        seen[url][1] = int(time.time())

    for _ in list(seen.keys()):
        if int(time.time()) - seen[_][1] > 86400:
            del seen[_]

    try:
        document = get(url)
    except Exception as e:
        log("%s: %s/%s: Error fetching %s: %s" % \
            (feed.key.name, feed.group.name, feed.name, url, str(e)))
        return

    if 'content-type' in document.headers:
        if 'application' in document.headers['content-type']:
            if not title:
                title = url
            article = Article(url=url, title=title)
            if "://" not in article.url:
                article.url = "http://" + article.url
            commit_to_feed(feed, article)
            log("%s: %s/%s: Stored %s, reference to %s (%s)" % \
                (feed.key.name, feed.group.name, feed.name, article.uid, url, document.headers['content-type']))
            return

    try:
        article_content = parser.extract_body(document.text)
        summary         = parser.summarise(article_content)
    except Exception as e:
        log("%s: %s: Error parsing %s: %s" % (feed.key.name, feed.group.name, url, str(e)))
        return

    if not title:
        title = parser.extract_title(document.text)

    if app.config['NO_DUPLICATE_TITLES']:
        if Article.query.filter(
            and_(Article.title == title, Article.key == feed.key)
        ).first():
            return

    article = Article(url=url, title=title, summary=summary)

    if not app.config['COMPRESS_ARTICLES']:
        article.content = article_content
    else:
        article.ccontent   = snappy.compress(article_content.encode("utf-8", "ignore"))
        article.compressed = True

    for s in app.scripts.scripts.values():
        try:
            s.execute(env={'article': article, 'feed': feed})
            article = s['article']
        except Exception as e:
            log("Error executing %s: %s" % (s.file, str(e)), "error")

    commit_to_feed(feed, article)

    now      = int(time.time())
    duration = tconv(now - then)
    log('%s: %s/%s: Stored %s "%s" (%s)' % \
        (feed.key.name, feed.group.name, feed.name, article.uid, article.title, duration))
    del then, now, duration, feed, article, url, title

def fetch_feedless_article(key, url, overwrite=False):
    """
    Given a URL, create an Article and attach it to a Key.
    """
    from harvest.models import Article

    then = int(time.time())
    log  = app.log

    if Article.query.filter(Article.url == url).first():
        if overwrite:
            log("%s: Preparing to overwrite existing copy of %s" % (key.name, url), "debug")
        else:
            log("%s: Already storing %s" % (key.name, url), "debug")
            return

    try:
        response = get(url)
    except Exception as e:
        log("%s: Error fetching %s: %s." % (key.name, url, str(e)))
        return

    article_content = parser.extract_body(response.text)
    title           = parser.extract_title(response.text)
    summary         = parser.summarise(article_content)
    article = Article(url=url, title=title, summary=summary)

    if not app.config['COMPRESS_ARTICLES']:
        article.content = article_content
    else:
        article.ccontent   = snappy.compress(article_content.encode("utf-8", "ignore"))
        article.compressed = True

    for s in app.scripts.scripts.values():
        try:
            s.execute(env={'article': article, 'feed': None})
            article = s['article']
        except Exception as e:
            log("Error executing %s: %s" % (s.file, str(e)), "error")

    key.articles.append(article)
    article.uid = uid()

    db.session.add(article)
    db.session.add(key)
    db.session.commit()

    now      = int(time.time())
    duration = tconv(now - then)
    log('%s: Stored %s "%s" (%s)' % (key.name, article.uid, article.title, duration))
    return article

def commit_to_feed(feed, article):
    """
    Place a new article on the api key of a feed, the feed itself,
    and commit changes.
    """
    article.uid = uid()

    session = feed._sa_instance_state.session
    feed.articles.append(article)
    feed.key.articles.append(article)

    session.add(article)
    session.add(feed)
    session.commit()
    del article, feed, session
