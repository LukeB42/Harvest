# _*_ coding: utf-8 _*_
#
# The structure of this package is essentially as follows
#
# models.py    Our abstractions for the types of data we persist to a database,
#              including how to represent columns and joins on other tables as singular
#              JSON documents. Handy for building list comprehensions of models.
# resources/   RESTful API endpoints for interacting with models over HTTP
# controllers/ Miscellaneous utilities used throughout the whole project
# run.py       A runner program that inserts a database schema if none is present,
#              binds to a network interface and changes UID if asked.
# repl.py      An interactive read-eval-print loop for working with the REST interface.
# config.py    Defines how to obtain a database URI.
"""
A democracy thing for researchers, programmers and news junkies who want personally curated news archives.
Harvest is a web content extractor that has a RESTful API and a scripting system.
Harvest stores the full text of linked articles from RSS feeds or URLs containing links.
"""

from pkgutil import extend_path
__path__ = extend_path(__path__, __name__)
__all__ = ["client", "controllers", "models", "resources", "run", "repl"]

from flask import Flask
from flask_restful import Api
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect

app = Flask("harvest")

# This config is the default and can be overridden by
# using options.config in run.py (python -m harvest.run -c somefile.py)
app.config.from_object("harvest.config")

app.version     = "3.0.0"
app.scripts     = None
app.feedmanager = None
app.config["HTTP_BASIC_AUTH_REALM"] = "Harvest " + app.version

db  = SQLAlchemy(app)
api = Api(app, prefix='/v1')

def init():
    # Models are imported here to prevent a circular import where we would
    # import models and the models would import the db object just above us.

    # They're also imported here in this function because we might not need
    # them if all we want from the namespace is something like app.version,
    # like in repl.py for example.
    from harvest.models import APIKey
    from harvest.models import FeedGroup
    from harvest.models import Feed
    from harvest.models import Article
    from harvest.models import Event

    from harvest.resources import api_key
    from harvest.resources import feeds
    from harvest.resources import feedgroups
    from harvest.resources import articles

    api.add_resource(api_key.KeyCollection,          "/keys")
    api.add_resource(api_key.KeyResource,            "/keys/<string:name>")

    api.add_resource(feedgroups.FeedGroupCollection, "/feeds")
    api.add_resource(feedgroups.FeedGroupResource,   "/feeds/<string:groupname>")
    api.add_resource(feedgroups.FeedGroupStop,       "/feeds/<string:groupname>/stop")
    api.add_resource(feedgroups.FeedGroupStart,      "/feeds/<string:groupname>/start")
    api.add_resource(feedgroups.FeedGroupArticles,   "/feeds/<string:groupname>/articles")
    api.add_resource(feedgroups.FeedGroupSearch,     "/feeds/<string:groupname>/search/<string:terms>")
    api.add_resource(feedgroups.FeedGroupCount,      "/feeds/<string:groupname>/count")

    api.add_resource(feeds.FeedResource,             "/feeds/<string:groupname>/<string:name>")
    api.add_resource(feeds.FeedArticleCollection,    "/feeds/<string:groupname>/<string:name>/articles")
    api.add_resource(feeds.FeedSearch,               "/feeds/<string:groupname>/<string:name>/search/<string:terms>")
    api.add_resource(feeds.FeedStartResource,        "/feeds/<string:groupname>/<string:name>/start")
    api.add_resource(feeds.FeedStopResource,         "/feeds/<string:groupname>/<string:name>/stop")

    api.add_resource(articles.ArticleCollection,     "/articles")
    api.add_resource(articles.ArticleResource,       "/articles/<string:uid>")
    api.add_resource(articles.ArticleSearch,         "/articles/search/<string:terms>")
    api.add_resource(articles.ArticleCount,          "/articles/count")

    # Create the database schema if it's not already laid out.
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()

    if 'api_keys' not in tables:
        db.create_all()
        master = APIKey(name=app.config['MASTER_KEY_NAME'])
        if app.config['MASTER_KEY']:
            master.key = app.config['MASTER_KEY']
        else:
            master.key = master.generate_key_str()
        print(master.key)
        master.active = True
        db.session.add(master)
        db.session.commit()
