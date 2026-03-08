"""
This file provides a generic logging class.
It could do with automatic file rotation and syslog support.

Luke Brooks 2015
MIT License.
"""
import logging, time

class Log(object):
    def __init__(self, program, log_file=None, log_stdout=False):
        self.program = program
        self.log = None
        self.debug = False

        if log_file or log_stdout:
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s', '%d/%m/%Y %H:%M:%S'
            )
            self.log = logging.getLogger(program)
            self.log.setLevel(logging.DEBUG)

            if log_stdout:
                ch = logging.StreamHandler()
                ch.setLevel(logging.DEBUG)
                ch.setFormatter(formatter)
                self.log.addHandler(ch)

            if log_file:
                ch = logging.FileHandler(log_file, 'a')
                ch.setLevel(logging.DEBUG)
                ch.setFormatter(formatter)
                self.log.addHandler(ch)

    def __call__(self, data, level='info'):
        if self.log:
            if level == 'debug':    level = 10
            if level == 'info':     level = 20
            if level == 'warning':  level = 30
            if level == 'error':    level = 40
            if level == 'critical': level = 50

            if (level > 15) or (self.debug):
                self.log.log(level, data)
