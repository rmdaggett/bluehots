import logging, requests
from lxml import html
from discord_hooks import Webhook

logger = logging.getLogger('bluehots')
source = 'http://www.overstalk.io/heroes/?sources=BLIZZARD_FORUM&_sources=on&_sources=on&_sources=on&_sources=on'
hook_url = 'https://discordapp.com/api/webhooks/395613235958513664/kp8uEeHVtFaPl2UrjxNopUNSAmmBsb4UWG4rkgmQ3VrZXCgGSQgxNn36TJKB--nBCrpC'

class BlueHots(object):

    page = None
    tree = None
    posts = []
    post_list = []

    def __init__(self):
        self.run_setup(source)

    def run_setup(self, source):
        self.get_page(source)
        self.get_tree()
        self.get_posts()
        self.populate_post_list(self.posts)
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

    def clean_string(self, string):
        return ' '.join(string.replace('\r\n','').split())

    def get_post_title(self, post):
        css = 'div.os-post-header'
        title_elm = post.cssselect(css)[0]
        return self.clean_string(title_elm.text_content())

    def get_post_body(self, post):
        css = 'div.os-post-content'
        body_elm = post.cssselect(css)[0]
        return self.clean_string(body_elm.text_content())

    def get_post_url(self, post):
        css = 'div.os-post-header > a'
        link_elm = post.cssselect(css)[0]
        return link_elm.get('href')

    def populate_post_list(self, posts):
        for p in posts:
            self.post_list.append(dict(url=self.get_post_url(p), title=self.get_post_title(p), body=self.get_post_body(p)))
        return self.post_list

    def get_latest_post(self):
        return self.populate_post_list(self.get_posts())[0]

    def post_to_webhook(self):
        latest_post = self.get_latest_post()
        msg_string = (latest_post['body'][:250] + '...') if len(latest_post['body']) > 250 else latest_post['body']
        embed = Webhook(hook_url, color=123123)
        embed.set_author(name=latest_post['title'], icon='https://cdn6.aptoide.com/imgs/5/1/f/51fc6f8666c50ce7456651810d7a4439_icon.png?w=240')
        embed.set_desc(msg_string)
        embed.add_field(name='Read more', value=latest_post['url'])
        embed.post()
