import logging, requests, firebase_admin
from lxml import html
from datetime import datetime
from discord_hooks import Webhook
from firebase_admin import credentials, db
from collections import defaultdict

logger = logging.getLogger('bluehots')
source = 'http://www.overstalk.io/heroes/?sources=BLIZZARD_FORUM&_sources=on&_sources=on&_sources=on&_sources=on'
hook_url = 'https://discordapp.com/api/webhooks/395613235958513664/kp8uEeHVtFaPl2UrjxNopUNSAmmBsb4UWG4rkgmQ3VrZXCgGSQgxNn36TJKB--nBCrpC'

class BlueHots(object):

    page = None
    tree = None
    posts = []
    post_dict = defaultdict(dict)
    firebase_app = None
    firebase_db = None

    def __init__(self):
        self.run_setup(source)
        self.init_firebase()

    def init_firebase(self):
        creds = credentials.Certificate('creds.json')
        self.firebase_app = firebase_admin.initialize_app(creds, {
            'databaseURL': 'https://bluehots-d71b6.firebaseio.com/'
        })
        self.get_firebase_db()
        return self.firebase_app

    def get_firebase_db(self):
        self.firebase_db = db.reference()
        return self.firebase_db

    def sync_posts(self):
        for key, value in self.post_dict.iteritems():
            self.firebase_db.child('posts').child(key).set(value)
        return self.firebase_db

    def run_setup(self, source):
        self.get_page(source)
        self.get_tree()
        self.get_posts()
        self.populate_posts(self.posts)
        return dict(page=self.page, tree=self.tree, posts=self.posts)

    def get_page(self, url):
        self.page = requests.get(url)
        return self.page

    def get_tree(self):
        self.tree = html.fromstring(self.page.content)
        return self.tree

    def get_posts(self):
        self.posts = self.tree.cssselect('div.card')
        return self.posts

    @staticmethod
    def clean_string(string):
        return ' '.join(string.replace('\r\n', '').split())

    def get_post_title(self, post):
        css = 'div.os-post-header'
        title_elm = post.cssselect(css)[0]
        return self.clean_string(title_elm.text_content())

    def get_post_timestamp(self, post):
        css = 'div.os-post-meta > a:nth-child(3)'
        timestamp = post.cssselect(css)[0]
        return timestamp.get('title')

    def get_post_body(self, post):
        css = 'div.os-post-content'
        body = post.cssselect(css)[0]
        return self.clean_string(body.text_content())

    def get_post_url(self, post):
        css = 'div.os-post-header > a'
        link = post.cssselect(css)[0]
        return link.get('href')

    def get_post_slug(self, post):
        ts = self.get_post_timestamp(post)
        title = self.get_post_title(post).lower()
        dt = datetime.strptime(ts, '%d %B %Y %H:%M:%S')
        slug = '{}-{}-{}-{}-{}{}{}'.format(title.split()[0],
                                           title.split()[1],
                                           title.split()[2],
                                           title.split()[3],
                                           dt.month,
                                           dt.day,
                                           dt.year)
        return slug

    def populate_posts(self, posts):
        for post in posts:
            ts = self.get_post_timestamp(post)
            url = self.get_post_url(post)
            title = self.get_post_title(post)
            body = self.get_post_body(post)
            slug = self.get_post_slug(post)
            self.post_dict[slug]['url'] = url
            self.post_dict[slug]['title'] = title
            self.post_dict[slug]['body'] = body
            self.post_dict[slug]['date'] = ts
        return self.post_dict

    def get_latest_post(self):
        return self.populate_posts(self.get_posts()).iterkeys().next()

    def post_to_webhook(self):
        latest_post = self.get_latest_post()
        msg_string = (latest_post['body'][:250] + '...') if len(latest_post['body']) > 250 else latest_post['body']
        embed = Webhook(hook_url, color=123123)
        embed.set_author(name=latest_post['title'], icon='https://cdn6.aptoide.com/imgs/5/1/f/51fc6f8666c50ce7456651810d7a4439_icon.png?w=240')
        embed.set_desc(msg_string)
        embed.add_field(name='Read more', value=latest_post['url'])
        embed.post()
