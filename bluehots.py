import logging, requests, firebase_admin
from lxml import html
from datetime import datetime
from discord_hooks import Webhook
from firebase_admin import credentials, db
from collections import defaultdict
from time import sleep

logging.basicConfig(level=logging.DEBUG)

FORUM_SOURCE = 'http://www.overstalk.io/heroes/?sources=BLIZZARD_FORUM&_sources=on&_sources=on&_sources=on&_sources=on'
BLOG_SOURCE = 'http://us.battle.net/heroes/en/blog/'
# TEST_HOOK_URL = 'https://discordapp.com/api/webhooks/395942721405059092/ywqzyE_SspBTlbSbDuiqRuj7Y1GhB5jZA-IrmBoEPWF2hTTBdNxaHBlUioCm-Lxn01U4'
HOOK_URL = 'https://discordapp.com/api/webhooks/395613235958513664/kp8uEeHVtFaPl2UrjxNopUNSAmmBsb4UWG4rkgmQ3VrZXCgGSQgxNn36TJKB--nBCrpC'
FIREBASE_URL = 'https://bluehots-d71b6.firebaseio.com/'

class BlueHots(object):

    page = None
    tree = None
    forum_posts = []
    blog_posts = []
    post_dict = defaultdict(dict)
    firebase_app = None
    firebase_db = None

    def __init__(self):
        self.crawl_data()
        self.init_firebase()
        self.sync_posts()

    def init_firebase(self):
        creds = credentials.Certificate('creds.json')
        self.firebase_app = firebase_admin.initialize_app(creds, {
            'databaseURL': FIREBASE_URL
        })
        self.get_firebase_db()
        return self.firebase_app

    def get_firebase_db(self):
        self.firebase_db = db.reference()
        return self.firebase_db

    def sync_posts(self):
        for slug in self.get_slugs_to_be_synced():
            post = self.post_dict[slug]
            self.firebase_db.child('posts').child(slug).set(post)
        return self.firebase_db

    def crawl_data(self):
        forum_page = self.get_page(FORUM_SOURCE)
        forum_tree = self.get_tree(forum_page)
        self.get_posts(forum_tree, 'forum')

        blog_page = self.get_page(BLOG_SOURCE)
        blog_tree = self.get_tree(blog_page)
        self.get_posts(blog_tree, 'blog')

        self.populate_posts(self.forum_posts, 'forum')
        self.populate_posts(self.blog_posts, 'blog')
        return dict(forum_posts=self.forum_posts, blog_posts=self.blog_posts)

    def get_page(self, url):
        return requests.get(url)

    def get_tree(self, page):
        return html.fromstring(page.content)

    def get_posts(self, tree, post_type):
        if post_type == 'forum':
            self.forum_posts = tree.cssselect('div.card')
        elif post_type == 'blog':
            self.blog_posts = tree.cssselect('div.container.news-index-section > ul.news-list > li.news-list__item')

    @staticmethod
    def clean_string(string):
        return ' '.join(string.replace('\r\n', '').split())

    def get_post_title(self, post, post_type):
        css = None
        if post_type == 'forum':
            css = 'div.os-post-header'
        elif post_type == 'blog':
            css = 'h2.news-list__item__title'
        title_elm = post.cssselect(css)[0]
        return self.clean_string(title_elm.text_content())

    def get_post_timestamp(self, post, post_type):
        css = None
        if post_type == 'forum':
            css = 'div.os-post-meta > a:nth-child(3)'
        elif post_type == 'blog':
            css = 'span.publish-date'
        timestamp = post.cssselect(css)[0]
        return timestamp.get('title')

    def get_post_body(self, post, post_type):
        css = None
        if post_type == 'forum':
            css = 'div.os-post-content'
        elif post_type == 'blog':
            css = 'p.news-list__item__description'
        body = post.cssselect(css)[0]
        return self.clean_string(body.text_content())

    def get_post_url(self, post, post_type):
        css = None
        if post_type == 'forum':
            css = 'div.os-post-header > a'
            link = post.cssselect(css)[0]
            return link.get('href')
        elif post_type == 'blog':
            css = 'h2.news-list__item__title > a'
            link = post.cssselect(css)[0]
            return 'http://us.battle.net' + link.get('href')

    def get_post_slug(self, post, post_type):
        ts = self.get_post_timestamp(post, post_type)
        title = self.get_post_title(post, post_type).lower()
        dt = None
        slug = None
        if post_type == 'forum':
            dt = datetime.strptime(ts, '%d %B %Y %H:%M:%S')
        elif post_type == 'blog':
            dt = datetime.strptime(ts.strip(' PST'), '%b %d, %Y %I:%M %p')
        if 1 < len(title.split()) < 4:
            while len(title.split()) < 4:
                now = datetime.now()
                title = title + ' {}'.format(now.microsecond)
        slug = '{}-{}-{}-{}-{}{}{}'.format(title.split()[0],
                                           title.split()[1],
                                           title.split()[2],
                                           title.split()[3],
                                           dt.month,
                                           dt.day,
                                           dt.year)
        return slug

    def populate_posts(self, posts, post_type):
        for post in posts:
            ts = self.get_post_timestamp(post, post_type)
            url = self.get_post_url(post, post_type)
            title = self.get_post_title(post, post_type)
            body = self.get_post_body(post, post_type)
            slug = self.get_post_slug(post, post_type)
            self.post_dict[slug]['url'] = url
            self.post_dict[slug]['title'] = title
            self.post_dict[slug]['body'] = body
            self.post_dict[slug]['date'] = ts
            self.post_dict[slug]['post_type'] = post_type
        return self.post_dict

    def post_to_webhook(self, slug):
        post = self.get_post_from_server(slug)
        msg_string = (post['body'][:250] + '...') if len(post['body']) > 250 else post['body']
        embed = Webhook(HOOK_URL, color=123123)
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

    def get_server_slugs(self):
        logging.debug('Fetching stored posts..')
        slugs = []
        for key in self.get_posts_from_server().iterkeys():
            slugs.append(key)
        return slugs

    def get_local_slugs(self):
        logging.debug('Getting local posts..')
        slugs = []
        for key in self.post_dict.iterkeys():
            slugs.append(key)
        return slugs

    def get_slugs_to_be_synced(self):
        server_slugs = self.get_server_slugs()
        local_slugs = self.get_local_slugs()
        slug_set = set(server_slugs)
        result = [x for x in local_slugs if x not in slug_set]
        logging.debug('Slugs to be synced: %s', result)
        return result

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
            logging.debug('Emitting post to webhook: %s', key)
            self.post_to_webhook(key)
            self.set_post_as_sent(key)
            sleep(1)
        return self.get_unsent_posts_from_server()

if __name__ == "__main__":
    logging.debug('BlueHots sync starting..')
    app = BlueHots()
    logging.debug('BlueHots sync complete.')
    app.emit_unsent_posts_to_webhook()
    logging.debug('BlueHots job complete.')
