# encoding: utf-8

"""
################################################################################
#                                                                              #
# Copyright 2013: Acebulf, alexames, PixelOrange, Snorrrlax, vaetrus, yaworsw  #
#                 and the moderators of http://www.reddit.com/r/changemyview   #
#                                                                              #
# This file is part of Deltabot sourcecode.                                    #
#                                                                              #
# Deltabot is free software: you can redistribute it and/or modify             #
# it under the terms of the GNU General Public License as published by         #
# the Free Software Foundation, either version 3 of the License, or            #
# (at your option) any later version.                                          #
#                                                                              #
# Deltabot is distributed in the hope that it will be useful,                  #
# but WITHOUT ANY WARRANTY; without even the implied warranty of               #
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the                #
# GNU General Public License for more details.                                 #
#                                                                              #
# You should have received a copy of the GNU General Public License            #
# along with Deltabot.  If not, see <http://www.gnu.org/licenses/>.            #
#                                                                              #
################################################################################
"""
from __future__ import print_function

import re
import os
import sys
import time
import praw
import logging
import calendar
from datetime import datetime, timedelta
import traceback
import collections
import random
from requests.exceptions import HTTPError
import sqlite3 as lite
import jinja2
from operator import itemgetter

try:
    from HTMLParser import HTMLParser
except ImportError:  # Python 3
    from html.parser import HTMLParser

import db

dispos = {
    'confirmed': 0,
    'comment_does_not_contain_token': 1,
    'comment_author_is_me': 2,
    'parent_author_is_me':3,
    'author_awarded_self': 4,
    'awarded_op': 5,
    'too_little_text': 6,
    'already_awarded_by_bot': 7,
    'already_awarded_in_this_tree': 8
}

rescannable_dispos = dispos['too_little_text'],
trivial_dispos = (dispos['comment_author_is_me'], 
                  dispos['comment_does_not_contain_token'])

logging.getLogger('requests').setLevel(logging.INFO)

def skippable_line(line):
    """ Returns true if the given line is a quote or code """
    return re.search('(^    |^ *&gt;)', line) is not None

def str_contains_token(text, tokens):
    """ Returns true if a given string contains one of the given tokens, as long
    as the token is not inside a quote or code block """
    lines = text.split('\n')
    in_quote = False
    for line in lines:
        if not line:  # Empty string
            in_quote = False
        if in_quote:
            continue
        if not skippable_line(line):
            for token in tokens:
                if token in line:
                    return True
        else:
            in_quote = True
    return False

def write_saved_id(filename, the_id):
    """ Write the previous comment's ID to file. """
    with open(filename, 'w') as _file:
        _file.write(the_id if the_id else "None")

def read_saved_id(filename):
    """ Get the last comment's ID from file. """
    logging.debug("Reading ID from file %s" % filename)
    try:
        with open(filename, 'r') as id_file:
            current = id_file.readline()
            if current == "None":
                current = None
        return current
    except IOError:
        return None

def get_longest_token_length(tokens):
    """
    Returns the length of the longest token within an iterable.
    Returns 0 if the list is empty or None
    """
    if tokens is None or len(tokens) == 0:
        return 0
    return len(max(tokens, key=lambda t: len(t)))

def load_templates(path):
    templates = {}
    root, dirs, fns = next(os.walk(path))
    for fn in fns:
        with open(os.path.join(path, fn), 'r', encoding='utf-8') as f:
            templates[os.path.splitext(fn)[0]] = jinja2.Template(f.read())
    for d in dirs:
        templates[d] = load_templates(os.path.join(path, d))
    return templates

class DeltaBot(object):
    def __init__(self, config, reddit):
        self.config = config
        self.running = False
        self.reddit = reddit

        logging.info('Connecting to reddit...')
        self.reddit.login(self.config.account['username'], self.config.account['password'])
        logging.info("Logged in as %s" % self.config.account['username'])

        self.subreddit = self.reddit.get_subreddit(self.config.subreddit)

        self.scanned_comments = collections.deque([], 10)

        most_recent_comment_id = read_saved_id(self.config.last_comment_filename)

        if most_recent_comment_id is not None:
            self.scanned_comments.append(most_recent_comment_id)

        self.minimum_comment_length = get_longest_token_length(self.config.tokens) + self.config.minimum_comment_length
        self.db = db.DatabaseManager(self.config.database)
        self.templates = load_templates('./config/templates')

        self.awarded_comments = []

    def climb_up(self, comment):
        if comment.is_root:
            return comment
        else:
            parent = self.reddit.get_info(thing_id=comment.parent_id)
            return self.climb_up(parent)

    def send_first_time_message(self, awardee):
        first_time_message = self.config.private_message % (self.config.subreddit, awardee)
        self.reddit.send_message(awardee,
            self.config.private_message_subject_line, first_time_message)

    def get_reply_text(self, comment, dispo, parent_comment=None):
        """ Replies to a comment with the type of message specified """
        if parent_comment is None:
            parent_comment = self.reddit.get_info(thing_id=comment.parent_id)
        dispo_code = next((k for k, v in dispos.items() if v == dispo), None)
        msg = self.templates['replies'][dispo_code].render(comment=comment, 
            parent_comment=parent_comment, config=self.config)
        return msg

    def string_matches_message(self, string, message_key, *args):
        messages = self.config.messages[message_key]
        for message in messages:
            appendation = self.config.messages['append_to_all_messages']
            full_message = (message % args) + appendation
            if string == full_message:
                return True
        return False

    def award_point(self, awarded_comment, awarding_comment):
        """ Awards a point. """
        logging.info("Awarding point to {}".format(awarded_comment.author.name))
        self.db.award_point(awarded_comment, awarding_comment)
        self.awarded_comments += awarded_comment

    def update_monthly_scoreboard(self, year, month, awards):
        logging.info("Updating monthly scoreboard")
        awardee_awards = {}
        for awardee in set([award['awarded_comment_author'] for award in awards]):
            awardee_awards[awardee] = [award for award in awards if award['awarded_comment_author'] == awardee]
        new_content = self.templates['monthly_scoreboard'].render(awardee_awards=awardee_awards)
        page_title = "scoreboard_%s_%s" % (year, month)
        self.reddit.edit_wiki_page(self.config.subreddit, page_title,
            new_content, "Updating monthly scoreboard")

    def adjust_point_flair(self, awardee, num):
        """ Update flair. """
        css_class = self.config.flair['css_class']
        current_flair = self.subreddit.get_flair(awardee)
        if current_flair['flair_css_class']:
            if self.config.flair['css_class'] not in current_flair['flair_css_class']:
                css_class = " ".join(filter(None, 
                    [ current_flair['flair_css_class'], 
                      self.config.flair['css_class'] ]))
        else:
            css_class = self.config.flair['css_class']

        self.subreddit.set_flair(awardee, self.config.flair['point_text'] % num, css_class)

    def get_most_recent_comment(self):
        """Finds the most recently scanned comment,
        so we know where to begin the next scan"""

        most_recent_comment_id = None
        while self.scanned_comments:
            comment = self.reddit.get_info(thing_id=self.scanned_comments[-1])
            if comment is not None:
                if comment.body == '[deleted]':
                    self.scanned_comments.pop()
                else:
                    most_recent_comment_id = self.scanned_comments[-1]
                    break
            else:
                most_recent_comment_id = self.scanned_comments[-1]
                break

        return most_recent_comment_id

    def already_awarded_in_this_tree(self, awarding_comment, awarded_comment=None):
        if awarded_comment is None:
            awarded_comment = self.reddit.get_info(thing_id=awarding_comment.parent_id)

        # first see if there's already a record of an award being given
        previous_awards = self.db.previous_awards_in_submission(awarded_comment, awarding_comment)

        # if nothing was found, then we're good to go
        if not previous_awards:
            return False

        # otherwise, check if the any of the previous awards come from the same root comment.
        else:
            awarded_comment_root = self.climb_up(awarded_comment)
            for previous_award in previous_awards:
                previous_awarding_comment = self.reddit.get_info(
                    thing_id='t1_'+previous_award['awarding_comment_id'])
                if self.climb_up(previous_awarding_comment).id == awarded_comment_root.id:
                    return True
        return False

    def already_awarded_by_bot(self, comment):
        return self.db.already_awarded_by_bot(comment)

    def dispo_comment(self, comment, strict=True):
        if not str_contains_token(comment.body, self.config.tokens) and strict:
            logging.info('String does not contain an award token')
            dispo = dispos['comment_does_not_contain_token']
            parent = None
        else:
            parent = self.reddit.get_info(thing_id=comment.parent_id)
            parent_author = parent.author.name
            comment_author = comment.author.name
            me = self.config.account['username']
            op = comment.submission.author.name

            if comment_author == me:
                logging.info("Reply was from {}".format(me))
                dispo = dispos['comment_author_is_me']

            elif parent_author == me:
                logging.info("Reply was to {}".format(me))
                dispo = dispos['parent_author_is_me']

            elif parent_author == comment_author:
                logging.info("Comment author attempted to award self")
                dispo = dispos['author_awarded_self']

            elif parent_author == op:
                logging.info("Comment author attempted to award OP")
                dispo = dispos['awarded_op']

            elif strict and len(comment.body) < self.minimum_comment_length:
                logging.info("Comment was too short")
                dispo = dispos['too_little_text']

            elif self.already_awarded_by_bot(comment):
                logging.info("Award has already been given for this comment")
                dispo = dispos['already_awarded_by_bot']

            elif strict and self.already_awarded_in_this_tree(comment, parent):
                logging.info("Comment author already awarded parent comment author in this comment tree")
                dispo = dispos['already_awarded_in_this_tree']

            else:
                logging.info("Comment meets criteria for awarding a point")
                dispo = dispos['confirmed']

        return dispo, parent

    def process_comment(self, comment, strict=True):
        logging.info("Processing comment {} by {}".format(
            comment.permalink, comment.author.name))

        dispo, parent = self.dispo_comment(comment, strict)

        prev_dispo_log = self.db.fetch_dispo_log_by_comment(comment)
        if not prev_dispo_log:
            if dispo not in trivial_dispos:
                reply = comment.reply(self.get_reply_text(comment, dispo, parent))
                reply.distinguish()
                self.db.log_dispo(comment, dispo, reply)
                if dispo == dispos['confirmed']:
                    self.award_point(parent, comment)
        else:
            if dispo != prev_dispo_log['dispo']:
                bots_reply = self.reddit.get_info(
                    thing_id=('t1_'+prev_dispo_log['reply_id']))
                if dispo in trivial_dispos:
                    bots_reply.delete()
                    self.db.delete_dispo_log(comment)
                else:
                    if dispo != dispos['already_awarded_by_bot']:
                        bots_reply.edit(self.get_reply_text(comment, dispo, parent))
                        self.db.log_dispo(comment, dispo, bots_reply)
                        if dispo == dispos['confirmed']:
                            self.award_point(parent, comment)            
        
    def scan_comments(self):
        """ Pull the most recent comments and search them for award tokens. If a token is found,
        award points. """
        logging.info("Scanning new comments")

        fresh_comments = self.subreddit.get_comments(
            params={'before': self.get_most_recent_comment()}, limit=None)

        for comment in fresh_comments:
            self.process_comment(comment)
            if (not self.scanned_comments) or (comment.name > self.scanned_comments[-1]):
                self.scanned_comments.append(comment.name)

    def rescan_comments(self):
        """Rescan comments with rescannable dispos"""
        logging.info("Rescanning comments")

        recent_logs = self.db.fetch_recent_dispo_logs(self.config.days_to_rescan)
        rescannable_logs = [log for log in recent_logs 
            if log['dispo'] in rescannable_dispos]

        for log in rescannable_logs:
            comment = self.reddit.get_info(thing_id='t1_'+log['comment_id'])
            self.process_comment(comment, log)

    def extract_comment_ids(self, message_body):
        comment_id_regex = ('(?:http://)?(?:www\.)?reddit\.com/r(?:eddit)?/' +
            self.config.subreddit + '/comments/[\d\w]+(?:/[^/]+)/?([\d\w]+)')
        return re.findall(comment_id_regex, message_body)

    def command_rescan(self, message_body, strict=True):
        comment_ids = self.extract_comment_ids(message_body)
        for comment_id in comment_ids:
            comment = self.reddit.get_info(thing_id='t1_'+comment_id)
            if type(comment) is praw.objects.Comment:
                self.process_comment(comment, strict=strict)

    def is_moderator(self, name):
        moderators = self.reddit.get_moderators(self.config.subreddit)
        mod_names = [mod.name for mod in moderators]
        return name in mod_names

    def scan_message(self, message):
        logging.info("Scanning message {} from {}".format(
            message.name, message.author))

        if self.is_moderator(message.author.name):
            command = message.subject.lower()
            if command == "force add":
                self.reddit.send_message("/r/" + self.config.subreddit,
                    "Force Add Detected", 
                    ("The Force Add command has been used on the following link(s):\n\n" +
                    message.body))

            if command == "add" or command == "force add":
                strict = (command != "force add")
                self.command_rescan(message.body, strict=strict)
                self.reddit.send_message(message.author, "Add complete",
                    "The add command has been completed on: " + message.body)

            elif command == "remove":
                # Todo
                pass

            elif command == "rescan":
                self.command_rescan(message.body)

            elif command == "reset":
                self.scanned_comments.clear()

            elif command == "stop":
                self.reddit.send_message("/r/" + self.config.subreddit,
                                         "Stop Message Confirmed",
                                         "NOTICE: The stop message has been "
                                         "issued and I have stopped running.")
                logging.warning("The stop command has been issued. If this was "
                                "not sent by you, please check as to why before"
                                " restarting.")
                message.mark_as_read()
                sys.exit(1)

    def scan_inbox(self):
        """ Scan a given list of messages for commands. If no list arg,
        then get newest comments from the inbox. """
        logging.info("Scanning inbox")

        messages = self.reddit.get_unread(unset_has_mail=True)

        for message in messages:
            kind = type(message)
            if kind == praw.objects.Comment:
                pass
            elif kind == praw.objects.Message:
                self.scan_message(message)

            message.mark_as_read()

    def scan_mod_mail(self):
        pass

    def update_top_css(self, leaders):
        """ Update the flair css for the top ten users """
        logging.info("Updating flair css for top 10 users")
        self.clear_leader_flair_css()
        
        for i, leader in enumerate(leaders):
            flair = self.subreddit.get_flair(leader)
            flair_text = flair['flair_text'] 
            current_css = flair['flair_css_class']
            new_class = self.config.flair['top1'] if (i == 0) else self.config.flair['top10']
            new_css = ' '.join(filter(None, [current_css, new_class]))
            self.subreddit.set_flair(leader, flair_text=flair_text, flair_css_class=new_css)

    def update_sidebar_scoreboard(self, leaders, month):
        """ Update the top 10 list with highest scores. """
        logging.info("Updating scoreboard")
        score_table = self.templates['sidebar_scoreboard'].render(leaders=leaders, 
            month=month)

        settings = self.subreddit.get_settings()
        old_desc = settings['description']
        # IMPORTANT: this splits the description on the _____ token.
        # Don't use said token for anything other than dividing sections
        # or else this breaks.
        split_desc = old_desc.split("_____")
        split_desc[-1] = score_table
        new_desc = "_____".join(split_desc).replace('&amp;', '&')
        self.subreddit.update_settings(description=new_desc)

    def update_wiki_tracker(self, awardee, awards):
        """ Update the wiki tracker page for an individual """
        logging.info('Updating wiki page for user {}'.format(awardee))
        # munge the raw awards data into a form suitable for rendering
        awarded_comments = []
        for awarded_comment_id in set([award['awarded_comment_id']
                for award in awards]):
            awards_for_comment = [award for award in awards if 
                award['awarded_comment_id'] == awarded_comment_id]
            awarded_comment = {key: awards_for_comment[0][key] for key in 
                awards_for_comment[0].keys() if 'awarding' not in key}
            awarded_comment['awarding_comments'] = [
                {key.replace('awarding_comment_', ''): award_for_comment[key] 
                for key in award_for_comment.keys() if 'awarding' in key} for 
                award_for_comment in awards_for_comment]
            awarded_comment['awarding_comments'].sort(key=lambda x: x['time'])
            awarded_comments.append(awarded_comment)

        new_content = self.templates['user_wiki_page'].render(awarde=awardee, 
            num_awards=len(awards), awarded_comments=awarded_comments, dt=datetime)
        self.reddit.edit_wiki_page(self.config.subreddit, "user/" + awardee, 
            new_content, "Updated awards.")

    def find_top_n(self, awards, n):

        def find_earliest_award(awardee):
            awardee_awards = [award for award in awards if 
                award['awarded_comment_author'] == awardee]
            awardee_awards.sort(key=lambda x: x['awarded_comment_time'])
            return awardee_awards[0]['awarded_comment_time']

        top_awardees = collections.Counter([award['awarded_comment_author'] 
            for award in awards]).most_common(n)
        tops = [
            {'awardee': awardee[0], 
             'num_awards': awardee[1], 
             'earliest_award_time': find_earliest_award(awardee[0])} 
            for awardee in top_awardees]
        return sorted(tops, key=lambda x: (x['num_awards'], -x['earliest_award_time']))

    def clear_leader_flair_css(self):
        top_csses = [value for key, value in self.config.flair.items()
            if key.startswith('top')]
        current_flairs = self.subreddit.get_flair_list()
        for flair in current_flairs:
            for css in top_csses:
                flair_class = flair['flair_css_class']
                if css in flair_class:
                    new_flair_class = re.sub(r'\s?' + css + r'\s?', ' ', 
                        flair_class).strip()
                else:
                    new_flair_class = ''
            self.subreddit.set_flair(flair['user'], 
                flair_text=flair['flair_text'], flair_css_class=new_flair_class)

    def go(self):
        """ Start DeltaBot. """
        self.running = True
        reset_counter = 0
        while self.running:
            old_comment_id = self.scanned_comments[-1] if self.scanned_comments else None
            logging.info("Starting iteration at %s" % old_comment_id or "None")

            self.scan_inbox()
            self.scan_mod_mail()
            self.scan_comments()

            if reset_counter == 0:
                self.rescan_comments()
                
            awardees = set([comment.author.name for comment in self.awarded_comments])
            self.awarded_comments.clear()
            while awardees:
                awardee = awardees.pop()
                awards = self.db.fetch_awards_by_awardee(awardee)

                num = len(awards)
                if num == 1:
                    self.send_first_time_message(awardee)
                self.adjust_point_flair(awardee, num)
                self.update_wiki_tracker(awardee, awards)

                if len(awardees) == 0:
                    now = datetime.utcnow()
                    monthly_awards = self.db.fetch_awards_by_month(now.year, now.month)
                    self.update_monthly_scoreboard(now.year, now.month, monthly_awards)
                    top10 = self.find_top_n(monthly_awards, 10)
                    self.update_top_css([top['awardee'] for top in top10])
                    self.update_sidebar_scoreboard(top10, now.strftime('%b'))

            if self.scanned_comments and (old_comment_id is not self.scanned_comments[-1]):
                write_saved_id(self.config.last_comment_filename,
                               self.scanned_comments[-1])

            logging.info("Iteration complete at %s" % (self.scanned_comments[-1] if
                                                       self.scanned_comments else "None"))
            reset_counter += 1
            print("Reset Counter at %s." % reset_counter)
            print("When this reaches 10, the script will clear its history.")
            if reset_counter == 10:
                self.scanned_comments.clear()
                reset_counter = 0
            logging.info("Sleeping for %s seconds" % self.config.sleep_time)
            time.sleep(self.config.sleep_time)
