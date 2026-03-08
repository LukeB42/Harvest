import asyncio
import sys, os, time, hashlib

from sqlalchemy import and_
from harvest.models import Feed, FeedGroup, APIKey
from harvest.controllers import cron
from harvest.controllers import fetch

class FeedManager(object):
    """Keeps CronTab objects in rotation."""
    def __init__(self, log):
        self.log      = log
        self.app      = None
        self.running  = False
        self.crontabs = {}  # name -> CronTab
        self.tasks    = {}  # name -> asyncio.Task
        self.revived  = {}  # name -> [count, timestamp]

    def load_feeds(self):
        """
        Start all active feeds. Called before the event loop is running,
        so we only create CronTab objects here — start_all() spawns the tasks.
        """
        for key in APIKey.query.all():

            if key.reader:
                continue

            if not key.active:
                self.log('API key "%s" marked inactive. Skipped.' % key.name)
                continue

            self.log("%s: Processing feed groups." % key.name)

            # Collect active feeds first so we can align the log columns.
            active = []
            for fg in key.feedgroups:
                if not fg.active:
                    self.log('%s: Feed group "%s" marked inactive. Skipped.' % \
                        (key.name, fg.name))
                    continue
                for feed in fg.feeds:
                    if not feed.active:
                        self.log('%s: %s: Feed "%s" marked inactive. Skipped.' % \
                            (key.name, fg.name, feed.name))
                        continue
                    active.append((fg, feed))

            if active:
                gw = max(len(fg.name)   for fg, _    in active)
                nw = max(len(feed.name) for _,   feed in active)
                for fg, feed in active:
                    self.log('%s: %s  %s  (%s)' % (
                        key.name,
                        fg.name.ljust(gw),
                        ('"%s"' % feed.name).ljust(nw + 2),
                        feed.schedule,
                    ))
                    ct = self.create_crontab(feed)
                    self.crontabs[ct.name] = ct

    def start_all(self):
        """
        Spawn asyncio tasks for all loaded crontabs.
        Must be called from within a running event loop.
        """
        for name, ct in self.crontabs.items():
            task = asyncio.create_task(ct.run())
            task.set_name(name)
            self.tasks[name] = task

    async def run(self):
        """
        Monitor running feed tasks and revive any that have died.
        """
        self.running = True
        while self.running:
            for name in list(self.tasks.keys()):
                if self.tasks[name].done():
                    self.revive_by_name(name)
            await asyncio.sleep(5)
        self.log("Feed manager stopped.")

    def create_crontab(self, feed):
        t   = cron.parse_timings(feed.schedule.split())
        evt = cron.Event(
            fetch.fetch_feed,
            t[0], t[1], t[2], t[3], t[4],
            [feed.id, self.log]
        )
        evt.feed = feed
        ct       = cron.CronTab(evt)
        ct.name  = self.generate_ct_name(feed)
        return ct

    def generate_ct_name(self, feed):
        return hashlib.sha1(("%s %s" % (feed.name, feed.created)).encode()).hexdigest()

    def revive_by_name(self, name):
        """
        Restart a dead crontab, with a minimum of one minute between restarts.
        """
        now = time.time()
        if name in self.revived:
            then = self.revived[name][1]
            if (now - then) < 60:
                return
            self.revived[name][0] += 1
            self.revived[name][1]  = now
        else:
            self.revived[name] = [1, now]

        if name not in self.crontabs:
            return

        old_feed = self.crontabs[name].events[0].feed
        feed     = Feed.query.get(old_feed.id)
        if not feed or not feed.active:
            return

        ct = self.create_crontab(feed)
        ct.name = name
        self.crontabs[name] = ct
        task = asyncio.create_task(ct.run())
        task.set_name(name)
        self.tasks[name] = task
        self.log("Restarted %s" % name, "warning")

    def is_feed_running(self, feed):
        """
        Synchronous check — safe to call from Flask route handlers.
        """
        name = self.generate_ct_name(feed)
        task = self.tasks.get(name)
        return bool(task and not task.done())

    def handle_check(self, feed):
        name = self.generate_ct_name(feed)
        task = self.tasks.get(name)
        return bool(task and not task.done())

    async def handle_start(self, args):
        """
        Schedule a feed. Looks the feed up fresh from the database.
        """
        key_id, name = args
        key  = APIKey.query.get(key_id)
        feed = Feed.query.filter(and_(Feed.key_id == key_id, Feed.name == name)).first()
        if not feed:
            return False

        self.log('%s: %s: Scheduling "%s" (%s)' % \
            (key.name, feed.group.name, feed.name, feed.schedule))

        ct = self.create_crontab(feed)
        self.crontabs[ct.name] = ct
        task = asyncio.create_task(ct.run())
        task.set_name(ct.name)
        self.tasks[ct.name] = task
        return True

    async def handle_stop(self, args):
        """
        Halt a feed by key id and name.
        """
        key_id, name = args

        for ct_name, ct in list(self.crontabs.items()):
            feed = ct.events[0].feed
            if feed.name == name and feed.key_id == key_id:
                self.log('%s: Unscheduling "%s".' % (feed.key.name, feed.name))
                task = self.tasks.pop(ct_name, None)
                if task:
                    task.cancel()
                del self.crontabs[ct_name]
                return True
        return False

    def __getitem__(self, name):
        if name in self.crontabs:
            return self.crontabs[name]
        raise KeyError('Invalid CronTab')

    def __delitem__(self, name):
        if name in self.crontabs:
            task = self.tasks.pop(name, None)
            if task:
                task.cancel()
            del self.crontabs[name]

    def keys(self):
        return self.crontabs.keys()
