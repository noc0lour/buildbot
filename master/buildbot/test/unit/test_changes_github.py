# This file is part of Buildbot.  Buildbot is free software: you can
# redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, version 2.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Copyright Buildbot Team Members
import re

from twisted.internet import defer
from twisted.internet import reactor
from twisted.trial import unittest

from buildbot.changes.github import GitHubPullrequestPoller
from buildbot.test.util import changesource


class TestGitHubPullrequestPoller(changesource.ChangeSourceMixin, unittest.TestCase):

    def setUp(self):
        pass


    def tearDown(self):
        pass


    def test_PR(self):
        self.assertEqual(1,1)

