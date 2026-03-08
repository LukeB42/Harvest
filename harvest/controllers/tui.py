import os
import time
from harvest import app
from harvest.controllers.utils import tconv
from harvest.controllers.window import Window, Pane, ALIGN_LEFT, EXPAND, palette

class TitleBar(Pane):
    geometry = [EXPAND, 1]

    def update(self):
        label = "Harvest %s" % app.version
        self.change_content(0, label, ALIGN_LEFT, palette(-1, -1))

class EmissaryMenu(Pane):
    """
    Defines a menu where items call local methods.
    """
    geometry = [EXPAND, EXPAND]
    col  = [-1, -1]
    sel  = [-1, "blue"]
    items = []

    def update(self):
        for i, item in enumerate(self.items):
            if item[0]:
                colours = palette(self.sel[0], self.sel[1])
            else:
                colours = palette(self.col[0], self.col[1])
            text   = ' ' + item[1]
            spaces = ' ' * (self.width - len(text))
            text  += spaces
            self.change_content(i, text + '\n', ALIGN_LEFT, colours)

    def process_input(self, character):
        if character == 10 or character == 13 or character == 261:
            for i, item in enumerate(self.items):
                if item[0]:
                    func = getattr(self, item[2].lower(), None)
                    if func:
                        func()

        elif character in [259, 258, 339, 338]:
            for i, item in enumerate(self.items):
                if item[0]:
                    if character == 259:  # up arrow
                        if i == 0: break
                        item[0] = 0
                        self.items[i - 1][0] = 1
                        break
                    if character == 258:  # down arrow
                        if i + 1 >= len(self.items): break
                        item[0] = 0
                        self.items[i + 1][0] = 1
                        break
                    if character == 339:  # page up
                        item[0] = 0
                        self.items[0][0] = 1
                        break
                    if character == 338:  # page down
                        item[0] = 0
                        self.items[-1][0] = 1
                        break

class FeedGroups(EmissaryMenu):
    geometry = [EXPAND, EXPAND]
    def update(self):
        if not self.items:
            (res, status) = self.window.c.get("feeds")

class Feeds(EmissaryMenu):
    geometry = [EXPAND, EXPAND]
    items = []

class Articles(Pane):
    """
    items for Articles are [1, "text", "uid"]
    """
    geometry = [EXPAND, EXPAND]
    items = []
    col  = [-1, -1]
    sel  = ["black", "white"]
    avail = ["black", "green"]

    def update(self):
        if not self.items:
            self.fetch_items()

        for i, item in enumerate(self.items):
            if item[0]:
                if item[3]:
                    colours = palette(self.avail[0], self.avail[1])
                else:
                    colours = palette(self.sel[0], self.sel[1])
            else:
                colours = palette(self.col[0], self.col[1])
            text   = ' ' + item[1]
            spaces = ' ' * (self.width - len(text))
            text  += spaces
            self.change_content(i, text + '\n', ALIGN_LEFT, colours)

    def process_input(self, character):
        if character in [10, 13, 261]:
            for i, item in enumerate(self.items):
                if item[0]:
                    uid = item[2]
                    (article, status) = self.window.c.get('articles/' + uid)
                    statuspane = self.window.get("status")

                    if status != 200:
                        statuspane.status = str(status)
                    else:
                        self.reader.article = article
                        if article['content'] is None:
                            self.reader.data = ""
                        else:
                            self.reader.data = article['content']
                        self.reader.active = True
                        self.active = False

        elif character == 114:  # r to refresh
            self.fetch_items()

        elif character == 9:    # tab to reader
            reader = self.window.get("reader")
            reader.active = True
            self.active   = False

        elif character in [259, 258, 339, 338]:
            for i, item in enumerate(self.items):
                if item[0]:
                    if character == 259:  # up arrow
                        if i == 0: break
                        item[0] = 0
                        self.items[i - 1][0] = 1
                        break
                    if character == 258:  # down arrow
                        if i + 1 >= len(self.items): break
                        item[0] = 0
                        self.items[i + 1][0] = 1
                        break
                    if character == 339:  # page up
                        item[0] = 0
                        self.items[0][0] = 1
                        break
                    if character == 338:  # page down
                        item[0] = 0
                        self.items[-1][0] = 1
                        break

    def fetch_items(self):
        (res, status) = self.window.c.get("articles?per_page=%i" % self.height)
        if status == 200:
            self.fill_menu(res)
        else:
            status = self.window.get("status")
            status.status = str(res)

    def fill_menu(self, res):
        self.items   = []
        self.content = []
        for r in res["data"]:
            self.items.append([0, r['title'], r['uid'], r['content_available']])
        if self.items:
            self.items[0][0] = 1

class Reader(Pane):
    """
    Defines a scrolling pager for long multi-line strings.
    """
    geometry  = [EXPAND, EXPAND]
    data      = ""
    outbuffer = ""
    position  = 0
    article   = None

    def update(self):
        if self.article:
            feed    = self.article.get('feed', None)
            heading = "%s\n%s (%s %s ago)\n%s\n\n" % \
                (self.article['title'], feed if feed else "",
                self.article['uid'], tconv(int(time.time()) - int(self.article['created'])),
                self.article['url'])
            self.change_content(0, heading)
        self.outbuffer = self.data.split('\n')[self.position:]
        self.change_content(1, '\n'.join(self.outbuffer))

    def process_input(self, character):
        self.window.window.clear()
        if character == 259:    # Up arrow
            if self.position != 0:
                self.position -= 1
        elif character == 258:  # Down arrow
            self.position += 1
        elif character == 339:  # Page up
            if self.position - self.height < 0:
                self.position = 0
            else:
                self.position -= self.height
        elif character == 338:  # Page down
            if not self.position + self.height > len(self.data.split('\n')):
                self.position += self.height

        elif character in [260, 9]:  # Left arrow or tab
            articles = self.window.get("articles")
            articles.active = True
            self.active = False

        elif character in [70, 102]:  # f/F to fullscreen the pager
            articles = self.window.get("articles")
            if articles.hidden:
                articles.hidden = False
            else:
                articles.hidden = True

class StatusLine(Pane):
    geometry  = [EXPAND, 1]
    content   = []
    buffer    = ""
    status    = ""
    searching = False
    tagline   = "Thanks God."

    def update(self):
        if self.searching:
            self.change_content(0, "/" + self.buffer, palette("black", "white"))
        else:
            state  = self.tagline
            state += ' ' * ((self.width // 2) - len(self.tagline) - (len(str(self.status)) // 2))
            state += str(self.status)
            self.change_content(0, state)

    def process_input(self, character):
        self.window.window.clear()
        if not self.searching and character in [80, 112]:  # p/P to enter a python REPL
            try:
                import pprint
                from ptpython.repl import embed

                def configure(repl):
                    repl.prompt_style                   = "ipython"
                    repl.vi_mode                        = True
                    repl.confirm_exit                   = False
                    repl.show_status_bar                = False
                    repl.show_line_numbers              = True
                    repl.show_sidebar_help              = False
                    repl.highlight_matching_parenthesis = True
                    repl.use_code_colorscheme("native")

                def a(uid):
                    """Return raw article text given an article uid."""
                    response = self.window.c.get("articles/%s" % uid)
                    if response[1] == 200:
                        return response[0]['content']
                    return ""

                p = pprint.PrettyPrinter()
                p = p.pprint
                l = {"a": a, "c": self.window.c, "p": p, "window": self.window}
                reader  = self.window.get("reader")
                article = getattr(reader, "article", None)
                if article:
                    l['article'] = article

                self.window.stop()
                print("\nStarting REPL. ^D to exit.")
                embed(locals=l, configure=configure)
                self.window.start()
            except ImportError:
                pass

        if not self.searching and character == 47:  # / to search
            articles = self.window.get("articles")
            articles.active = False
            self.searching  = True
            return

        if self.searching:
            self.window.window.clear()
            if character == 23 and self.buffer:    # Clear buffer on ^W
                self.buffer = ''
            elif character == 263:                 # Handle backspace
                if self.buffer:
                    self.buffer = self.buffer[:-1]
                if not self.buffer:
                    self.searching = False
                    articles = self.window.get("articles")
                    articles.active = True

            elif character == 10 or character == 13:  # Handle the return key
                self.searching = False
                articles = self.window.get("articles")
                articles.active = True
                reader   = self.window.get("reader")
                reader.active = False
                self.buffer = ""
            else:
                try:
                    self.buffer += chr(character)
                except:
                    pass
                articles = self.window.get("articles")
                url = "articles/search/" + self.buffer + "?per_page=" + str(articles.height)
                (res, status) = self.window.c.get(url)
                if status == 200:
                    articles.fill_menu(res)


window = Window(blocking=True)

titlebar          = TitleBar("titlebar")
feedgroups        = FeedGroups("feedgroups")
feedgroups.active = False
feedgroups.hidden = True
feeds             = Feeds("feeds")
feeds.active      = False
feeds.hidden      = True
articles          = Articles("articles")
reader            = Reader("reader")
reader.wrap       = True
reader.active     = False
articles.reader   = reader
status            = StatusLine("status")

window.add(titlebar)
panes = [feedgroups, feeds, articles, reader]
window.add(panes)
window.add(status)

window.exit_keys.append(4)  # ^D to exit
