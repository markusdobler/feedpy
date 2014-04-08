import requests
import json
import re
from collections import defaultdict
import base64
from datetime import datetime

class Entry(object):
    def __init__(self, entry, stream):
        self._entry = entry
        self._stream = stream

    def get(self, attr, default=None):
        return self._entry.get(attr, default)

    @property
    def title(self):
        return self.get('title', "<no title>")

    @property
    def keep_unread(self):
        saved_tag = self._stream._feedpy.api.global_resource_id('tag', 'saved')
        return saved_tag in [t['id'] for t in self.get('tags',default=())]

    @property
    def link(self):
        is_link = lambda l: l.startswith('https://') or l.startswith('http://')
        originId = self.get('originId', '')
        if is_link(originId):
            return originId
        for a in self.get('alternate', ()):
            href = a['href']
            if is_link(href):
                return href
        return "#nolink"

    @property
    def content(self):
        return (
            self.get('content',{}).get('content')
            or self.get('summary',{}).get('content')
            or "<b>no content found:</b> <tt>%s</tt>" % self._entry
        )

    @property
    def origin_title(self):
        return (
            self.get('origin',{}).get('title')
            or "</>"
        )

    @property
    def origin_title_short(self):
        otitle = self.origin_title
        initials = [part[0] for part in otitle.split()]
        return "".join(i for i in initials if i.isalnum())

    @property
    def _timestamp(self):
        published = self.get('published')
        if published is None:
            return "<unknown time>"
        return datetime.fromtimestamp(published/1000)

    @property
    def timestamp(self):
        return self._timestamp.strftime('%Y-%m-%d %H:%M:%S')

    @property
    def age(self):
        delta = datetime.now() - self._timestamp
        totalseconds = delta.days*24*60*60 + delta.seconds
        if totalseconds > 30*60*60:
            return "%id" % round(totalseconds/(24*60*60))
        if totalseconds > 80*60:
            return "%ih" % round(totalseconds/(60*60))
        if totalseconds > 5*60:
            return "%im" % round(totalseconds/(60))
        return "just now"

    @property
    def id(self):
        return self.get('id')

    @property
    def content_b64(self):
        return base64.b64encode(self.content.encode('utf8'))


class Stream(object):
    def __init__(self, content, feedpy):
        self._content = content
        self._feedpy = feedpy
        self.entries = [Entry(e, self) for e in content['items']]

    @property
    def title(self):
        return (
            self._content.get('title')
            or self._content.get('id', '').split('/')[-1]
        )


class Feedpy(object):
    """ High-level Feedly API 

    api = FeedlyAPI(user_id, refresh_token)
    # or: api = FeedlyAPI.from_authentication_code(...)

    feedpy = Feedpy(api)
    feedpy.list_of_unread_counts()
    """

    def __init__(self, api):
        self.api = api

    @property
    def _get(self): return self.api.get
    @property
    def _post(self): return self.api.post

    def _subscriptions(self):
        subscriptions = self._get('/subscriptions')
        return dict((s['id'], s) for s in subscriptions)


    def list_of_unread_counts(self):
        """ Returns a data structure with unread counts for categories and
        subscriptions.  The returned dict contains a key with id and label for
        each category.  The corresponding value 
        {
            (cat_id, cat_label): [cat_count, [ (sub_id, sub_title, sub_count), ...] ],
            ...
        }

        # iterate with:
        for (cat_id, cat_label), (cat_cnt, feeds) in counts.items():
            print cat_label, cat_cnt
            for (feed_id, feed_title, feed_cnt) in feeds:
                print "  ", feed_title, feed_cnt
        """
        subscriptions = self._subscriptions()
        counts_list = self._get('/markers/counts')
        counts_list = [feed for feed in counts_list['unreadcounts'] if
                       feed['id'].startswith('feed') and feed['count']]
        counts = defaultdict(lambda : [0, []])
        uncategorized = [dict(label='uncategorized',
                             id=self.api.global_resource_id('category', 'uncategorized'))]

        for feed in counts_list:
            feed_id, count = feed['id'], feed['count']
            feed_title = subscriptions[feed_id]['title']
            feed_categories = subscriptions[feed_id]['categories'] or uncategorized
            for category in feed_categories:
                category = (category['id'], category['label'])
                counts[category][0] += count
                counts[category][1].append((feed_id, feed_title, count))
        return dict(counts)

    def stream_content(self, stream_id, count=25, unread_only=True,
                       continuation=None, oldest_first=True):
        params = {
            'streamId': stream_id,
            'count': count,
            'ranked': 'oldest' if oldest_first else 'newest',
            'unreadOnly': unread_only,
            'continuation': continuation,
        }
        content = self._get('/streams/contents', params)
        return Stream(content, self)


    def _post_to_markers(self, action, type_singular, type_plural, ids, last_entry_id=None):
        data = {
            "action": action,
            "type": type_plural,
            "%sIds"%type_singular: ids,
        }
        if last_entry_id:
            data['lastReadEntryId'] = last_entry_id
        return self._post('/markers', data)

    def mark_articles_as_read(self, entry_ids):
        return self._post_to_markers('markAsRead', 'entry', 'entries', entry_ids)

    def mark_articles_as_unread(self, entry_ids):
        return self._post_to_markers('keepUnread', 'entry', 'entries', entry_ids)

    def mark_feed_as_read(self, feed_id, last_read_entry):
        return self._post_to_markers('markAsRead', 'feed', 'feeds', [feed_id], last_read_entry)

    def mark_category_as_read(self, category_id, last_read_entry):
        return self._post_to_markers('markAsRead', 'category', 'categories', [category_id], last_read_entry)

    def recently_read(self, **params):
        stream = self.api.global_resource_id('tag', 'read')
        params.setdefault('oldest_first', False)
        return self.stream_content(stream, **params)


class FeedlyAPIException(Exception):
    pass

class FeedlyAPIRequestException(FeedlyAPIException):
    def __init__(self, msg, response):
        FeedlyAPIException.__init__(self, msg)
        self.response = response

def retry_with_authorization_renewed(request):
    def wrapper(self, *args, **kwargs):
        r = request(self, *args, **kwargs)
        if r.status_code == 401:
            self.reauthenticate()
            r = request(self, *args, **kwargs)
        if r.status_code not in (200,):
            raise FeedlyAPIRequestException("Failed connection", r)
        try:
            return r.json()
        except:
            return r.text
    return wrapper

class FeedlyAPI(object):
    """ Low-level feedly api """

    # This should be overwritten by derived classes that have other endpoints
    base_url = 'http://sandbox.feedly.com/v3'
    client_id = 'sandbox'
    client_secret = 'CM786L1D4P3M9VYUPOB8'
    redirect_uri = 'http://localhost'


    def __init__(self, user_id, refresh_token, access_token=None):
        """Create API object from a user id, a refresh token and an optional
        access_token"""
        self._user_id = user_id
        self._refresh_token = refresh_token
        self._session = requests.Session()
        if access_token:
            self._set_authorization(access_token)

    @classmethod
    def authentication_url(cls):
        """Create the URL that starts the authentication with feedly"""
        params = {
            'response_type': 'code',
            'client_id': cls.client_id,
            'redirect_uri': cls.redirect_uri,
            'scope': 'https://cloud.feedly.com/subscriptions',
        }
        p = requests.PreparedRequest()
        p.prepare_url(cls.base_url + '/auth/auth', params)
        return p.url

    @classmethod
    def from_authentication_code(cls, code_or_full_url):
        """Create API object from an OAuth authorization code (which can be
        wrapped in an URL as returned by feedly)

        print api.authentication_url()
        # open URL in browser, follow directions
        # after several redirects, browser location will contain '...&code=...'
        # use that url for authentication:
        api.from_authentication_code(code_or_full_url)
        """
        user_id, refresh_token, access_token = cls._get_id_and_tokens(code_or_full_url)
        return cls(user_id, refresh_token, access_token)

    @classmethod
    def _get_id_and_tokens(cls, code_or_url):
        # extract code from url if necessary
        r = re.search('[?&]code=([-_a-zA-Z0-9]*)(&.*)?$', code_or_url)
        code = r.group(1) if r else code_or_url
        data = {
            'code': code,
            'client_id': cls.client_id,
            'client_secret': cls.client_secret,
            'redirect_uri': cls.redirect_uri,
            'grant_type': 'authorization_code',
        }
        r = requests.post(cls._full_url('/auth/token'), data=data).json()
        return r['id'], r['refresh_token'], r['access_token']


    def reauthenticate(self):
        params = {
            'refresh_token': self._refresh_token,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'refresh_token',
        }
        r = self.post_no_reauthenticate('/auth/token', params)
        if r.status_code != 200:
            raise FeedlyAPIException("Couldn't reauthenticate: " + r.text)
        self._set_authorization(r.json()['access_token'])

    def _set_authorization(self, access_token):
        self._session.headers.update({'Authorization': 'OAuth %s'%access_token})


    @retry_with_authorization_renewed
    def get(self, path, params=None):
        """ Low-level get access to API

        req = api.get('/streams/contents', {
        'streamId': "feed/http://www.heise.de/newsticker/heise-atom.xml",
        'unreadOnly': False,
        'count': 5,
        )}
        """
        params = params if params else {}
        return self._session.get(self._full_url(path), params=params)

    @retry_with_authorization_renewed
    def post(self, path, data=None):
        return self.post_no_reauthenticate(path, data)

    def post_no_reauthenticate(self, path, data=None):
        """ Low-level post access to API

        req = api.post('/markers', {
            "action": "markAsRead",
            "type": "entries",
            "entryIds": [ item['id'] ]
        })
        """
        data = json.dumps(data) if data else '{}'
        return self._session.post(self._full_url(path), data=data)

    @retry_with_authorization_renewed
    def put(self, path, data=None):
        """ Low-level put access to API"""
        data = json.dumps(data) if data else '{}'
        return self._session.put(self._full_url(path), data=data)

    @retry_with_authorization_renewed
    def delete(self, path, data=None):
        """ Low-level delete access to API"""
        data = json.dumps(data) if data else '{}'
        return self._session.delete(self._full_url(path), data=data)

    @classmethod
    def _full_url(cls, path):
        """ Combine bae_url and path """
        return cls.base_url + path

    def global_resource_id(self, kind, name):
        return self.resource_id(kind, 'global.%s'%name)

    def resource_id(self, kind, name):
        return 'user/%s/%s/%s' % (self._user_id, kind, name)
