import json
import logging
import os
import time

import tweepy
from topia.termextract import tag

import secrets

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

tagger = tag.Tagger()
tagger.initialize()

__location__ = os.path.realpath(
        os.path.join(os.getcwd(), os.path.dirname(__file__)))

DRY_RUN = False

class Error(StandardError):
    pass
class NotProcessed(Error):
    pass

class FeedPrefixer(object):
    def __init__(self, source_username, username, state_filename):
        self.source_username = source_username
        self.username = username

        self.twitter = new_client()
        self.test_connection()

        # load user objects to make sure accounts exist
        self.source_user = self.lookup_account_by_username(source_username)
        self.user = self.lookup_account_by_username(username)

        self.dry_run = DRY_RUN

        self.state_filename = state_filename

    def run_once(self):
        log.info("run_once()")

        since_id = self.load_since_id()
        new_since_id = self.run_since(since_id)

        if new_since_id == since_id:
            return

        self.save_since_id(new_since_id)

    def load_since_id(self):
        log.info("Loading since_id from %r" % self.state_filename)
        f = open(self.state_filename, 'r')
        data = json.load(f)
        log.debug("loaded data: %r" % data)
        return data['since_id']

    def save_since_id(self, since_id):
        log.info("Saving since_id %d to %r" % (since_id, self.state_filename))
        f = open(self.state_filename, 'w')
        data = {
            'timestamp': time.time(),
            'since_id': since_id,
        }

        if self.dry_run:
            log.info("(Not saving due to dry run)")
        else:
            json.dump(data, f)

    def test_connection(self):
        log.info('Connecting to twitter...')
        self.twitter.verify_credentials()
        log.info('OK')

    def lookup_account_by_username(self, username):
        log.debug('Looking up twitter screen name %r' % username)
        try:
            return self.twitter.get_user(screen_name=username)
        except tweepy.error.TweepError as e:
            log.warn('Failed to look up %r: %r' % (username, e))
            raise

    def statuses_cursor(self, user, *args, **kwargs):
        """
        Get statuses for given user

        c = fp.statuses_cursor(user, since_id=foo)
        limit = 10
        for status in c.items(limit):
            process(status)
        """
        log.debug("Cursor over tweets for %r: %r, %r" % (user, args, kwargs))
        return tweepy.Cursor(self.twitter.user_timeline, user_id=user.id,
                             *args, **kwargs)

    def source_tweets_since(self, since_id):
        c = self.statuses_cursor(self.source_user, since_id=since_id)
        return c.items()

    def is_retweet(self, status):
        return hasattr(status, 'retweeted_status')

    def is_at_mention(self, status):
        if status.entities['user_mentions']:
            return True
        else:
            return False

    def cyberify(self, status):
        return cyberify_string(status.text)

    def tweet(self, message):
        log.info('Tweeting %r' % message)

        if self.dry_run:
            log.info('(dry run)')
        else:
            return self.twitter.update_status(message)

    def run_since(self, since_id):
        """
        Process all tweets since `since_id` and return the ID of the last
        status processed.

        If no tweets are processed, return since_id.
        """

        log.info("Looking for tweets since ID %r" % since_id)
        new_tweets = list(self.source_tweets_since(since_id))
        log.info("Found %d new tweets" % len(new_tweets))

        if not new_tweets:
            log.info("Nothing to do")
            return since_id

        for status in reversed(new_tweets):
            self.process(status)

        return status.id

    def process(self, status):
        log.info("Processing status %d: %r" % (status.id, status.text))
        if self.is_retweet(status):
            log.info("Skipping retweet")
            return False
        if self.is_at_mention(status):
            log.info("Skipping @mention")
            return False

        try:
            new_text = self.cyberify(status)
        except NotProcessed, e:
            log.info("Skipping, %s" % e)
            return False

        self.tweet(new_text)

    # def _DELETE_ALL_TWEETS(self):
    #     print 'THIS WILL DELETE ALL TWEETS'
    #     print 'ACCOUNT: ', self.twitter.me().screen_name
    #     ans = raw_input('Enter DESTROY to continue: ')
    #     log.warn('DELETING ALL TWEETS')
    #     assert ans == 'DESTROY'
    #     for status in self.twitter.user_timeline():
    #         log.warn('DELETING %r' % status.text)
    #         status.destroy()
    #     log.warn('DONE')

def new_client():
    auth = tweepy.OAuthHandler(secrets.CONSUMER_KEY, secrets.CONSUMER_SECRET)
    auth.set_access_token(secrets.ACCESS_TOKEN, secrets.ACCESS_TOKEN_SECRET)
    return tweepy.API(auth)

def cyberify_string(headline):
    tagged = tagger(headline)
    # Find cyberthings to replace
    for i, word in enumerate(tagged):
        # Skip the first word because the logic doesn't work for it.
        # Experimentation suggests that prefixing the first word isn't very
        # funny anyway.
        if i == 0:
            continue

        # Avoid having two "cybers" in a row
        if is_replaceable(word) and not is_replaceable(tagged[i-1]):
            headline = headline.replace(' ' + word[0], ' cyber' + word[0], 1)

    # Don't tweet anything that's too long
    # TODO: don't replace words that would take us over the limit
    if len(headline) > 140:
        raise NotProcessed('tweet is too long')

    # Don't tweet anything where a replacement hasn't been made
    if "cyber" not in headline:
        raise NotProcessed('no changes to make')
    else:
        return headline

def is_replaceable(word):
    # Prefix any noun (singular or plural) that begins with a lowercase letter
    if (word[1] == 'NN' or word[1] == 'NNS') and word[0][0].isalpha \
        and word[0][0].islower():
        return True
    else:
        return False



DEFAULT_FEEDPREFIXER = FeedPrefixer('nytminuscontext', 'cyber_nyt',
                                    os.path.join(__location__, 'state.json'))
