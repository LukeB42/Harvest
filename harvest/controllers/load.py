# This file contains functions designed for
# loading cron tables and storing new feeds.

from harvest import db
from sqlalchemy import and_
from harvest.controllers.utils import spaceparse
from harvest.controllers.cron import parse_timings
from harvest.models import APIKey, Feed, FeedGroup

def create_feed(log, db, key, group, feed):
    """
    Takes a key object, a group name and a dictionary
    describing a feed ({name:,url:,schedule:,active:})
    and reliably attaches a newly created feed to the key
    and group.
    """
    if not type(feed) == dict:
        log('Unexpected type when creating feed for API key "%s"' % key.name)
        return

    for i in ['name', 'schedule', 'active', 'url']:
        if i not in feed.keys():
            log('%s: Error creating feed. Missing "%s" field from feed definition.' % (key.name, i))
            return

    f  = Feed.query.filter(and_(Feed.key == key, Feed.name == feed['name'])).first()
    fg = FeedGroup.query.filter(and_(FeedGroup.key == key, FeedGroup.name == group)).first()

    if f:
        if f.group:
            log('%s: Error creating feed "%s" in group "%s", feed already exists in group "%s".' % \
                (key.name, feed['name'], group, f.group.name))
            return
        elif fg:
            log('%s: %s: Adding feed "%s"' % (key.name, fg.name, f.name))
            fg.append(f)
            db.session.add(fg)
            db.session.add(f)
            db.session.commit()
            return

    if not fg:
        log('%s: Creating feed group %s.' % (key.name, group))
        fg = FeedGroup(name=group)
        key.feedgroups.append(fg)

    try:
        parse_timings(feed['schedule'])
    except Exception as e:
        log('%s: %s: Error creating "%s": %s' % \
            (key.name, fg.name, feed['name'], str(e)))

    log('%s: %s: Creating feed "%s"' % (key.name, fg.name, feed['name']))
    f = Feed(
        name=feed['name'],
        url=feed['url'],
        active=feed['active'],
        schedule=feed['schedule']
    )
    fg.feeds.append(f)
    key.feeds.append(f)
    db.session.add(key)
    db.session.add(fg)
    db.session.add(f)
    db.session.commit()

def parse_crontab(filename):
    """
    Get a file descriptor on filename and
    create feeds and groups for API keys therein.
    """
    def log(message):
        print(message)

    try:
        fd = open(filename, "r")
    except OSError:
        print("Error opening %s" % filename)
        raise SystemExit
    crontab = fd.read()
    fd.close()

    key = None

    for i, line in enumerate(crontab.split('\n')):

        if line.startswith("apikey:"):
            if ' ' in line:
                key_str = line.split()[1]
                key = APIKey.query.filter(APIKey.key == key_str).first()
            if not key:
                print('Malformed or unknown API key at line %i in %s: %s' % (i + 1, filename, line))
                raise SystemExit
            else:
                print('Using API key "%s".' % key.name)

        if line.startswith("http"):
            feed = {'active': True}

            feed['url'] = line.split().pop(0)
            line = ' '.join(line.split()[1:])

            names = spaceparse(line)
            if not names:
                print("Error parsing feed or group name at line %i in %s: %s" % (i + 1, filename, line))
                continue
            feed['name'], group = names[:2]

            schedule = line.split()[-5:]
            try:
                parse_timings(schedule)
            except Exception as e:
                print("Error parsing schedule at line %i in %s: %s" % (i + 1, filename, str(e)))
                continue

            feed['schedule'] = ' '.join(schedule)

            create_feed(log, db, key, group, feed)
