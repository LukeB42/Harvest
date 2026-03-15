# _*_ coding: utf-8 _*_
# This file provides the HTTP endpoints for operating on groups of feeds.
import asyncio
from datetime import datetime
from harvest import app, db
from flask import request
from flask_restful import Resource, reqparse, abort
from sqlalchemy import and_, desc
from harvest.resources.api_key import auth
from harvest.models import FeedGroup, Feed, Article
from harvest.controllers.cron import CronError, parse_timings
from harvest.controllers.utils import cors, gzipped, make_response, ArgsParser

class FeedGroupCollection(Resource):

    @cors
    @gzipped
    def get(self):
        """
        Paginate an array of feed groups associated with the requesting key.
        """
        key = auth()

        parser = ArgsParser()
        parser.add_argument("page",     type=int,  default=1)
        parser.add_argument("per_page", type=int,  default=10)
        args = parser.parse_args()

        query = FeedGroup.query.filter(FeedGroup.key == key) \
                .order_by(desc(FeedGroup.created)).paginate(page=args.page, per_page=args.per_page)

        return make_response(request.url, query)

    @cors
    @gzipped
    def put(self):
        """
        Create a new feed group, providing the name isn't already in use.
        """
        key = auth(forbid_reader_keys=True)

        parser = reqparse.RequestParser()
        parser.add_argument("name",   type=str,  required=True)
        parser.add_argument("active", type=bool, default=True, help="Feed group is active", required=False)
        args = parser.parse_args()

        if [fg for fg in key.feedgroups if fg.name == args.name]:
            return {"message": "Feed group %s already exists." % args.name}, 304

        fg = FeedGroup(name=args.name, active=args.active)
        key.feedgroups.append(fg)
        db.session.add(fg)
        db.session.add(key)
        db.session.commit()
        return fg.jsonify(), 201

class FeedGroupResource(Resource):

    @cors
    @gzipped
    def get(self, groupname):
        """
        Review a specific feed group.
        """
        key = auth()

        fg = FeedGroup.query.filter(and_(FeedGroup.key == key, FeedGroup.name == groupname)).first()
        if not fg:
            abort(404)
        return fg.jsonify()

    @cors
    @gzipped
    def put(self, groupname):
        """
        Create a new feed providing the name and url are unique.
        Feeds must be associated with a group.
        """
        key = auth(forbid_reader_keys=True)

        parser = reqparse.RequestParser()
        parser.add_argument("name",     type=str,  required=True)
        parser.add_argument("url",      type=str,  required=True)
        parser.add_argument("schedule", type=str,  required=True)
        parser.add_argument("active",   type=bool, default=True, help="Feed is active", required=False)
        args = parser.parse_args()

        fg = FeedGroup.query.filter(and_(FeedGroup.key == key, FeedGroup.name == groupname)).first()
        if not fg:
            return {"message": "Unknown Feed Group %s" % groupname}, 304

        try:
            parse_timings(args.schedule)
        except CronError as err:
            return {"message": str(err)}, 500

        if [feed for feed in key.feeds if feed.url == args.url]:
            return {"message": "A feed on this key already exists with this url."}, 500

        if [feed for feed in fg.feeds if feed.name == args.name]:
            return {"message": "A feed in this group already exists with this name."}, 500

        feed = Feed(name=args.name, url=args.url, schedule=args.schedule, active=args.active)
        fg.feeds.append(feed)
        key.feeds.append(feed)

        db.session.add(feed)
        db.session.add(fg)
        db.session.add(key)
        db.session.commit()

        feed = Feed.query.filter(and_(Feed.key == key, Feed.name == args.name)).first()
        if not feed:
            return {"message": "Error saving feed."}, 304

        asyncio.get_running_loop().create_task(
            app.feedmanager.handle_start([key.id, feed.name])
        )
        return feed.jsonify(), 201

    @cors
    @gzipped
    def post(self, groupname):
        "Rename a feedgroup or toggle active status."

        key = auth(forbid_reader_keys=True)

        parser = reqparse.RequestParser()
        parser.add_argument("name",   type=str,  help="Rename a feed group")
        parser.add_argument("active", type=bool, default=None)
        args = parser.parse_args()

        fg = FeedGroup.query.filter(
            and_(FeedGroup.key == key, FeedGroup.name == groupname)
        ).first()
        if not fg:
            abort(404)

        if args.name:
            if FeedGroup.query.filter(
                and_(FeedGroup.key == key, FeedGroup.name == args.name)
            ).first():
                return {"message": "A feed group already exists with this name."}, 304
            fg.name = args.name

        if args.active or args.active == False:
            fg.active = args.active

        db.session.add(fg)
        db.session.commit()
        return fg.jsonify()

    @cors
    @gzipped
    def delete(self, groupname):
        key = auth(forbid_reader_keys=True)

        fg = FeedGroup.query.filter(and_(FeedGroup.key == key, FeedGroup.name == groupname)).first()
        if not fg:
            abort(404)

        count = 0
        for feed in fg.feeds:
            for article in feed.articles:
                count += 1
                db.session.delete(article)
            db.session.delete(feed)
        db.session.delete(fg)
        db.session.commit()
        count = "{:,}".format(count)
        app.log('%s: Deleted feed group "%s". (%s articles)' % (key.name, fg.name, count))
        return {}

class FeedGroupArticles(Resource):

    @cors
    def get(self, groupname):
        """
        Retrieve articles by feedgroup.
        """
        key = auth()

        fg = FeedGroup.query.filter(and_(FeedGroup.key == key, FeedGroup.name == groupname)).first()
        if not fg:
            abort(404)

        parser = ArgsParser()
        parser.add_argument("page",     type=int,   default=1)
        parser.add_argument("per_page", type=int,   default=10)
        parser.add_argument("content",  type=bool,  default=None)
        parser.add_argument("before",   type=float, default=None)
        args = parser.parse_args()

        filters = [Article.feed.has(group=fg)]
        if args.before is not None:
            filters.append(Article.created < datetime.fromtimestamp(args.before))
        if args.content == True:
            filters.append(Article.content != None)
        elif args.content == False:
            filters.append(Article.content == None)

        query = Article.query.filter(and_(*filters)) \
                .order_by(desc(Article.created)).paginate(page=args.page, per_page=args.per_page)
        return make_response(request.url, query)

class FeedGroupStart(Resource):

    @cors
    def post(self, groupname):
        """
        Start all feeds within a group.
        """
        key = auth(forbid_reader_keys=True)

        fg = FeedGroup.query.filter(and_(FeedGroup.key == key, FeedGroup.name == groupname)).first()
        if not fg:
            abort(404)

        loop = asyncio.get_running_loop()
        for feed in fg.feeds:
            loop.create_task(app.feedmanager.handle_start([key.id, feed.name]))
        return {}

class FeedGroupStop(Resource):

    @cors
    def post(self, groupname):
        key = auth(forbid_reader_keys=True)

        fg = FeedGroup.query.filter(and_(FeedGroup.key == key, FeedGroup.name == groupname)).first()
        if not fg:
            abort(404)

        loop = asyncio.get_running_loop()
        for feed in fg.feeds:
            loop.create_task(app.feedmanager.handle_stop([key.id, feed.name]))
        return {}

class FeedGroupSearch(Resource):

    @cors
    def get(self, groupname, terms):
        """
        Return articles on feeds in this group with our search terms in the title.
        """
        key = auth()

        parser = ArgsParser()
        parser.add_argument("page",     type=int, default=1)
        parser.add_argument("per_page", type=int, default=10)
        args = parser.parse_args()

        fg = FeedGroup.query.filter(and_(FeedGroup.key == key, FeedGroup.name == groupname)).first()
        if not fg:
            abort(404)

        query = Article.query.filter(
                    and_(Article.feed.has(group=fg), Article.title.like("%" + terms + "%"))) \
                .order_by(desc(Article.created)).paginate(page=args.page, per_page=args.per_page)
        return make_response(request.url, query)

class FeedGroupCount(Resource):

    @cors
    def get(self, groupname):
        key = auth()

        fg = FeedGroup.query.filter(and_(FeedGroup.key == key, FeedGroup.name == groupname)).first()
        if not fg:
            abort(404)

        return sum(len(f.articles) for f in fg.feeds)
