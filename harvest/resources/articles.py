# _*_ coding: utf-8 _*_
# This file determines how articles are accessed.
# You may also want to examine the Article class in harvest/models.py
from harvest import db
from flask import request
from flask_restful import Resource, reqparse, abort
from sqlalchemy import desc, and_
from harvest.models import Article
from harvest.resources.api_key import auth
from harvest.controllers.fetch import fetch_feedless_article
from harvest.controllers.utils import make_response, gzipped, cors, ArgsParser

class ArticleCollection(Resource):

    @cors
    def get(self):
        """
        Review all articles associated with this key.
        """
        key = auth()

        parser = ArgsParser()
        parser.add_argument("page",     type=int,  default=1)
        parser.add_argument("per_page", type=int,  default=10)
        parser.add_argument("content",  type=bool, default=None)
        args = parser.parse_args()

        if args.content == True:
            query = Article.query.filter(and_(Article.key == key, Article.content != None)) \
                    .order_by(desc(Article.created)).paginate(page=args.page, per_page=args.per_page)
        elif args.content == False:
            query = Article.query.filter(and_(Article.key == key, Article.content == None)) \
                    .order_by(desc(Article.created)).paginate(page=args.page, per_page=args.per_page)
        else:
            query = Article.query.filter(Article.key == key) \
                    .order_by(desc(Article.created)).paginate(page=args.page, per_page=args.per_page)

        return make_response(request.url, query)

    @cors
    def put(self):
        """
        Fetch an article without an associated feed.
        """
        key = auth()

        parser = reqparse.RequestParser()
        parser.add_argument("url", type=str, required=True)
        args = parser.parse_args()

        try:
            article = fetch_feedless_article(key, args.url)
        except Exception as e:
            return {"Error": str(e)}

        if not article:
            return {"Error": "This URL has already been stored."}, 304

        return article.jsonify(), 201

class ArticleSearch(Resource):

    @cors
    def get(self, terms):
        """
        The /v1/articles/search/<terms> endpoint.
        """
        key = auth()

        parser = ArgsParser()
        parser.add_argument("page",     type=int,  default=1)
        parser.add_argument("per_page", type=int,  default=10)
        parser.add_argument("content",  type=bool, default=None)
        args = parser.parse_args()

        if args.content == True:
            query = Article.query.filter(
                        and_(
                            Article.key == key,
                            Article.content != None,
                            Article.title.like("%" + terms + "%")
                        )) \
                    .order_by(desc(Article.created)).paginate(page=args.page, per_page=args.per_page)

            response = make_response(request.url, query)

            # This method of manually pruning JSON documents because they
            # don't relate to items that have content can omit them from search
            # completely. They don't have content but they're showing up here in
            # content != None rather than content == None.. You could always just
            # comment out this next for loop
            for doc in response['data']:
                if not doc['content_available']:
                    response['data'].remove(doc)
            return response

        elif args.content == False:
            query = Article.query.filter(
                        and_(
                            Article.key == key,
                            Article.content == None,
                            Article.title.like("%" + terms + "%")
                        )) \
                    .order_by(desc(Article.created)).paginate(page=args.page, per_page=args.per_page)
            return make_response(request.url, query)

        query = Article.query.filter(
                    and_(Article.key == key, Article.title.like("%" + terms + "%"))) \
                .order_by(desc(Article.created)).paginate(page=args.page, per_page=args.per_page)
        return make_response(request.url, query)

class ArticleResource(Resource):

    @cors
    def get(self, uid):
        """
        Read an article.
        """
        key = auth()

        article = Article.query.filter(and_(Article.key == key, Article.uid == uid)).first()
        if article:
            return article.jsonify(summary=True, content=True)

        abort(404)

    @cors
    @gzipped
    def delete(self, uid):
        """
        Delete an article.
        """
        key = auth(forbid_reader_keys=True)

        article = Article.query.filter(and_(Article.key == key, Article.uid == uid)).first()
        if article:
            db.session.delete(article)
            db.session.commit()
            return {}

        abort(404)

class ArticleCount(Resource):

    @cors
    def get(self):
        """
        Return the amount of articles belonging to an API key.
        """
        key = auth()
        return len(key.articles)
