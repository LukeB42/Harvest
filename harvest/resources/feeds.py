# _*_ coding: utf-8 _*_
# This file provides the HTTP endpoints for operating on individual feeds.
import asyncio
from datetime import datetime
from harvest import app, db
from flask import request
from flask_restful import Resource, reqparse, abort
from sqlalchemy import desc, and_
from harvest.models import Feed, FeedGroup, Article
from harvest.resources.api_key import auth
from harvest.controllers.cron import CronError, parse_timings
from harvest.controllers.utils import make_response, gzipped, cors, ArgsParser

class FeedResource(Resource):

    @cors
    @gzipped
    def get(self, groupname, name):
        """
        Review a feed.
        """
        key = auth()

        feed = Feed.query.filter(and_(Feed.name == name, Feed.key == key)).first()
        if feed:
            return feed.jsonify()
        abort(404)

    @cors
    @gzipped
    def post(self, groupname, name):
        """
        Modify an existing feed.
        """
        key = auth(forbid_reader_keys=True)

        parser = reqparse.RequestParser()
        parser.add_argument("name",     type=str)
        parser.add_argument("group",    type=str)
        parser.add_argument("url",      type=str)
        parser.add_argument("schedule", type=str)
        parser.add_argument("active",   type=bool, default=None, help="Feed is active")
        args = parser.parse_args()

        feed = Feed.query.filter(and_(Feed.key == key, Feed.name == name)).first()
        if not feed:
            abort(404)

        if args.name:
            if Feed.query.filter(and_(Feed.key == key, Feed.name == args.name)).first():
                return {"message": "A feed already exists with this name."}, 304
            feed.name = args.name

        if args.active is not None:
            feed.active = args.active

        if args.url:
            feed.url = args.url

        if args.schedule:
            try:
                parse_timings(args.schedule)
            except CronError as err:
                return {"message": str(err)}, 500
            feed.schedule = args.schedule

        db.session.add(feed)
        db.session.commit()

        if args.url or args.schedule:
            loop = asyncio.get_running_loop()
            loop.create_task(app.feedmanager.handle_stop([key.id, feed.name]))
            loop.create_task(app.feedmanager.handle_start([key.id, feed.name]))

        return feed.jsonify()

    @cors
    @gzipped
    def delete(self, groupname, name):
        """
        Halt and delete a feed, along with its articles.
        """
        key  = auth(forbid_reader_keys=True)
        feed = Feed.query.filter(and_(Feed.key == key, Feed.name == name)).first()
        if not feed:
            abort(404)

        asyncio.get_running_loop().create_task(
            app.feedmanager.handle_stop([key.id, feed.name])
        )
        app.log('%s: %s: Deleting feed "%s".' % (feed.key.name, feed.group.name, feed.name))

        for a in feed.articles:
            db.session.delete(a)

        db.session.delete(feed)
        db.session.commit()
        return {}

class FeedArticleCollection(Resource):

    @cors
    def get(self, groupname, name):
        """
        Review the articles for a specific feed on this key.
        """
        key = auth()

        feed = Feed.query.filter(and_(Feed.name == name, Feed.key == key)).first()
        if not feed:
            abort(404)

        parser = ArgsParser()
        parser.add_argument("page",     type=int,   default=1)
        parser.add_argument("per_page", type=int,   default=10)
        parser.add_argument("content",  type=bool,  default=None)
        parser.add_argument("before",   type=float, default=None)
        args = parser.parse_args()

        filters = [Article.key == key, Article.feed == feed]
        if args.before is not None:
            filters.append(Article.created < datetime.fromtimestamp(args.before))
        if args.content == True:
            filters.append(Article.content != None)
        elif args.content == False:
            filters.append(Article.content == None)

        query = Article.query.filter(and_(*filters)) \
                .order_by(desc(Article.created)).paginate(page=args.page, per_page=args.per_page)
        return make_response(request.url, query)

class FeedSearch(Resource):

    @cors
    def get(self, groupname, name, terms):
        """
        Search for articles within a feed.
        """
        key = auth()

        parser = ArgsParser()
        parser.add_argument("page",     type=int, default=1)
        parser.add_argument("per_page", type=int, default=10)
        args = parser.parse_args()

        fg = FeedGroup.query.filter(and_(FeedGroup.key == key, FeedGroup.name == groupname)).first()
        if not fg:
            abort(404)

        f = [f for f in fg.feeds if f.name == name]
        if not f:
            abort(404)

        f = f[0]

        query = Article.query.filter(
                and_(Article.feed == f, Article.title.like("%" + terms + "%"))) \
                .order_by(desc(Article.created)).paginate(page=args.page, per_page=args.per_page)

        return make_response(request.url, query)

class FeedStartResource(Resource):

    @cors
    def post(self, groupname, name):
        key = auth(forbid_reader_keys=True)

        feed = Feed.query.filter(and_(Feed.name == name, Feed.key == key)).first()
        if feed:
            asyncio.get_running_loop().create_task(
                app.feedmanager.handle_start([key.id, feed.name])
            )
            return feed.jsonify()
        abort(404)

class FeedStopResource(Resource):

    @cors
    def post(self, groupname, name):
        key = auth(forbid_reader_keys=True)

        feed = Feed.query.filter(and_(Feed.name == name, Feed.key == key)).first()
        if feed:
            asyncio.get_running_loop().create_task(
                app.feedmanager.handle_stop([key.id, feed.name])
            )
            return feed.jsonify()
        abort(404)
