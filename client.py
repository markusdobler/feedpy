from feedpy import FeedlyAPI, Feedpy, FeedlyAPIRequestException

print FeedlyAPI.authentication_url()

code_url = 'http://localhost/?code=AQAAZlV7InUiOiIxMTUyODM4Mjk5ODYzODAzMDU5MTEiLCJpIjoiNDM4MTkyMTgtNjdiMC00YmYyLWJmYzctZmQ5MTJkZjU2MWNhIiwicCI6NiwiYSI6IkZlZWRseSBzYW5kYm94IGNsaWVudCIsInQiOjEzODkzOTg4MDY5Mjh9&state='
#user_id, refresh_token, access_token = Feedly.get_id_and_tokens(code_url)
user_id = '43819218-67b0-4bf2-bfc7-fd912df561ca'
refresh_token = u'AQAAyv97Im4iOiJlVmI5ZzkyZkQ1YUhIdXA2IiwidSI6IjExNTI4MzgyOTk4NjM4MDMwNTkxMSIsImkiOiI0MzgxOTIxOC02N2IwLTRiZjItYmZjNy1mZDkxMmRmNTYxY2EiLCJwIjo2LCJjIjoxMzg5Mzk3ODQ2OTU5LCJhIjoiRmVlZGx5IHNhbmRib3ggY2xpZW50IiwidiI6InNhbmRib3gifQ:sandbox'

api = FeedlyAPI(user_id, refresh_token)
feedpy = Feedpy(api)

#req = feedpy._get('/profile')
#req = feedpy._get('/subscriptions')
#req = feedpy._get('/categories')
counts = feedpy.list_of_unread_counts()
print counts
for (cat_id, cat_label), (cat_cnt, feeds) in counts.items():
    print cat_label, cat_cnt
    for (feed_id, feed_title, feed_cnt) in feeds:
        print "  ", feed_title, feed_cnt

contents = feedpy.stream_content('feed/http://www.spiegel.de/schlagzeilen/index.rss')
ids = [c['id'] for n,c in enumerate(contents['items']) if n%6==0]
feedpy.mark_articles_as_read(ids)

continuation = None
while True:
    read = feedpy.recently_read(continuation=continuation, count=5)
    print "\n".join(k['title'] for k in read['items'])
    feedpy.mark_articles_as_unread([read['items'][0]['id']])
    try:
        continuation = read['continuation']
    except KeyError:
        break
    print
#  print req.url, req
#  data = req.json()
#  print data
#  for item in data['items']:
#      print item['title']
#  print item['id']
#  
#  req = feedpy._post('/markers', {
#      "action": "markAsRead",
#      "type": "entries",
#      "entryIds": [
#          item['id'],
#      ]
#  })
#  print req.url, req
#  print req.text
#  print req.request.body
#  print dir(req.request)
