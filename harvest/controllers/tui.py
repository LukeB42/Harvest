import os
import time
import datetime
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

class Feeds(Pane):
    """
    Left sidebar for selecting which feed to view articles from.
    Items: [selected, label, group_name, feed_name]
    group_name=None and feed_name=None means "All feeds".
    """
    geometry = [20, EXPAND]
    col      = (-1, -1)
    sel      = ("black", "white")

    def __init__(self, name):
        super().__init__(name)
        self.all_items  = []
        self.items      = []
        self.offset     = 0
        self.searching  = False
        self.search_buf = ""

    def update(self):
        self.content = []
        if not self.all_items:
            self.fetch_items()
        h       = self.height or 0
        visible = self.items[self.offset:self.offset + h]
        for i, item in enumerate(visible):
            if item[0]:
                colours = palette("black", "green") if self.active else palette(*self.sel)
            else:
                colours = palette(*self.col)
            text    = ' ' + item[1]
            text   += ' ' * max(0, self.width - len(text))
            self.change_content(i, text + '\n', ALIGN_LEFT, colours)

    def fetch_items(self):
        (res, status) = self.window.c.get("feeds?per_page=100")
        if status != 200:
            return
        all_items = [[0, "All", None, None]]
        for group in res.get("data", []):
            for feed in group.get("feeds", []):
                all_items.append([0, feed['name'], group['name'], feed['name']])
        self.all_items = all_items
        self.items     = list(self.all_items)
        if self.items:
            self.items[0][0] = 1
        max_len       = max(len(item[1]) for item in self.items) + 2  # leading space + padding
        self.geometry = [max_len, EXPAND]
        self.offset   = 0

    def _selected_index(self):
        for i, item in enumerate(self.items):
            if item[0]:
                return i
        return 0

    def _select(self, new_idx):
        """Select item at new_idx and scroll the viewport to keep it visible."""
        h = self.height or 1
        for item in self.items:
            item[0] = 0
        self.items[new_idx][0] = 1
        if new_idx < self.offset:
            self.offset = new_idx
        elif new_idx >= self.offset + h:
            self.offset = new_idx - h + 1

    def _activate_selection(self):
        """Tell Articles to load articles for the currently selected feed."""
        if not self.items:
            return
        idx      = self._selected_index()
        item     = self.items[idx]
        articles = self.window.get("articles")
        articles.feed_context = (item[2], item[3]) if item[2] is not None else None
        articles.fetch_items()

    def _apply_search(self):
        term       = self.search_buf.lower()
        self.items = [self.all_items[0]] + [
            i for i in self.all_items[1:] if term in i[1].lower()
        ]
        for item in self.items:
            item[0] = 0
        if self.items:
            self.items[0][0] = 1
        self.offset = 0

    def _reset_search(self):
        self.searching  = False
        self.search_buf = ''
        self.items      = list(self.all_items)
        for item in self.items:
            item[0] = 0
        if self.items:
            self.items[0][0] = 1
        self.offset = 0

    def process_input(self, character):
        if self.searching:
            self.window.window.clear()
            if character == 23:  # ^W - clear search and exit search mode
                self.search_buf = ''
                self._reset_search()
            elif character == 263:  # backspace
                if self.search_buf:
                    self.search_buf = self.search_buf[:-1]
                if not self.search_buf:
                    self._reset_search()
                else:
                    self._apply_search()
            elif character in (10, 13):  # enter - commit and return to navigation
                self.searching = False
            else:
                try:
                    self.search_buf += chr(character)
                    self._apply_search()
                except Exception:
                    pass
            return

        if character == 47:  # / - begin search
            self.searching  = True
            self.search_buf = ''
            return

        if character in (70, 102):  # f/F - hide feeds panel, return focus to articles
            self.hidden = True
            self.active = False
            self.window.get("articles").active = True
            self.window.window.clear()
            return

        if character in (114, 82, 269):  # r/R/F5 - refresh feed list
            idx     = self._selected_index()
            current = self.items[idx] if self.items else None
            sel_group, sel_feed = (current[2], current[3]) if current else (None, None)
            self.fetch_items()
            # Restore selection to the same feed if it still exists
            if sel_feed is not None:
                for i, item in enumerate(self.items):
                    if item[2] == sel_group and item[3] == sel_feed:
                        for it in self.items:
                            it[0] = 0
                        self._select(i)
                        break
            if character == 269:  # F5 - also refresh articles
                self.window.get("articles").fetch_items()
            self.window.window.clear()
            return

        if character in (261, 10, 13):  # right arrow or enter - activate feed and go to articles
            self._activate_selection()
            self.active = False
            self.window.get("articles").active = True
            return

        if not self.items:
            return

        idx = self._selected_index()
        h   = self.height or 1
        n   = len(self.items)

        if character == 259:  # up
            if idx > 0:
                self._select(idx - 1)
        elif character == 258:  # down
            if idx + 1 < n:
                self._select(idx + 1)
        elif character == 339:  # pgup
            if idx == self.offset:
                self.offset = max(0, self.offset - h)
            for item in self.items:
                item[0] = 0
            self.items[self.offset][0] = 1
        elif character == 338:  # pgdown
            last_vis = min(self.offset + h - 1, n - 1)
            if idx == last_vis:
                self.offset = min(self.offset + h, n - 1)
            last_vis = min(self.offset + h - 1, n - 1)
            for item in self.items:
                item[0] = 0
            self.items[last_vis][0] = 1
        elif character == 262:  # home - first item in list
            self._select(0)
        elif character == 360:  # end - last item in list
            self._select(n - 1)

class Articles(Pane):
    """
    items for Articles are [selected, title, uid, content_available, created]
    """
    geometry = [EXPAND, EXPAND]
    col      = (-1, -1)
    sel      = ("black", "white")
    avail    = ("black", "green")

    def __init__(self, name):
        super().__init__(name)
        self.items          = []
        self.offset         = 0
        self.feed_context   = None  # None = all feeds, or (group_name, feed_name)
        self.per_page       = 100
        self.has_more       = False
        self.bottom_aligned = False

    def update(self):
        self.content = []
        if not self.items:
            self.fetch_items()
        h           = self.height or 0
        n           = len(self.items)
        from_offset = n - self.offset

        if self.bottom_aligned and from_offset < h:
            display_offset = max(0, n - h)
            visible = self.items[display_offset:]
        else:
            self.bottom_aligned = False
            visible = self.items[self.offset:self.offset + h]

        for i, item in enumerate(visible):
            if item[0]:
                if self.active:
                    colours = palette(*self.avail) if item[3] else palette(*self.sel)
                else:
                    colours = palette(*self.sel)
            else:
                colours = palette(*self.col)
            ts   = datetime.datetime.fromtimestamp(item[4]).strftime('%d-%m-%y %H:%M')
            text = ' ' + ts + '  ' + item[1]
            text += ' ' * max(0, self.width - len(text))
            self.change_content(i, text + '\n', ALIGN_LEFT, colours)

    def _selected_index(self):
        for i, item in enumerate(self.items):
            if item[0]:
                return i
        return 0

    def _select(self, new_idx):
        h = self.height or 1
        for item in self.items:
            item[0] = 0
        self.items[new_idx][0] = 1
        if new_idx < self.offset:
            self.offset = new_idx
        elif new_idx >= self.offset + h:
            self.offset = new_idx - h + 1
        if new_idx == len(self.items) - 1 and self.has_more:
            self.fetch_more()

    def process_input(self, character):
        if character in (10, 13, 261):  # enter/right - open selected article
            for item in self.items:
                if item[0]:
                    uid = item[2]
                    (article, status) = self.window.c.get('articles/' + uid)
                    statuspane = self.window.get("status")
                    if status != 200:
                        statuspane.status = str(status)
                    else:
                        self.reader.article = article
                        self.reader.data    = article['content'] if article['content'] else ""
                        self.reader.active  = True
                        self.active         = False
                    break

        elif character == 260:  # left arrow - focus feeds panel
            feeds = self.window.get("feeds")
            if feeds:
                feeds.hidden = False
                feeds.active = True
                self.active  = False
                self.window.window.clear()

        elif character in (70, 102):  # f/F - toggle feeds panel
            feeds = self.window.get("feeds")
            if feeds:
                if feeds.hidden:
                    feeds.hidden = False
                    feeds.active = True
                    self.active  = False
                else:
                    feeds.hidden = True
                    feeds.active = False
                self.window.window.clear()

        elif character in (114, 269):  # r/F5 - refresh articles (F5 also refreshes feeds)
            if character == 269:
                feeds = self.window.get("feeds")
                if feeds:
                    feeds.fetch_items()
            self.fetch_items()

        elif character == 9:  # tab - go to reader
            reader = self.window.get("reader")
            reader.active = True
            self.active   = False

        elif character == 259:  # up
            if not self.items: return
            self.bottom_aligned = False
            idx = self._selected_index()
            if idx > 0:
                self._select(idx - 1)

        elif character == 258:  # down
            if not self.items: return
            idx = self._selected_index()
            if idx + 1 < len(self.items):
                self._select(idx + 1)
            elif self.has_more:
                self.fetch_more()
                if idx + 1 < len(self.items):
                    self._select(idx + 1)

        elif character == 339:  # pgup
            if not self.items: return
            self.bottom_aligned = False
            h   = self.height or 1
            idx = self._selected_index()
            if idx == self.offset:
                self.offset = max(0, self.offset - h)
            for item in self.items: item[0] = 0
            self.items[self.offset][0] = 1

        elif character == 338:  # pgdown
            if not self.items: return
            h        = self.height or 1
            n        = len(self.items)
            idx      = self._selected_index()
            last_vis = min(self.offset + h - 1, n - 1)
            if idx == last_vis:
                if last_vis == n - 1 and self.has_more:
                    self.fetch_more()
                    n = len(self.items)
                self.offset = min(self.offset + h, n - 1)
                self.bottom_aligned = (n - self.offset) < h
            last_vis = min(self.offset + h - 1, n - 1)
            for item in self.items: item[0] = 0
            self.items[last_vis][0] = 1

        elif character == 262:  # home - first item
            if not self.items: return
            self.bottom_aligned = False
            self._select(0)

        elif character == 360:  # end - last item
            if not self.items: return
            self._select(len(self.items) - 1)

    def fetch_items(self):
        if self.feed_context:
            group, name = self.feed_context
            url = "feeds/%s/%s/articles?per_page=%i" % (group, name, self.per_page)
        else:
            url = "articles?per_page=%i" % self.per_page
        (res, status) = self.window.c.get(url)
        if status == 200:
            self.fill_menu(res)
            self.has_more = len(res.get("data", [])) >= self.per_page
        else:
            status_pane = self.window.get("status")
            if status_pane:
                status_pane.status = str(res)

    def fetch_more(self):
        if not self.items:
            return
        cursor = self.items[-1][4]
        if self.feed_context:
            group, name = self.feed_context
            url = "feeds/%s/%s/articles?per_page=%i&before=%s" % (group, name, self.per_page, cursor)
        else:
            url = "articles?per_page=%i&before=%s" % (self.per_page, cursor)
        (res, status) = self.window.c.get(url)
        if status != 200:
            self.has_more = False
            return
        new_data      = res.get("data", [])
        existing_uids = {item[2] for item in self.items}
        for r in new_data:
            if 'uid' not in r or r['uid'] in existing_uids:
                continue
            self.items.append([
                0, r['title'], r['uid'], r['content_available'],
                r.get('created', 0)
            ])
        self.has_more = len(new_data) >= self.per_page

    def fill_menu(self, res):
        self.items    = []
        self.content  = []
        self.offset   = 0
        self.has_more = False
        for r in res["data"]:
            if 'uid' not in r:
                continue
            self.items.append([
                0, r['title'], r['uid'], r['content_available'],
                r.get('created', 0)
            ])
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
        lines   = self.data.split('\n')
        max_pos = max(0, len(lines) - 1)
        if character == 259:    # Up arrow
            self.position = max(0, self.position - 1)
        elif character == 258:  # Down arrow
            self.position = min(max_pos, self.position + 1)
        elif character == 339:  # Page up
            self.position = max(0, self.position - self.height)
        elif character == 338:  # Page down
            self.position = min(max_pos, self.position + self.height)
        elif character == 262:  # Home
            self.position = 0
        elif character == 360:  # End
            self.position = max_pos

        elif character in [260, 9]:  # Left arrow or tab
            articles = self.window.get("articles")
            articles.active = True
            self.active = False

        elif character in [70, 102]:  # f/F to fullscreen the pager
            articles = self.window.get("articles")
            feeds    = self.window.get("feeds")
            if articles.hidden:
                articles.hidden = False
                if feeds and getattr(self, '_feeds_was_visible', False):
                    feeds.hidden = False
            else:
                self._feeds_was_visible = feeds and not feeds.hidden
                articles.hidden = True
                if feeds:
                    feeds.hidden = True

class StatusLine(Pane):
    geometry  = [EXPAND, 1]
    content   = []
    buffer    = ""
    status    = ""
    searching = False
    tagline   = "Thanks God."

    def update(self):
        feeds = self.window.get("feeds")
        if self.searching:
            self.change_content(0, "/" + self.buffer, palette("black", "white"))
        elif feeds and feeds.searching:
            self.change_content(0, "/" + feeds.search_buf, palette("black", "white"))
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

                try:
                    import anthropic as _anthropic
                    import json as _json

                    _c      = self.window.c
                    _client = _anthropic.Anthropic()
                    _model  = "claude-sonnet-4-5"

                    _articles_pane = self.window.panes[1][2]
                    _current_items = _articles_pane.items if _articles_pane else []

                    _system = (
                        "You are a research assistant embedded in a terminal RSS reader called Harvest. "
                        "You have tools to list, search, and read articles from the user's feeds. "
                        "The user's current article list has %d items. "
                        "Never use markdown formatting unless explicitly asked. "
                        "Respond in plain prose only. "
                        "When the user says 'my current' or refers to their current article or current articles list, use the read_current tool. "
                        "When the user says 'read me ...' or 'read ... to me', use the cat tool to print the content directly to the user." % len(_current_items)
                    )

                    _tools = [
                        {
                            "name": "read_current",
                            "description": "Fetch the full content of the article currently selected in the user's article list. Use this when the user refers to 'my current' article or 'my current articles list'.",
                            "input_schema": {"type": "object", "properties": {}},
                        },
                        {
                            "name": "cat",
                            "description": "Print text directly to the user's terminal. Use this when the user says 'read me ...' or 'read ... to me'.",
                            "input_schema": {
                                "type": "object",
                                "properties": {
                                    "text": {"type": "string"},
                                },
                                "required": ["text"],
                            },
                        },
                        {
                            "name": "feeds",
                            "description": "List all feed groups and the feeds within them, including each feed's name and group.",
                            "input_schema": {"type": "object", "properties": {}},
                        },
                        {
                            "name": "list",
                            "description": (
                                "List articles. Without group/feed returns articles across all feeds. "
                                "With group and feed returns articles only from that feed. "
                                "Use the feeds tool first to discover valid group and feed names."
                            ),
                            "input_schema": {
                                "type": "object",
                                "properties": {
                                    "group":    {"type": "string", "description": "Feed group name"},
                                    "feed":     {"type": "string", "description": "Feed name"},
                                    "page":     {"type": "integer", "default": 1},
                                    "per_page": {"type": "integer", "default": 50},
                                },
                            },
                        },
                        {
                            "name": "search",
                            "description": "Search article titles for the given terms.",
                            "input_schema": {
                                "type": "object",
                                "properties": {
                                    "terms": {"type": "string"},
                                },
                                "required": ["terms"],
                            },
                        },
                        {
                            "name": "read",
                            "description": "Fetch the full content of an article by its UID.",
                            "input_schema": {
                                "type": "object",
                                "properties": {
                                    "uid": {"type": "string"},
                                },
                                "required": ["uid"],
                            },
                        },
                    ]

                    def _run_tool(name, inp):
                        if name == "read_current":
                            selected = next((it for it in _articles_pane.items if it[0]), None)
                            if not selected:
                                return {"error": "no article selected"}
                            res, st = _c.get("articles/%s" % selected[2])
                            return res if st == 200 else {"error": st}
                        elif name == "cat":
                            print(inp.get("text", ""))
                            return {}
                        elif name == "feeds":
                            res, st = _c.get("feeds?per_page=100")
                            if st != 200:
                                return {"error": st}
                            return [
                                {"group": g["name"], "feeds": [f["name"] for f in g.get("feeds", [])]}
                                for g in res.get("data", [])
                            ]
                        elif name == "list":
                            group = inp.get("group")
                            feed  = inp.get("feed")
                            page     = inp.get("page", 1)
                            per_page = inp.get("per_page", 50)
                            if group and feed:
                                url = "feeds/%s/%s/articles?page=%d&per_page=%d" % (group, feed, page, per_page)
                            else:
                                url = "articles?page=%d&per_page=%d" % (page, per_page)
                            res, st = _c.get(url)
                        elif name == "search":
                            res, st = _c.get("articles/search/%s?per_page=50" % inp["terms"])
                        elif name == "read":
                            res, st = _c.get("articles/%s" % inp["uid"])
                        else:
                            return {"error": "unknown tool"}
                        return res if st == 200 else {"error": st}

                    def claude(prompt, model=_model):
                        """Send a single prompt to Claude and return the response text."""
                        r = _client.messages.create(
                            model=model, max_tokens=8096, system=_system,
                            messages=[{"role": "user", "content": prompt}],
                        )
                        return r.content[0].text

                    def chat(model=_model):
                        """Turn-based chat with Claude. Claude can use list, search, read tools."""
                        messages = []
                        print("\nChatting with Claude (tools: list, search, read). Empty input or ^D to quit.\n")
                        while True:
                            try:
                                user_input = input(format(_c.get("articles/count")[0], ",") + "> ").strip()
                            except (EOFError, KeyboardInterrupt):
                                print()
                                break
                            if not user_input:
                                break
                            messages.append({"role": "user", "content": user_input})
                            while True:
                                r = _client.messages.create(
                                    model=model, max_tokens=8096, system=_system,
                                    tools=_tools, messages=messages,
                                )
                                tool_uses  = [b for b in r.content if b.type == "tool_use"]
                                text_parts = [b.text for b in r.content if b.type == "text"]
                                if text_parts:
                                    print("claude> " + "\n".join(text_parts) + "\n")
                                messages.append({"role": "assistant", "content": r.content})
                                if r.stop_reason != "tool_use" or not tool_uses:
                                    break
                                results = []
                                for tu in tool_uses:
                                    print("[tool: %s %s]" % (tu.name, tu.input))
                                    results.append({
                                        "type":        "tool_result",
                                        "tool_use_id": tu.id,
                                        "content":     _json.dumps(_run_tool(tu.name, tu.input)),
                                    })
                                messages.append({"role": "user", "content": results})

                    l["claude"] = claude
                    l["chat"]   = chat
                except ImportError:
                    pass

                self.window.stop()
                print("\nStarting REPL. ^D to exit.")
                embed(locals=l, configure=configure)
                self.window.start()
            except ImportError:
                pass

        if not self.searching and character == 47:  # / to search articles
            # Don't enter article search if the feeds panel has focus
            feeds = self.window.get("feeds")
            if feeds and not feeds.hidden and feeds.active:
                return
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

titlebar        = TitleBar("titlebar")
feedgroups      = FeedGroups("feedgroups")
feedgroups.hidden = True
feeds           = Feeds("feeds")
articles        = Articles("articles")
reader          = Reader("reader")
reader.wrap     = True
articles.reader = reader
status          = StatusLine("status")

window.add(titlebar)
panes = [feedgroups, feeds, articles, reader]
window.add(panes)
window.add(status)

# init_pane sets all panes active=True; explicitly set focus state after add
feedgroups.active = False
feeds.active      = False
feeds.hidden      = True
reader.active     = False

window.exit_keys.append(4)  # ^D to exit
