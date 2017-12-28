import logging, requests, firebase_admin
from lxml import html
from datetime import datetime
from discord_hooks import Webhook
from firebase_admin import credentials, db
from collections import defaultdict
from time import sleep

logger = logging.getLogger('bluehots')
source = 'http://www.overstalk.io/heroes/?sources=BLIZZARD_FORUM&_sources=on&_sources=on&_sources=on&_sources=on'
hook_url = 'https://discordapp.com/api/webhooks/395613235958513664/kp8uEeHVtFaPl2UrjxNopUNSAmmBsb4UWG4rkgmQ3VrZXCgGSQgxNn36TJKB--nBCrpC'
firebase_url = 'https://bluehots-d71b6.firebaseio.com/'

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
            'databaseURL': firebase_url
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

    def post_to_webhook(self, slug):
        post = self.get_post_from_server(slug)
        msg_string = (post['body'][:250] + '...') if len(post['body']) > 250 else post['body']
        embed = Webhook(hook_url, color=123123)
        embed.set_author(name=post['title'], icon='https://cdn6.aptoide.com/imgs/5/1/f/51fc6f8666c50ce7456651810d7a4439_icon.png?w=240')
        embed.set_desc(msg_string)
        embed.add_field(name='Read more', value=post['url'])
        embed.post()

    def set_post_as_sent(self, slug):
        return self.firebase_db.child('posts').child(slug).update({'sent': True})

    def get_post_from_server(self, slug):
        return self.firebase_db.child('posts').child(slug).get()

    def get_posts_from_server(self):
        return self.firebase_db.child('posts').get()

    def get_unsent_posts_from_server(self):
        unsent_posts = defaultdict(dict)
        for key, value in self.get_posts_from_server().iteritems():
            try:
                sent = value['sent']
                if not sent:
                    unsent_posts[key] = value
            except KeyError:
                unsent_posts[key] = value
                unsent_posts[key]['sent'] = False
        return unsent_posts

    def emit_unsent_posts_to_webhook(self):
        for key in self.get_unsent_posts_from_server():
            self.post_to_webhook(key)
            self.set_post_as_sent(key)
            sleep(1)
        return self.get_unsent_posts_from_server()
