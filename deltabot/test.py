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

import sys
py3k = sys.version_info > (3, 0)
import unittest
if sys.version_info > (3, 3):
    from unittest import mock
else:
    import mock
import logging
import os

import config
import deltabot
import praw

test_config = config.Config(os.getcwd() + '/config/config.json')
logging.getLogger('requests').setLevel(logging.WARNING)

def test_suite():
    cases = [TestScanComment]
    alltests = [unittest.TestLoader().loadTestsFromTestCase(case) for case in cases]
    return unittest.TestSuite(alltests)


class DeltaBotTestCase(unittest.TestCase):
    def setUp(self):
        MockReddit = mock.create_autospec(praw.Reddit)
        self.bot = deltabot.DeltaBot(config=test_config, reddit=MockReddit())

class TestScanComment(DeltaBotTestCase):

    def setUp(self):
        if py3k:
            super().setUp()
        else:
            super(TestScanComment, self).setUp()

        self.comment = mock.Mock(body=("a" * self.bot.minimum_comment_length))
        self.comment.author.name = 'Bob'
        self.parent = mock.Mock()
        self.parent.author.name = 'Sue'

        self.bot.already_replied = mock.create_autospec(
            self.bot.already_replied, return_value=False)
        self.bot.is_parent_commenter_author = mock.create_autospec(
            self.bot.is_parent_commenter_author, return_value=False)
        self.bot.points_already_awarded_to_ancestor = mock.create_autospec(
            self.bot.points_already_awarded_to_ancestor, return_value=False)
        self.bot.reddit.get_info.return_value = self.parent
        self.bot.award_points = mock.create_autospec(self.bot.award_points)

    @mock.patch('deltabot.logging', autospec=True)
    def test_correctly_awards_delta(self, mock_logging):
        """
        2 - If a comment contains a Delta Symbol, DeltaBot should award 1 point to the author of the comment's parent
        """
        
        test_messages = [(msg + test_config.messages['append_to_all_messages']) 
            % (self.parent.author, test_config.subreddit, self.parent.author)
            for msg in test_config.messages['confirmation']]
        
        for token in test_config.tokens:   # confirm all legal tokens work
            old_comment_body = self.comment.body
            self.comment.body += token

            self.bot.scan_comment(self.comment)
            
            self.assertEqual(self.bot.award_points.call_count, 1,
                "award_points not called or called multiple times")
            self.assertEqual(self.bot.award_points.call_args[0], 
                (self.parent.author.name, self.comment), 
                "Did not properly award a delta, awardee: %s" % self.bot.award_points.call_args[0][0])
            message = self.comment.reply.call_args[0][0]
            self.assertIn(message, test_messages,
                "Did not properly award a delta, sent wrong message: %s" % message)
            self.assertEqual(mock_logging.info.call_count, 1, 
                "Did not properly award a delta: %s" % mock_logging.info.call_args[0][0])

            self.bot.award_points.reset_mock()
            mock_logging.reset_mock()
            self.comment.body = old_comment_body

    @mock.patch('deltabot.logging', autospec=True)
    def test_awards_no_points_if_token_missing(self, mock_logging):
        """ 2.1 - If a comment does not contain a Delta Symbol, DeltaBot should not award a point """
        
        self.bot.scan_comment(self.comment)

        awardee = self.bot.award_points.call_args[0][0] if self.bot.award_points.called else None
        self.assertFalse(self.bot.award_points.called, 
            "Improperly awarded a delta, awardee: %s" % awardee)
        message = self.comment.reply.call_args[0][0] if self.comment.reply.called else None
        self.assertFalse(self.comment.reply.called, 
            "Improperly awarded a delta, sent wrong message: %s" % message)
        log = mock_logging.info.call_args[0][0]
        self.assertEqual(log, "No points awarded, comment does not contain Delta", 
            "Improperly awarded a delta: %s" % log)
    
    @mock.patch('deltabot.logging', autospec=True)
    def test_awards_no_points_if_parent_is_OP(self, mock_logging):
        """ 2.2 - If the parent is OP, DeltaBot should not award a point. """
        self.bot.is_parent_commenter_author.return_value = True
        test_messages = [(msg + test_config.messages['append_to_all_messages']) 
            for msg in test_config.messages['broken_rule']]
        self.comment.body += test_config.tokens[0]

        self.bot.scan_comment(self.comment)

        awardee = self.bot.award_points.call_args[0][0] if self.bot.award_points.called else None
        self.assertFalse(self.bot.award_points.called, 
            "Did not properly recognize a reply to OP, awardee: %s" % awardee)
        message = self.comment.reply.call_args[0][0] if self.comment.reply.called else None
        self.assertIn(message, test_messages, 
            "Did not properly recognize a reply to OP, sent wrong message: %s" % message)
        log = mock_logging.info.call_args[0][0]
        self.assertEqual(log, "No points awarded, parent is OP", 
            "Did not properly recognize a reply to DeltaBot")

    @mock.patch('deltabot.logging', autospec=True)
    def test_awards_no_points_if_parent_is_DeltaBot(self, mock_logging):
        """ 2.3 - If the parent is DeltaBot, DeltaBot should not award a point. """
        self.comment.body += test_config.tokens[0]
        self.parent.author.name = test_config.account['username']

        self.bot.scan_comment(self.comment)
        
        awardee = self.bot.award_points.call_args[0][0] if self.bot.award_points.called else None
        self.assertFalse(self.bot.award_points.called, 
            "Did not properly recognize a reply to DeltaBot, awardee: %s" % awardee)
        message = self.comment.reply.call_args[0][0] if self.comment.reply.called else None     
        self.assertFalse(self.comment.reply.called, 
            "Did not properly recognize a reply to DeltaBot, message: %s" % message)
        log = mock_logging.info.call_args[0][0]
        self.assertEqual(log, "No points awarded, replying to DeltaBot", 
            "Did not properly recognize a reply to DeltaBot")


    @mock.patch('deltabot.logging', autospec=True)
    def test_commenter_has_already_awarded_delta(self, mock_logging):
        """ 2.4 - The commenter has already awarded a delta to this comment."""
        self.comment.body += test_config.tokens[0]
        self.bot.already_replied.return_value = True

        self.bot.scan_comment(self.comment)


        awardee = self.bot.award_points.call_args[0][0] if self.bot.award_points.called else None
        self.assertFalse(self.bot.award_points.called, 
            "Did not properly recognize an already replied, awardee: %s" % awardee)
        message = self.comment.reply.call_args[0][0] if self.comment.reply.called else None       
        self.assertFalse(self.comment.reply.called, 
            "Did not properly recognize an already replied, sent wrong message: %s" % message)
        log = mock_logging.info.call_args[0][0]
        self.assertEqual(log, "No points awarded, already replied", 
            "Did not properly recognize an already replied: %s" % log)


    @mock.patch('deltabot.logging', autospec=True)
    def test_commenter_has_already_awarded_delta_at_higher_point_in_thread(self, mock_logging):
        """ 2.5 - The commenter has already awarded a delta to this comment."""
        self.comment.body += test_config.tokens[0]
        self.bot.points_already_awarded_to_ancestor.return_value = True
        test_messages = [(msg + test_config.messages['append_to_all_messages']) 
            % self.parent.author for msg in test_config.messages['already_awarded']]

        self.bot.scan_comment(self.comment)

        awardee = self.bot.award_points.call_args[0][0] if self.bot.award_points.called else None
        self.assertFalse(self.bot.award_points.called, 
            "Did not properly recognize an award to descendent, awardee: %s" % awardee)
        message = self.comment.reply.call_args[0][0] if self.comment.reply.called else None       
        self.assertIn(message, test_messages,
            "Did not properly recognize an award to descendent, sent wrong message: %s" % message)
        log = mock_logging.info.call_args[0][0]
        self.assertEqual(log, "No points awarded, already awarded", 
            "Did not properly recognize an award to descendent: %s" % log)
   
    @mock.patch('deltabot.logging', autospec=True)
    def test_comment_is_too_short(self, mock_logging):
        """ 2.6 - The comment is too short"""
        self.comment.body = self.comment.body[10:] + test_config.tokens[0]
        test_messages = [(msg + test_config.messages['append_to_all_messages']) 
            % self.parent.author for msg in test_config.messages['too_little_text']]

        self.bot.scan_comment(self.comment)

        awardee = self.bot.award_points.call_args[0][0] if self.bot.award_points.called else None
        self.assertFalse(self.bot.award_points.called, 
            "Did not properly recognize a short comment, awardee: %s" % awardee)
        message = self.comment.reply.call_args[0][0] if self.comment.reply.called else None
        self.assertIn(message, test_messages,
            "Did not properly recognize a short comment, sent wrong message: %s" % message)
        log = mock_logging.info.call_args[0][0]
        self.assertEqual(log, "No points awarded, too short", 
            "Did not properly recognize a short comment: %s" % log)

class TestAlreadyReplied(DeltaBotTestCase):
    def setUp(self):
        if py3k:
            super().setUp()
        else:
            super(TestAlreadyReplied, self).setUp()

        self.comment = mock.Mock()

        self.mock_comment = mock.Mock(replies=[])
        self.mock_submission = mock.Mock(comments=[self.mock_comment])
        self.bot.reddit.get_submission.return_value = self.mock_submission

    def test_no_replies(self):
        result = self.bot.already_replied(self.comment)

        self.assertFalse(result, "already_replied returns True with no replies")

    def test_one_bot_reply(self):
        reply = mock.create_autospec(praw.objects.Comment)
        reply.author = mock.create_autospec(praw.objects.Redditor)
        reply.author.name = test_config.account['username']
        self.mock_comment.replies = [reply]
        reply.__str__ = lambda x: self.bot.get_message('confirmation')

        result = self.bot.already_replied(self.comment)
        
        self.assertTrue(result, "already_replied returns False when DeltaBot is only reply")
    
class TestIsParentCommenterAuthor(DeltaBotTestCase):
    def setUp(self):
        if py3k:
            super().setUp()
        else:
            super(TestIsParentCommenterAuthor, self).setUp()

        comment_author = mock.create_autospec(praw.objects.Redditor)
        comment_author.name = "Someone"
        self.comment = mock.create_autospec(praw.objects.Comment)
        self.comment.submission.author = comment_author
        self.parent = mock.create_autospec(praw.objects.Comment)

    def test_with_op_parent(self):
        self.parent.author = self.comment.submission.author

        result = self.bot.is_parent_commenter_author(self.comment, self.parent)
        self.assertTrue(result, "is_parent_commenter_author() could not recognize OP as author")

    def test_with_op_not_parent(self):
        parent_author = mock.create_autospec(praw.objects.Redditor)
        parent_author.name = "SomeoneElse"
        self.parent.author = parent_author

        result = self.bot.is_parent_commenter_author(self.comment, self.parent)
        self.assertFalse(result, "is_parent_commenter_author() incorrectly recognized OP as author")

class TestAncestorPoints(DeltaBotTestCase):
    # Need a more complicated mock in order to test this
    def test_with_root_comment(self):
        pass

class TestIsCommentTooShort(DeltaBotTestCase):
    def test_no_comment(self):
        no_comment = mock.Mock(spec=praw.objects.Comment, body="")
        result = self.bot.is_comment_too_short(no_comment)
        self.assertTrue(result, "is_comment_too_short() returns False with empty comment")

    def test_short_comment(self):
        short_comment = mock.Mock(spec=praw.objects.Comment, body="a" * (self.bot.minimum_comment_length - 1))
        result = self.bot.is_comment_too_short(short_comment)
        self.assertTrue(result, "is_comment_too_short() returns False with short comment")

    def test_good_comment(self):
        good_comment = mock.Mock(spec=praw.objects.Comment, body="a" * self.bot.minimum_comment_length)
        result = self.bot.is_comment_too_short(good_comment)
        self.assertFalse(result, "is_comment_too_short() returns True with good comment")

    def test_long_comment(self):
        long_comment = mock.Mock(spec=praw.objects.Comment, body="a" * (self.bot.minimum_comment_length * 10))
        result = self.bot.is_comment_too_short(long_comment)
        self.assertFalse(result, "is_comment_too_short() returns True with long comment")

if __name__ == '__main__':
    unittest.main()
