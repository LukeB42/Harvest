#!/usr/bin/env python
# _*_ coding: utf-8 _*_

import os
import sys
import asyncio
import argparse
import signal

import uvloop
import tornado.wsgi
import tornado.httpserver

from harvest import app, init, db
from harvest.models import APIKey
from harvest.controllers.log import Log
from harvest.controllers.scripts import Scripts
from harvest.controllers.load import parse_crontab
from harvest.controllers.manager import FeedManager

try:
    import setproctitle
    setproctitle.setproctitle("harvest")
except ImportError:
    pass

def export_crontab(filename):
    """
    Defined here to prevent circular imports.
    """
    crontab = ""
    fd = open(filename, "w")
    keys = [k for k in APIKey.query.all() if not k.reader]
    for key in keys:
        crontab += "apikey: %s\n\n" % key.key
        for feed in key.feeds:
            crontab += '%s "%s" "%s" %s\n' % (feed.url, feed.name, feed.group.name, feed.schedule)
        crontab += '\n\n'
    fd.write(crontab)
    fd.close()

async def main(options):
    # Push a persistent app context for the lifetime of the process.
    # FeedManager coroutines run within this context.
    ctx = app.app_context()
    ctx.push()

    if options.config:
        app.config.from_object(options.config)

    app.debug = options.debug

    log = Log("Harvest", log_file=options.logfile, log_stdout=True)
    log.debug = options.debug
    app.log = log

    log("Starting Harvest %s." % app.version)

    # Create the database schema and insert an administrative key.
    init()

    if options.crontab:
        parse_crontab(options.crontab)
        return

    if options.export:
        try:
            export_crontab(options.export)
            log('Crontab written to "%s".' % options.export)
        except Exception as e:
            log('Error writing crontab: %s' % str(e))
        return

    # Load scripts.
    app.scripts = Scripts(options.scripts_dir)
    app.scripts.reload()

    # Trap SIGHUP to reload scripts.
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGHUP, app.scripts.reload)

    # Initialise the feed manager and load feeds.
    fm = FeedManager(log)
    fm.db  = db
    fm.app = app
    fm.load_feeds()
    app.feedmanager = fm

    # Start all feed crontabs as asyncio tasks.
    fm.start_all()

    # Schedule the monitor coroutine.
    asyncio.create_task(fm.run())

    # Set up Tornado to serve the Flask WSGI app.
    container = tornado.wsgi.WSGIContainer(app)

    ssl_options = None
    if options.key and options.cert:
        if '~' in options.cert:
            options.cert = os.path.expanduser(options.cert)
        if '~' in options.key:
            options.key  = os.path.expanduser(options.key)
        if not os.path.isfile(options.cert):
            sys.exit("Certificate not found at %s" % options.cert)
        if not os.path.isfile(options.key):
            sys.exit("Key not found at %s" % options.key)
        ssl_options = {"certfile": options.cert, "keyfile": options.key}

    httpd = tornado.httpserver.HTTPServer(container, ssl_options=ssl_options)
    httpd.listen(int(options.port), address=options.address)
    log("Binding to %s:%s" % (options.address, options.port))

    stop_event = asyncio.Event()
    loop.add_signal_handler(signal.SIGINT,  stop_event.set)
    loop.add_signal_handler(signal.SIGTERM, stop_event.set)

    await stop_event.wait()

    log("Stopping...")
    httpd.stop()
    for task in list(fm.tasks.values()):
        task.cancel()
    await asyncio.gather(*fm.tasks.values(), return_exceptions=True)
    fm.tasks.clear()

def cli():
    prog        = "Harvest"
    description = "A microservice for archiving the news."
    epilog      = "Float64."

    parser = argparse.ArgumentParser(prog=prog, description=description, epilog=epilog)
    parser.add_argument("-c", "--crontab",   dest="crontab",    default=None,
                        help="Crontab to parse")
    parser.add_argument("--config",          dest="config",     default=None,
                        help="(defaults to harvest.config)")
    parser.add_argument("-a", "--address",   dest="address",    default='0.0.0.0',
                        help="(defaults to 0.0.0.0)")
    parser.add_argument("-p", "--port",      dest="port",       default='6362',
                        help="(defaults to 6362)")
    parser.add_argument("--key",             dest="key",        default=None,
                        help="SSL key file")
    parser.add_argument("--cert",            dest="cert",       default=None,
                        help="SSL certificate")
    parser.add_argument("--export",          dest="export",     default=None,
                        help="Write out current database as a crontab")
    parser.add_argument("--logfile",         dest="logfile",    default="harvest.log",
                        help="(defaults to ./harvest.log)")
    parser.add_argument("--debug",           dest="debug",      action="store_true", default=False,
                        help="Log to stdout")
    parser.add_argument("--scripts-dir",     dest="scripts_dir", default="scripts",
                        help="(defaults to ./scripts/)")
    parser.add_argument("--repl",            dest="repl",        action="store_true", default=False,
                        help="Start an interactive REPL")
    parser.add_argument("--ncurses",         dest="ncurses",     action="store_true", default=False,
                        help="Start the ncurses TUI")
    options = parser.parse_args()

    if options.repl or options.ncurses:
        from harvest.repl import start
        from harvest.models import APIKey

        address = '127.0.0.1' if options.address == '0.0.0.0' else options.address
        url = 'https://%s:%s/v1/' % (address, options.port)

        api_key = os.environ.get('HARVEST_API_KEY', '')
        if not api_key:
            try:
                ctx = app.app_context()
                ctx.push()
                master = APIKey.query.filter_by(
                    name=app.config['MASTER_KEY_NAME']
                ).first()
                if master:
                    api_key = master.key
            except Exception:
                pass

        start(url, api_key, ncurses=options.ncurses)
        return

    uvloop.install()
    asyncio.run(main(options))
