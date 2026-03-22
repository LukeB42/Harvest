# -*- coding: utf-8 -*-
# Defines a simple ncurses window, an event loop and some panes.
import locale
import time
import unicodedata
import _curses

VERSION = "0.0.4"

# Initialise locale so curses can render arbitrary UTF-8 characters.
locale.setlocale(locale.LC_ALL, "")

FIT          = "FIT"           # pane axis hugs its content
EXPAND       = "EXPAND"        # stretch on axis as much as possible

ALIGN_LEFT   = "ALIGN_LEFT"   # values for the align argument to Pane.change_content
ALIGN_RIGHT  = "ALIGN_RIGHT"
ALIGN_CENTER = "ALIGN_CENTER"


def display_width(text):
    """
    Return the number of terminal columns required to display *text*.
    Full-width (F) and Wide (W) Unicode characters each occupy two columns;
    combining / zero-width characters occupy zero columns.
    All other characters occupy one column.
    """
    width = 0
    for ch in text:
        eaw = unicodedata.east_asian_width(ch)
        if eaw in ("W", "F"):
            width += 2
        elif unicodedata.category(ch) in ("Mn", "Cf", "Me"):
            pass   # combining / zero-width
        else:
            width += 1
    return width


def truncate_to_display_width(text, max_cols):
    """Return the longest prefix of *text* whose display width <= *max_cols*."""
    width = 0
    out   = []
    for ch in text:
        eaw = unicodedata.east_asian_width(ch)
        if eaw in ("W", "F"):
            ch_w = 2
        elif unicodedata.category(ch) in ("Mn", "Cf", "Me"):
            ch_w = 0
        else:
            ch_w = 1
        if width + ch_w > max_cols:
            break
        out.append(ch)
        width += ch_w
    return "".join(out)


class WindowError(Exception):
    def __init__(self, message):
        self.message = message
    def __str__(self):
        return repr(self.message)


class PaneError(Exception):
    def __init__(self, message):
        self.message = message
    def __str__(self):
        return repr(self.message)


class Window(object):
    """
    A window can have multiple panes responsible for different things.
    This object filters input characters through the .process_input() method on all
    panes marked as active.

    The list of panes orders panes vertically from highest to lowest.
    Elements in the list of panes can also be lists of panes ordered left to right.

    Set blocking=True to wait for input before redrawing the screen.
    Set debug=True to draw exception messages and print character codes on the last line.

    In non-blocking mode a default delay of 0.030 s is used to avoid hogging the CPU.
    Higher values can be used for wall clocks, etc.
    """
    def __init__(self, blocking=True):
        self.blocking   = blocking
        self.running    = None
        self.debug      = None
        self.window     = None
        self.height     = None
        self.width      = None
        self.panes      = []
        self.pane_cache = []
        self.exit_keys  = []
        self.friendly   = True
        self.delay      = 0.030

    def start(self):
        """Window event loop."""
        self.window = _curses.initscr()
        _curses.savetty()
        _curses.start_color()
        _curses.use_default_colors()
        self.window.leaveok(1)
        _curses.raw()
        self.window.keypad(1)
        _curses.noecho()
        _curses.cbreak()
        _curses.nonl()
        _curses.curs_set(0)
        if self.blocking:
            self.window.nodelay(0)
        else:
            self.window.nodelay(1)
        self.running = True
        try:
            while self.running:
                self.cycle()
                if self.friendly and not self.blocking:
                    time.sleep(self.delay)
        finally:
            self.stop()

    def cycle(self):
        """
        Permits composition with asyncio / your own event loop::

            while True:
                sockets.poll()
                update_with_network_data(window)
                window.cycle()
        """
        self.draw()
        self.process_input()

    def stop(self):
        """Restore the TTY to its original state."""
        if not self.window:
            return
        try:
            _curses.curs_set(1)
        except _curses.error:
            pass
        _curses.nocbreak()
        self.window.keypad(0)
        _curses.echo()
        _curses.resetty()
        _curses.endwin()
        self.running = False
        self.window = None

    def draw(self):
        self.update_window_size()
        self.calculate_pane_heights_and_widths()
        self.coordinate()
        [pane.update() for pane in self if not pane.hidden]

        for pane in self:
            if pane.hidden:
                continue

            top_left_top      = pane.coords[0][0][0]
            top_left_left     = pane.coords[0][0][1]
            top_right_top     = pane.coords[0][1][0]
            top_right_left    = pane.coords[0][1][1]
            bottom_left_top   = pane.coords[1][0][0]
            bottom_left_left  = pane.coords[1][0][1]
            bottom_right_top  = pane.coords[1][1][0]
            bottom_right_left = pane.coords[1][1][1]

            pane_draw_width = top_right_left - top_left_left

            y = 0
            x = 0

            for frame in pane.content:
                (text, align, attrs) = frame

                for i, line in enumerate(text.split("\n")):

                    if (i + y) > (bottom_left_top - top_left_top):
                        break

                    dw = display_width(line)

                    if not pane.wrap:
                        # -------------------------------------------------------- #
                        # Alignment: set x offset within the pane before clipping  #
                        # -------------------------------------------------------- #
                        if align == ALIGN_RIGHT:
                            x = max(0, pane_draw_width - dw)
                        elif align == ALIGN_CENTER:
                            x = max(0, (pane_draw_width - dw) // 2)
                        else:
                            x = 0

                        # Maximum columns available from current x position
                        max_cols = pane_draw_width - x

                        # Honour inverted corners
                        if top_right_top > top_left_top or top_right_left < bottom_right_left:
                            if y >= top_right_top:
                                if bottom_left_top < bottom_right_top and y >= bottom_left_top:
                                    max_cols = min(max_cols, top_right_left - bottom_left_left - x)
                                else:
                                    max_cols = min(max_cols, top_right_left - top_left_left - x)

                        if bottom_right_top < bottom_left_top or top_right_left > bottom_right_left:
                            if y >= bottom_right_top:
                                if top_left_top > top_right_top and y >= top_left_top:
                                    max_cols = min(max_cols, bottom_right_left - top_left_left - x)
                                else:
                                    max_cols = min(max_cols, bottom_right_left - bottom_left_left - x)

                        if top_left_left > bottom_left_left or top_left_top > top_right_top:
                            if y >= top_left_top:
                                if bottom_right_top < bottom_left_top and y >= bottom_right_top:
                                    max_cols = min(max_cols, bottom_right_left - top_left_left - x)
                                else:
                                    max_cols = min(max_cols, top_right_left - top_left_left - x)

                        if bottom_left_left > top_left_left:
                            if y >= bottom_left_top:
                                if top_right_top > top_left_top and y <= top_right_top:
                                    max_cols = min(max_cols, top_right_left - bottom_left_left - x)
                                else:
                                    max_cols = min(max_cols, bottom_right_left - bottom_left_left - x)

                        # Global window right-edge guard
                        max_cols = min(max_cols, self.width - (top_left_left + x))

                        if max_cols < 1:
                            x = 0
                            continue

                        line = truncate_to_display_width(line, max_cols)

                    else:
                        # ---- word / char wrapping ---- #
                        x = 0
                        pane_width = top_right_left - top_left_left
                        if dw > pane_width:
                            if pane.wrap == 1 or pane.wrap is True:
                                words = line.split()
                            else:
                                words = list(line)

                            for c, j in enumerate(words):
                                if y > bottom_left_top - top_left_top:
                                    break
                                if c and isinstance(words, list) and pane.wrap == 1:
                                    j = ' ' + j
                                jw = display_width(j)
                                if top_left_left + x + jw > top_right_left:
                                    y += 1
                                    x  = 0
                                    if len(j) > 1 and j[0] == ' ':
                                        j = j[1:]
                                    jw = display_width(j)
                                    avail = top_right_left - top_left_left - x
                                    if jw > avail:
                                        if not c:
                                            y -= 1
                                        t = truncate_to_display_width('...', avail)
                                        self.addstr(top_left_top + i + y, top_left_left + x, t, attrs)
                                        continue
                                self.addstr(top_left_top + i + y, top_left_left + x, j, attrs)
                                x += display_width(j)

                            x = 0
                            continue
                        else:
                            # Line fits — still clip it to the pane width
                            line = truncate_to_display_width(line, pane_width - x)

                    # ---- draw ---- #
                    if top_left_top > top_right_top and y >= top_left_top:
                        self.addstr(top_left_top + i + y, bottom_left_left + x, line, attrs)
                    elif bottom_left_top < bottom_right_top and y >= bottom_left_top:
                        self.addstr(top_left_top + i + y, bottom_left_left + x, line, attrs)
                    else:
                        self.addstr(top_left_top + i + y, top_left_left + x, line, attrs)
                    x = 0

                x = display_width(line)
                y += i

    def process_input(self):
        try:
            character = self.window.getch()
        except Exception as e:
            character = -1
            if self.debug:
                msg = str(e)
                self.addstr(self.height - 1, self.width - len(msg) + 1, msg)

        if character in self.exit_keys:
            self.stop()
            return

        if character == 12:    # ^L — force redraw
            self.window.clear()
            return

        if character != -1:
            for pane in [p for p in self if p.active]:
                pane.process_input(character)

            if self.debug:
                self.addstr(self.height - 1, self.width // 2, "    ")
                s = str(character)
                self.addstr(self.height - 1, self.width // 2 - len(s) // 2, s)

    def calculate_pane_heights_and_widths(self):
        """
        Update pane heights and widths based on the window size and each pane's
        desired geometry (int, FIT, or EXPAND).
        """
        # ---- height pass ---- #
        growing_panes   = []
        claimed_columns = 0

        for v_index, element in enumerate(self.panes):
            if type(element) == list:
                expanding_in_sublist = []
                claimed_from_sublist = []

                for h_index, pane in enumerate(element):
                    if pane.hidden:
                        continue
                    if pane.coords and pane.self_coordinating:
                        pane.height = max(pane.coords[1][0][0], pane.coords[1][1][0])
                        claimed_from_sublist.append(pane.height)
                        continue
                    if len(pane.geometry) < 2:
                        pane.height = 0
                        continue

                    desired = pane.geometry[1]
                    if isinstance(desired, int):
                        pane.height = desired
                        claimed_from_sublist.append(pane.height)
                    elif desired == FIT:
                        buf = "".join(f[0] for f in pane.content)
                        pane.height = len(buf.split('\n'))
                        claimed_from_sublist.append(pane.height)
                    elif desired == EXPAND:
                        expanding_in_sublist.append(pane)
                    else:
                        pane.height = desired

                if expanding_in_sublist:
                    growing_panes.append(expanding_in_sublist)
                if claimed_from_sublist:
                    claimed_columns += max(claimed_from_sublist)

            else:
                if element.hidden:
                    continue
                if element.coords and element.self_coordinating:
                    element.height = max(element.coords[1][0][0], element.coords[1][1][0])
                    claimed_columns += element.height
                    continue
                if len(element.geometry) < 2:
                    element.height = 0
                    continue

                desired = element.geometry[1]
                if isinstance(desired, int):
                    element.height = desired
                    claimed_columns += element.height
                elif desired == FIT:
                    buf = "".join(f[0] for f in element.content)
                    element.height = len(buf.split('\n'))
                    claimed_columns += element.height
                elif desired == EXPAND:
                    growing_panes.append(element)

        if growing_panes:
            g = len(growing_panes)
            remaining = self.height - claimed_columns
            share     = remaining // g
            rmg       = remaining % g

            for i, pane in enumerate(growing_panes):
                if isinstance(pane, list):
                    for k, p in enumerate(pane):
                        p.height = share
                        if not i:
                            for x in range(g):
                                if rmg == x:
                                    p.height -= g - (x + 1)
                            if self.height % 2:
                                p.height += (1 if not claimed_columns else -claimed_columns)
                            else:
                                p.height -= claimed_columns
                else:
                    pane.height = share
                    if not i:
                        for x in range(g):
                            if rmg == x:
                                pane.height -= g - (x + 1)
                        if self.height % 2:
                            pane.height += (1 if not claimed_columns else -claimed_columns)
                        else:
                            pane.height -= claimed_columns

        # ---- width pass ---- #
        for v_index, element in enumerate(self.panes):
            claimed_rows  = 0
            growing_panes = []

            if type(element) == list:
                for h_index, pane in enumerate(element):
                    if pane.hidden:
                        continue
                    if pane.coords and pane.self_coordinating:
                        pane.width = max(pane.coords[0][1][1], pane.coords[1][1][1])
                        continue
                    if not pane.geometry:
                        pane.width = 0
                        continue

                    desired = pane.geometry[0]
                    if isinstance(desired, int):
                        pane.width    = desired
                        claimed_rows += desired
                    elif desired == FIT:
                        buf = "".join(f[0] for f in pane.content)
                        pane.width    = max(display_width(l) for l in buf.split('\n')) if buf else 0
                        claimed_rows += pane.width
                    elif desired == EXPAND:
                        growing_panes.append(pane)
            else:
                if element.hidden:
                    continue
                if element.coords and element.self_coordinating:
                    element.width = max(element.coords[0][1][1], element.coords[1][1][1])
                    continue
                if not element.geometry:
                    element.width = 0
                    continue

                desired = element.geometry[0]
                if isinstance(desired, int):
                    element.width = desired
                elif desired == FIT:
                    buf = "".join(f[0] for f in element.content)
                    element.width = max(display_width(l) for l in buf.split('\n')) if buf else 0
                elif desired == EXPAND:
                    element.width = self.width

            if growing_panes:
                share = (self.width - claimed_rows) // len(growing_panes)
                for pane in growing_panes:
                    pane.width = share

        # Give the rightmost EXPAND pane an extra column on odd-width terminals
        if self.width % 2:
            for pane in self.panes:
                if isinstance(pane, list):
                    for i, p in enumerate(reversed(pane)):
                        if i == 0 and not p.self_coordinating and p.geometry \
                                and p.geometry[0] == EXPAND and not p.hidden:
                            p.width += 1
                else:
                    if not pane.self_coordinating and pane.geometry \
                            and pane.geometry[0] == EXPAND and not pane.hidden:
                        pane.width += 1

        if self.debug:
            self.addstr(self.height - 5, 0, "Window height: " + str(self.height))
            self.addstr(self.height - 4, 0, "Window width:  " + str(self.width))
            self.addstr(self.height - 2, 0, "Heights: " + str([p.height for p in self]))
            self.addstr(self.height - 1, 0, "Widths:  " + str([p.width  for p in self]))

    def coordinate(self, panes=[], index=0):
        """
        Assign coordinate tuples to every pane based on heights and widths.
        """
        y = 0
        for i, element in enumerate(self.panes):
            x = 0
            if isinstance(element, list):
                current_height = 0
                for j, pane in enumerate(element):
                    if pane.hidden:
                        continue
                    cw = pane.width
                    ch = pane.height
                    current_height = ch
                    pane.coords = [
                        ((y, x),          (y, x + cw)),
                        ((y + (ch if ch > 1 else 0), x),
                         (y + (ch if ch > 1 else 0), x + cw)),
                    ]
                    x += cw
                y += (current_height + 1 if current_height > 1 else 1)
            else:
                if element.hidden:
                    continue
                cw = element.width
                ch = element.height
                element.coords = [
                    ((y, x),          (y, x + cw)),
                    ((y + (ch if ch > 1 else 0), x),
                     (y + (ch if ch > 1 else 0), x + cw)),
                ]
                y += (ch + 1 if ch > 1 else 1)

            if self.debug:
                coords = "Coordinates: " + str([p.coords for p in self])
                self.addstr(self.height - 3, 0, coords[:self.width])

    def addstr(self, h, w, text, attrs=0):
        """
        Safe addstr wrapper.  Handles arbitrary UTF-8 text via locale settings.
        """
        self.update_window_size()
        if h >= self.height or w >= self.width:
            return
        max_cols = self.width - w
        if max_cols <= 0:
            return
        text = truncate_to_display_width(text, max_cols)
        try:
            self.window.addstr(h, w, text, attrs)
        except Exception:
            pass

    def update_window_size(self):
        height, width = self.window.getmaxyx()
        if self.height != height or self.width != width:
            self.height, self.width = height, width
            self.window.clear()

    def add(self, pane):
        if isinstance(pane, list):
            self.panes.append([self.init_pane(p) for p in pane])
        else:
            self.panes.append(self.init_pane(pane))

    def init_pane(self, pane):
        if not pane.name:
            raise PaneError("Unnamed pane.")
        pane.active = True
        pane.window = self
        for existing in self:
            if existing.name == pane.name:
                raise WindowError("A pane is already attached with the name %s" % pane.name)
        return pane

    def block(self):
        self.blocking = True
        self.window.nodelay(0)

    def unblock(self):
        self.blocking = False
        self.window.nodelay(1)

    def get(self, name, default=None, cache=False):
        """Get a pane by name.  Returns *default* if not found."""
        if cache:
            for pane in self.pane_cache:
                if pane.name == name:
                    return pane
            return default
        for pane in self:
            if pane.name == name:
                return pane
        return default

    def __setitem__(self, name, new_pane):
        for i, pane in enumerate(self.panes):
            if not isinstance(pane, list):
                if pane.name == name:
                    self.panes[i] = new_pane
                    return
            else:
                for x, hp in enumerate(pane):
                    if hp.name == name:
                        self.panes[i][x] = new_pane
                        return
        raise KeyError("Unknown pane %s" % name)

    def __getitem__(self, name):
        for pane in self:
            if pane.name == name:
                return pane
        raise KeyError("Unknown pane %s" % name)

    def __len__(self):
        return len(list(self.__iter__()))

    def __iter__(self):
        panes = []
        for pane in self.panes:
            if type(pane) == list:
                panes.extend(pane)
            else:
                panes.append(pane)
        return iter(panes)


# ---------------------------------------------------------------------------
# Colour helper
# ---------------------------------------------------------------------------

def palette(fg, bg=-1):
    """
    Memoised colour-pair factory.
    Pass colour names as strings ("red", "blue", …) or curses colour ints.
    -1 means terminal default.
    """
    if not hasattr(palette, "counter"):
        palette.counter    = 1
        palette.selections = {}

    key = "%s%s" % (fg, bg)
    if key not in palette.selections:
        palette.selections[key] = palette.counter
        palette.counter += 1

    if isinstance(fg, str):
        fg = getattr(_curses, "COLOR_" + fg.upper(), -1)
    if isinstance(bg, str):
        bg = getattr(_curses, "COLOR_" + bg.upper(), -1)

    _curses.init_pair(palette.selections[key], fg, bg)
    return _curses.color_pair(palette.selections[key])


# ---------------------------------------------------------------------------
# Base Pane
# ---------------------------------------------------------------------------

class Pane(object):
    """
    Subclassable data and logic for window panes.

    geometry = [width, height]  — each axis may be an int, FIT, or EXPAND.

    content  = [[text, align, attrs], …]  — rendered contiguously.

    wrap = 1 → word-wrap   |   wrap = 2 → character-wrap   |   wrap = None → clip
    """
    name              = ''
    window            = None
    active            = None
    geometry          = []
    coords            = []
    content           = []
    height            = None
    width             = None
    attr              = None
    floating          = None
    self_coordinating = None
    wrap              = None
    hidden            = None

    def __init__(self, name):
        self.name    = name
        self.content = []

    def process_input(self, character):
        func = None
        try:
            func = getattr(self, "handle_%s" % chr(character), None)
        except Exception:
            pass
        if func:
            func()

    def update(self):
        pass

    def __iadd__(self, data):
        if isinstance(data, str):
            if self.content:
                self.content[0][0] += data
            else:
                self.change_content(0, data, align=ALIGN_LEFT, attrs=1)
        elif isinstance(data, (tuple, list)):
            if len(data) < 2 or not isinstance(data[0], int):
                return self
            if len(self.content) < data[0] + 1:
                self.change_content(data[0], data[1], align=ALIGN_LEFT, attrs=1)
                return self
            self.content[data[0]][0] += data[1]
        return self

    def change_content(self, index, text, align=ALIGN_LEFT, attrs=1):
        if index > len(self.content) and self.content:
            return
        if not self.content or index == len(self.content):
            self.content.append([text, align, attrs])
        else:
            self.content[index] = [text, align, attrs]

    def __repr__(self):
        if self.name:
            return "<Pane %s at %s>" % (self.name, hex(id(self)))
        return "<Pane at %s>" % hex(id(self))


# ---------------------------------------------------------------------------
# TabBar — single-row horizontal tab strip
# ---------------------------------------------------------------------------

class TabBar(Pane):
    """
    A single-line horizontal tab strip that provides a tabs-like interface
    by hiding/showing sibling panes.

    Usage::

        bar   = TabBar("tabs")
        pane_a = MyPane("panel_a")
        pane_b = MyPane("panel_b")

        window.add(bar)
        window.add(pane_a)
        window.add(pane_b)

        # Register tabs *after* window.add() so pane references are live
        bar.register("Alpha", pane_a)
        bar.register("Beta",  pane_b)
        bar.select(0)   # show first tab

    Keys:  ← / h   move left    |    → / l   move right
           Tab / Enter / Space   activate focused tab
    """
    geometry = [EXPAND, 1]

    col_normal   = (-1,       -1)       # (fg, bg) for unselected tabs
    col_selected = ("black", "white")   # (fg, bg) for selected tab

    def __init__(self, name):
        super().__init__(name)
        self._tabs    = []   # list of [label, pane]
        self.selected = 0

    def register(self, label, pane):
        """Register *pane* as a tab with the given *label*."""
        self._tabs.append([label, pane])

    def select(self, index):
        """Show the pane at *index*, hide all others."""
        if not self._tabs:
            return
        self.selected = index % len(self._tabs)
        for i, (_, pane) in enumerate(self._tabs):
            pane.hidden = (i != self.selected)
            pane.active = (i == self.selected)
        if self.window and self.window.window:
            self.window.window.clear()

    def update(self):
        if not self._tabs:
            return
        self.content = []
        col = 0
        for i, (label, _) in enumerate(self._tabs):
            text  = "  %s  " % label
            attrs = palette(*self.col_selected) if i == self.selected \
                    else palette(*self.col_normal)
            # Pad the final segment to fill the bar
            if i == len(self._tabs) - 1 and self.width:
                text = text + " " * max(0, self.width - col - display_width(text))
            self.content.append([text, ALIGN_LEFT, attrs])
            col += display_width(text)

    def process_input(self, character):
        if not self._tabs:
            return
        if character in (260, ord('h')):        # ← or h
            self.select(self.selected - 1)
        elif character in (261, ord('l')):       # → or l
            self.select(self.selected + 1)
        elif character in (9, 10, 13, 32):       # Tab / Enter / Space
            self.select(self.selected)


# ---------------------------------------------------------------------------
# Convenience subclasses
# ---------------------------------------------------------------------------

class Menu(Pane):
    """
    Vertical menu where items call local methods.
    items = [[selected_bool, label, method_name], ...]
    """
    geometry = [EXPAND, EXPAND]
    col = (-1, -1)
    sel = (-1, "blue")
    items = []

    def update(self):
        for i, item in enumerate(self.items):
            colours = palette(*self.sel) if item[0] else palette(*self.col)
            text  = ' ' + item[1]
            text += ' ' * max(0, self.width - display_width(text))
            self.change_content(i, text + '\n', ALIGN_LEFT, colours)

    def process_input(self, character):
        if character in (10, 13):
            for item in self.items:
                if item[0]:
                    func = getattr(self, item[2].lower(), None)
                    if func:
                        func()
        elif character in (259, 258, 339, 338):
            for i, item in enumerate(self.items):
                if item[0]:
                    if character == 259:
                        if i == 0: break
                        item[0] = 0; self.items[i - 1][0] = 1; break
                    if character == 258:
                        if i + 1 >= len(self.items): break
                        item[0] = 0; self.items[i + 1][0] = 1; break
                    if character == 339:
                        item[0] = 0; self.items[0][0] = 1; break
                    if character == 338:
                        item[0] = 0; self.items[-1][0] = 1; break


class Editor(Pane):
    """Simple text editor / input pane."""
    geometry = [EXPAND, EXPAND]
    buffer   = ""

    def update(self):
        if len(self.content) >= 1:
            self.change_content(1, "%i\n" % len(self.buffer))

    def process_input(self, character):
        self.window.window.clear()
        if character == 23 and self.buffer:
            self.buffer = ''
        elif character == 263 and self.buffer:
            self.buffer = self.buffer[:-1]
        elif character in (10, 13):
            self.buffer += "\n"
        else:
            try:
                self.buffer += chr(character)
            except Exception:
                pass
        import random
        colours = palette(-1, random.choice(["blue", "red"]))
        self.change_content(0, self.buffer, ALIGN_LEFT, colours)


class Pager(Pane):
    """Scrolling pager.  Set pager.data to the text to display."""
    geometry = [EXPAND, EXPAND]
    data     = ""
    position = 0

    def update(self):
        lines = self.data.split('\n')[self.position:]
        self.change_content(0, '\n'.join(lines))

    def process_input(self, character):
        self.window.window.clear()
        if character == 259:
            if self.position: self.position -= 1
        elif character == 258:
            self.position += 1
        elif character == 339:
            self.position = max(0, self.position - self.height)
        elif character == 338:
            total = len(self.data.split('\n'))
            if self.position + self.height < total:
                self.position += self.height
