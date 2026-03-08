#!/usr/bin/env python3
# From http://stackoverflow.com/questions/373335/suggestions-for-a-cron-like-scheduler-in-python
import asyncio
import time, sys
from datetime import datetime, timedelta

class CronError(Exception):
    def __init__(self, message):
        self.message = message
    def __str__(self):
        return repr(self.message)

class days:
    mon = 0
    tue = 1
    wed = 2
    thu = 3
    fri = 4
    sat = 5
    sun = 6

class months:
    jan = 1
    feb = 2
    mar = 3
    apr = 4
    may = 5
    jun = 6
    jul = 7
    aug = 8
    sep = 9
    oct = 10
    nov = 11
    dec = 12

# Turn a list of timing data into raw numeric values
def parse_timings(timings):
    # minute  hour    day month   weekday
    # 0       6,12    *   0-11    mon-sun
    if type(timings) == str:
        timings = timings.split()
    if len(timings) != 5:
        print(len(timings), timings)
        raise CronError('Timings require five fields.')
    minute = hour = day = month = weekday = []
    if timings[0] == '*': minute  = allMatch
    if timings[1] == '*': hour    = allMatch
    if timings[2] == '*': day     = allMatch
    if timings[3] == '*': month   = allMatch
    if timings[4] == '*': weekday = allMatch
    for i, v in enumerate(timings):
        if len(v) < 3:
            try:
                r = int(v)
                if i == 0: minute  = [r]
                if i == 1: hour    = [r]
                if i == 2: day     = [r]
                if i == 3: month   = [r]
                if i == 4: weekday = [r]
            except:
                pass
        if ',' in v:
            t = v.split(',')
            x = []
            for f in t:
                x.append(int(f))
            if i == 0: minute  = x
            if i == 1: hour    = x
            if i == 2: day     = x
            if i == 3: month   = x
            if i == 4: weekday = x
            del t, f, x
        if v.endswith("!") or v.startswith("*/"):
            s = ""
            for j in v:
                if j.isdigit():
                    s += j
            s = int(s)
            if i == 0: minute  = range(0, 60, s)
            if i == 1: hour    = range(0, 24, s)
            if i == 2: day     = range(0, 32, s)
            if i == 3: month   = range(0, 12, s)
            if i == 4: weekday = range(0, 7, s)
        if '-' in v and len(v) > 2:
            r = v.split('-')
            for n, m in enumerate(r):
                try:
                    r[n] = int(m)
                except:
                    pass
                if type(r[n]) == int:
                    if i == 0: minute  = range(r[0], int(r[1]) + 1)
                    if i == 1: hour    = range(r[0], int(r[1]) + 1)
                    if i == 2: day     = range(r[0], int(r[1]) + 1)
                    if i == 3: month   = range(r[0], int(r[1]) + 1)
                    if i == 4: weekday = range(r[0], int(r[1]) + 1)
                    continue
                else:
                    start = stop = None
                    if i == 3:  # Months
                        if hasattr(months, r[0]):
                            start = getattr(months, r[0])
                        if hasattr(months, r[1]):
                            stop  = getattr(months, r[1])
                        if (start and stop) is not None:
                            month = range(start, stop + 1)
                            del start, stop
                        else:
                            raise CronError('Malformed month data.')
                    if i == 4:  # Weekdays
                        if hasattr(days, r[0]):
                            start = getattr(days, r[0])
                        if hasattr(days, r[1]):
                            stop  = getattr(days, r[1])
                        if (start and stop) is not None:
                            weekday = range(start, stop + 1)
                            del start, stop
                        else:
                            raise CronError('Malformed day-of-the-week data.')
            del v, i, r, n, m
    return minute, hour, day, month, weekday

def parse_crontab_line(line, lineno=None, tcpd=False):
    url = line.split()[0]
    f = line.split()[1:]
    for i, w in enumerate(f):
        if w.endswith("'"): break
    name = ' '.join(f[:i + 1]).strip("'")
    timings = ' '.join(f[i + 1:])
    parse_timings(timings)
    if not tcpd:
        if lineno:
            print("Line %s. %s: %s %s" % (lineno, name, url, timings))
        else:
            print("%s: %s %s" % (name, url, timings))
    return (url, name, timings)

# Some utility classes / functions first
class AllMatch(set):
    """Universal set - match everything"""
    def __contains__(self, item): return True

allMatch = AllMatch()

def conv_to_set(obj):  # Allow single integer to be provided
    if isinstance(obj, int):
        return set([obj])  # Single item
    if not isinstance(obj, set):
        obj = set(obj)
    return obj

class Event(object):
    def __init__(self, action, min=allMatch, hour=allMatch,
                       day=allMatch, month=allMatch, dow=allMatch,
                       args=(), kwargs={}):
        self.mins   = conv_to_set(min)
        self.hours  = conv_to_set(hour)
        self.days   = conv_to_set(day)
        self.months = conv_to_set(month)
        self.dow    = conv_to_set(dow)
        self.action = action
        self.args   = args
        self.kwargs = kwargs
        self.running = False
        self.name    = None

    def matchtime(self, t):
        """Return True if this event should trigger at the specified datetime"""
        return ((t.minute    in self.mins) and
                (t.hour      in self.hours) and
                (t.day       in self.days) and
                (t.month     in self.months) and
                (t.weekday() in self.dow))

    async def check(self, t):
        if self.matchtime(t):
            self.running = True
            await asyncio.to_thread(self.action, *self.args, **self.kwargs)
            self.running = False

class CronTab:
    def __init__(self, *events):
        self.events = events
        self.name   = None

    async def run(self):
        t = datetime(*datetime.now().timetuple()[:5])
        while True:
            for e in self.events:
                await e.check(t)
            t += timedelta(minutes=1)
            n = datetime.now()
            while n < t:
                s = (t - n).seconds + 1
                await asyncio.sleep(s)
                n = datetime.now()

    def __repr__(self):
        if self.name:
            return "<CronTab object '%s' at %s>" % (self.name, hex(id(self)))
        else:
            return "<CronTab object at %s>" % hex(id(self))
