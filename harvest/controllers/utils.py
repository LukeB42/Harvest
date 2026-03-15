# _*_ coding: utf-8 _*_
# This file defines a nifty utility for querying the database,
# gzipping requests thanks to a snippet on pocoo.org and unique ID generation.
import gzip
import uuid
import hashlib
import functools
import urllib.parse
from io import BytesIO
from harvest import app, db
from sqlalchemy import or_, and_
from flask import after_this_request, request
from flask_restful import reqparse
from harvest.controllers.cron import parse_timings

class ArgsParser(reqparse.RequestParser):
    """RequestParser that reads from the query string (use in GET handlers)."""
    def add_argument(self, *args, **kwargs):
        kwargs.setdefault('location', 'args')
        return super().add_argument(*args, **kwargs)

def sha1sum(text):
    return hashlib.sha1(text.encode()).hexdigest()

def cors(f):
    if not app.config.get('ENABLE_CORS'):
        return f

    @functools.wraps(f)
    def view_func(*args, **kwargs):
        @after_this_request
        def enable_cors(response):
            response.headers['Access-Control-Allow-Headers'] = "Cache-Control, Pragma, Origin, Authorization, Content-Type, X-Requested-With, Accept"
            response.headers['Access-Control-Allow-Methods'] = "OPTIONS, GET, POST, PUT, DELETE"
            response.headers['Access-Control-Allow-Origin']  = "*"
            return response
        return f(*args, **kwargs)

    return view_func

def gzipped(f):
    if not app.config.get('GZIP_HERE'):
        return f

    @functools.wraps(f)
    def view_func(*args, **kwargs):
        @after_this_request
        def zipper(response):
            accept_encoding = request.headers.get('Accept-Encoding', '')

            if 'gzip' not in accept_encoding.lower():
                return response

            response.direct_passthrough = False

            if (response.status_code < 200 or
                response.status_code >= 300 or
                'Content-Encoding' in response.headers):
                return response

            gzip_buffer = BytesIO()
            gzip_file = gzip.GzipFile(mode='wb', fileobj=gzip_buffer)
            gzip_file.write(response.data)
            gzip_file.close()

            response.data = gzip_buffer.getvalue()
            response.headers['Content-Encoding'] = 'gzip'
            response.headers['Vary'] = 'Accept-Encoding'
            response.headers['Content-Length'] = len(response.data)

            return response

        return f(*args, **kwargs)

    return view_func

def uid():
    return str(uuid.uuid4())

def tconv(seconds):
    if not seconds:
        return "< 1 second"
    minutes, seconds = divmod(seconds, 60)
    hours, minutes   = divmod(minutes, 60)
    days, hours      = divmod(hours, 24)
    weeks, days      = divmod(days, 7)
    s = ""
    if weeks:
        s += "1 week, " if weeks == 1 else "%i weeks, " % weeks
    if days:
        s += "1 day, " if days == 1 else "%i days, " % days
    if hours:
        s += "1 hour, " if hours == 1 else "%i hours, " % hours
    if minutes:
        s += "1 minute" if minutes == 1 else "%i minutes" % minutes
    if seconds:
        if len(s) > 0:
            s += " and 1 second" if seconds == 1 else " and %i seconds" % seconds
        else:
            s += "1 second" if seconds == 1 else "%i seconds" % seconds
    return s

def spaceparse(string):
    """
    Return strings surrounded in quotes as a list, or dict if they're key="value".
    """
    results = []
    quotes  = string.count('"')
    quoted  = quotes // 2
    keyvalue = False

    # Return an empty resultset if there are an uneven number of quotation marks
    if quotes % 2 != 0:
        return results

    for phrase in range(0, quoted + 1):
        if not string: break
        start = string.find('"')
        end   = string.find('"', start + 1)

        if start > 0 and string[start - 1] == '=':
            keyvalue = True
            for i in range(start, -1, -1):
                if string[i] == ' ' or i == 0:
                    results.append(string[i:end])
                    break
        else:
            results.append(string[start + 1:end])
        string = string[end + 1:]

    if keyvalue:
        res = {}
        for item in results:
            k, v = item.split('=')
            if k.startswith(' '):
                k = k[1:]
            if v.startswith('"'):
                v = v[1:]
            res[k] = v
        return res
    return results

def update_url(url, params):
    url_parts = list(urllib.parse.urlparse(request.url))
    query = dict(urllib.parse.parse_qsl(url_parts[4]))
    query.update(params)
    url_parts[4] = urllib.parse.urlencode(query)
    return urllib.parse.urlunparse(url_parts)

def make_response(url, query, jsonify=True):
    """
    Take a paginated SQLAlchemy query and return
    a response that's more easily reasoned about
    by other programs.
    """
    response = {}
    if jsonify:
        response['data'] = [i.jsonify() for i in query.items]

    response['links'] = {}
    response['links']['self'] = url
    if query.has_next:
        response['links']['next'] = update_url(url, {"page": str(query.next_num)})
    return response
