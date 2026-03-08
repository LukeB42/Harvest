# _*_ coding: utf-8 _*_
# This file provides scripting capabilities
import os
import builtins
from harvest import app
from harvest.controllers.utils import sha1sum

class Scripts(object):

    def __init__(self, dir):
        self.dir = None
        self.scripts = {}

        dir = os.path.abspath(dir)
        if not os.path.isdir(dir):
            app.log("%s isn't a valid system path." % dir, "error")
            return

        self.dir = dir

    def reload(self, *args):  # args caught for signal handler
        if self.dir:
            if self.scripts:
                app.log("Reloading scripts.")
            for file in os.listdir(self.dir):
                self.unload(file)
                self.load(file)

    def load(self, file):
        file = os.path.abspath(os.path.join(self.dir, file))

        for script in self.scripts.values():
            if script.file == file:
                return

        if os.path.isfile(file):
            self.scripts[file] = Script(file)
            app.log("Loaded %s" % file)

    def unload(self, file):
        file = os.path.abspath(os.path.join(self.dir, file))

        if file in self.scripts:
            del self.scripts[file]


class Script(object):
    """
    Represents the execution environment for a third-party script.
    We send custom values into the environment and work with whatever's left.
    Scripts can also call any methods on objects put in their environment.
    """
    def __init__(self, file=None, env={}):
        self.read_on_exec = app.debug
        self.file = file
        self.env  = env
        self.script = ''
        self.code = None
        self.hash = None
        self.cache = {
            'app': app
        }

    def execute(self, env={}):
        if not self.code or self.read_on_exec:
            self.compile()
        if env:
            self.env = env
        self.env['cache'] = self.cache
        exec(self.code, self.env)
        del self.env['__builtins__']
        if 'cache' in self.env.keys():
            self.cache = self.env['cache']
        return self.env

    def compile(self, script=''):
        if self.file:
            with open(self.file, 'r') as f:
                self.script = f.read()
        elif script:
            self.script = script
        else:
            return
        hash = sha1sum(self.script)
        if self.hash != hash:
            self.hash = hash
            self.code = builtins.compile(self.script, self.file or '<string>', 'exec')
        self.script = ''

    def __getitem__(self, key):
        if key in self.env.keys():
            return self.env[key]
        else:
            raise KeyError(key)

    def keys(self):
        return self.env.keys()
