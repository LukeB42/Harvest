# _*_ coding: utf-8 _*_
# This module determines the behavior of API Keys within the system.
import re
from flask import request
from sqlalchemy import and_
from harvest import app, db
from harvest.models import *
from flask_restful import Resource, reqparse, abort
from harvest.controllers.utils import cors, gzipped

def auth(forbid_reader_keys=False):
    """
    Determine that inactive keys are invalid
    and that reader keys resolve to their parent unless forbidden.
    """
    if 'Authorization' in request.headers:
        key_str = request.headers['Authorization'].replace('Basic ', '')
        key = APIKey.query.filter(APIKey.key == key_str).first()
        if key and key.active:
            if key.reader:
                if not forbid_reader_keys:
                    return key.parent
                abort(401, message="Forbidden to reader keys.")
            return key
    abort(401, message="Invalid API Key.")

class KeyCollection(Resource):

    @cors
    @gzipped
    def get(self):
        key = auth()
        response = key.jsonify(feedgroups=False)

        if key.name == app.config['MASTER_KEY_NAME']:
            keys = []
            for i in APIKey.query.all():
                keys.append(i.name)
            response['system'] = {}
            response['system']['keys'] = keys
            response['system']['permit_new'] = app.config['PERMIT_NEW']

        return [response]

    @cors
    @gzipped
    def put(self):
        """
        Create a key under the specified name, presuming config['PERMIT_NEW']
        is enabled or the master key is in use.

        Reader keys are created by setting the "reader" parameter.
        They are automatically associated with the requesting key.
        """
        key = None
        parser = reqparse.RequestParser()
        parser.add_argument("name",   type=str,  help="Name associated with the key", required=True)
        parser.add_argument("reader", type=bool, help="Creates a reader key", default=False)
        args = parser.parse_args()

        if 'Authorization' in request.headers:
            key_str = request.headers['Authorization'].replace('Basic ', '')
            key = APIKey.query.filter(APIKey.key == key_str).first()
            if key.reader:
                abort(401, message="Reader keys cannot create API keys.")

        if key and args.name and args.reader:
            new_key = APIKey(name=args.name, active=True, reader=True)
            new_key.key = new_key.generate_key_str()
            key.readers.append(new_key)
            db.session.add(key)
            db.session.add(new_key)
            db.session.commit()
            return new_key.jsonify(with_key_str=True), 201

        if (key and key.name == app.config['MASTER_KEY_NAME']) or app.config['PERMIT_NEW']:
            if re.match(r"^$|\s+[a-zA-Z0-9_]+$", args.name) or len(args.name) > 60:
                abort(422, message="Invalid key name. Must contain alphanumeric characters.")
            key = APIKey.query.filter(APIKey.name == args.name).first()

            if key:
                abort(403, message="A key already exists with this name.")

            key = APIKey(name=args.name)
            key.key    = key.generate_key_str()
            key.active = True
            db.session.add(key)
            db.session.commit()
            return key.jsonify(with_key_str=True), 201

        abort(403, message="This server isn't currently generating new keys.")

    @cors
    @gzipped
    def post(self):
        "Update existing API keys via the master key."

        key = auth(forbid_reader_keys=True)

        parser = reqparse.RequestParser()
        parser.add_argument("key",        type=str,  help="API Key")
        parser.add_argument("name",       type=str,  help="Name associated with the key")
        parser.add_argument("permit_new", type=bool, help="Determines whether new API keys can be created.")
        parser.add_argument("active",     type=bool, help="Determines whether a key is active or not.", default=None)
        args = parser.parse_args()

        if key.name != app.config['MASTER_KEY_NAME']:
            abort(403)

        response = {}
        subject  = None

        if args.key and args.name:
            subject = APIKey.query.filter(APIKey.key == args.key).first()
            if APIKey.query.filter(APIKey.name == args.name).first():
                return {'message': "A key already exists with this name."}, 304
            subject.name = args.name
        elif args.name and not args.key:
            subject = APIKey.query.filter(APIKey.name == args.name).first()
        elif args.key and not args.name:
            subject = APIKey.query.filter(APIKey.key == args.key).first()

        if not subject:
            abort(404)

        if subject.name == app.config['MASTER_KEY_NAME']:
            abort(403)
        if args.active or args.active == False:
            subject.active = args.active
            response['key'] = subject.jsonify(with_key_str=True)
            db.session.add(subject)

        if (args.permit_new or args.permit_new == False) and key.name == app.config['MASTER_KEY_NAME']:
            app.config['PERMIT_NEW'] = args.permit_new
            response['system'] = {}
            response['system']['permit_new'] = app.config['PERMIT_NEW']

        db.session.commit()
        return response

    @cors
    @gzipped
    def delete(self):
        key = auth(forbid_reader_keys=True)

        parser = reqparse.RequestParser()
        parser.add_argument("key", type=str, help="API Key")
        args = parser.parse_args()

        target = APIKey.query.filter(APIKey.key == args.key).first()
        if not target:
            abort(404, message="Unrecognized key.")

        if args.key != key.key and key.name != app.config['MASTER_KEY_NAME']:
            abort(403, message="You do not have permission to remove this key.")
        if key.name == app.config['MASTER_KEY_NAME'] and args.key == key.key:
            abort(403, message="You are attempting to delete the master key.")

        for fg in target.feedgroups: db.session.delete(fg)
        for f  in target.feeds:      db.session.delete(f)
        for a  in target.articles:   db.session.delete(a)

        db.session.delete(target)
        db.session.commit()
        return {}, 204

class KeyResource(Resource):

    @cors
    @gzipped
    def get(self, name):
        """
        Permit the administrative key to review another key by name.
        """
        key = auth(forbid_reader_keys=True)
        if key.name != app.config['MASTER_KEY_NAME'] and name != key.name:
            abort(403)

        target = APIKey.query.filter_by(name=name).first()
        if target:
            return target.jsonify(feedgroups=True, with_key_str=True)

        abort(404, message="Unrecognised key.")
