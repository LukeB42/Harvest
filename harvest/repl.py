#!/usr/bin/env python
import sys
import cmd
import json
import time
import errno
import _curses
import argparse
import textwrap
from harvest import app
from harvest.client import Client
from harvest.models import APIKey
from subprocess import Popen, PIPE
from harvest.controllers.utils import tconv, spaceparse
from harvest.controllers.tui import window

try:
    from pygments import highlight
    from pygments.lexers import JsonLexer
    from pygments.styles import get_style_by_name, STYLE_MAP
    from pygments.formatters.terminal256 import Terminal256Formatter
except ImportError:
    highlight = False

class repl(cmd.Cmd):

    prompt = "> "
    intro = "Harvest %s\nPsybernetics %i\n" % (app.version, time.gmtime()[0])
    ruler = '-'
    width = 80

    def parse_args(self, args):
        body = {}
        parsed = spaceparse(args)
        args = args.split()
        for i in args:
            try:
                x = i.split('=')
                if type(parsed) == dict and not x[0] in parsed:
                    parsed[x[0]] = x[1]
                else:
                    body[x[0]] = x[1]
            except:
                continue
        if type(parsed) == dict:
            body = parsed
        return body

    def formatted_prompt(self):
        """
        Here we format the first return value of /v1/articles/count
        into something that adds commas to triple digit (etc) values.
        """
        try:
            return "({:,}) > ".format(
                self.c.get("articles/count")[0]
            )
        except:
            return "no connection> "

    def do_setkey(self, key):
        "Sets the API key to transmit requests with."
        if key:
            self.c.key = key
            print('Changed active API key to "%s"' % key)
        else:
            print("Usage: setkey <key>")

    def do_use(self, key):
        "Alias of setkey."
        self.do_setkey(key)

    def do_getkey(self, line):
        "Displays the current API key."
        print(self.c.key)

    def do_get(self, line):
        """
        Sends GET requests
        EG: get articles
            get feeds
            get feedgroups
        """
        response = self.c._send_request(line)
        self.display(response)

    def do_put(self, line):
        """
        Creates a new feed or feed group.
        EG: put feedgroups name=HN
        """
        if ' ' not in line:
            print("Need data to transmit.")
        else:
            line, body = line.split(' ', 1)
            body = self.parse_args(body)
            response = self.c._send_request(line, 'PUT', body)
            self.display(response)

    def do_post(self, line):
        """
        Modifies an existing feed or feed group.
        EG: post feeds/SomeFeed schedule="20 3 2! * *"
        """
        if ' ' not in line:
            print("Need data to transmit.")
        else:
            line, body = line.split(' ', 1)
            body = self.parse_args(body)
            response = self.c._send_request(line, 'POST', body)
            self.display(response)

    def do_exit(self, line):
        try:
            _curses.endwin()
        except _curses.error:
            pass
        finally:
            raise SystemExit

    def do_read(self, line):
        """
        Usage: read <article_uid>
        Pipes article content into the system pager.

        Text column width can be configured with the width command.
        """
        then = time.time()
        response = self.c._send_request("articles/" + line)
        if response[1] != 200:
            print(response[1])
            return

        data = response[0]

        if 'content' not in data:
            print(None)
        else:
            p = Popen(['less', '-P', data['title']], stdin=PIPE)

            try:
                duration = tconv(int(then) - int(data['created']))
                header = '%s\n(%i paragraphs, fetched %s ago)\n%s\n\n' % (
                    data['title'],
                    len(data['content'].split("\n")) // 2 + 1,
                    duration,
                    data['url']
                )
                p.stdin.write(header.encode('utf-8', 'replace'))

                content = data['content']
                if self.width == "auto":
                    s = _curses.initscr()
                    width = s.getmaxyx()[1]
                    _curses.endwin()
                else:
                    width = self.width

                content = '\n'.join(
                    textwrap.wrap(content, width, break_long_words=False, replace_whitespace=False)
                )
                p.stdin.write(content.encode('utf-8', 'replace'))

            except IOError as e:
                if e.errno == errno.EPIPE or e.errno == errno.EINVAL:
                    sys.stderr.write("Error writing to pipe.\n")
                else:
                    raise

            p.stdin.close()
            p.wait()

    def do_delete(self, line):
        """
        Sends a DELETE request.
        EG: delete feeds/somefeed
        """
        if ' ' in line:
            line, body = line.split(' ', 1)
            body = self.parse_args(body)
        else:
            body = ''
        response = self.c._send_request(line, 'DELETE', body)
        self.display(response)

    def do_EOF(self, line):
        print("^D", end=' ')
        return True

    def postcmd(self, stop, line):
        self.prompt = self.formatted_prompt()
        return stop

    def emptyline(self):
        pass

    def postloop(self):
        print()

    def do_width(self, line):
        """
        Set the text width for the read command.
        Acceptable values are an integer amount of characters or "auto".
        """
        if line == "auto":
            self.width = "auto"
        elif line == "":
            print("The current width is set to %s" % str(self.width))
        else:
            try:
                self.width = int(line)
            except:
                print("width must be an integer.")

    def do_search(self, line):
        self.do_get("articles/search/" + line)

    def do_style(self, style):
        """
        Usage: style <theme_name>
        Lists the available themes if no
        name is supplied, or sets the theme to use.
        """
        if not self.highlight:
            print("For syntax highlighting you will need to install the Pygments package.")
            print("sudo pip install pygments")
            return
        if style:
            self.style = style
            print('Changed style to "%s"' % style)
        else:
            print(', '.join(self.AVAILABLE_STYLES))
            print('Currently using "%s"' % self.style)

    def display(self, response):
        if self.highlight:
            print(response[1])
            print(highlight(json.dumps(response[0], indent=4), JsonLexer(), Terminal256Formatter(style=self.style)))
        else:
            self.c.p(response)

def reqwrap(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except:
            return ({'error': 'Connection refused.'}, 000)
    return wrapper


def start(url, api_key, ncurses=False):
    if ncurses:
        r = window
    else:
        r = repl()

    r.c = Client('', url, verify=False)
    r.c.key = api_key
    r.c.verify_https = False

    if not ncurses:
        r.highlight = highlight
        r.prompt = r.formatted_prompt()
        if highlight:
            r.AVAILABLE_STYLES = set(STYLE_MAP.keys())
            if 'tango' in r.AVAILABLE_STYLES:
                r.style = 'tango'
            else:
                for s in r.AVAILABLE_STYLES:
                    break
                r.style = s
    r.c._send_request = reqwrap(r.c._send_request)

    try:
        if ncurses:
            window.start()
        else:
            r.cmdloop()
    except KeyboardInterrupt:
        print("^C")
        raise SystemExit
