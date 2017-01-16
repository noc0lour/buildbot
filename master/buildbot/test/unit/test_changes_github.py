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

from buildbot.test.fake import httpclientservice as fakehttpclientservice
from buildbot.test.fake import fakedb
from buildbot.test.fake.change import Change
from buildbot.changes.github import GitHubPullrequestPoller
from buildbot.test.util import changesource



class TestGitHubPullrequestPoller(changesource.ChangeSourceMixin, unittest.TestCase):

    @defer.inlineCallbacks
    def setUp(self):
        return self.setUpChangeSource()


    def tearDown(self):
        return self.tearDownChangeSource()

    @defer.inlineCallbacks
    def newChangeSource(self, owner, repo, **kwargs):
        http_headers = {'User-Agent': 'Buildbot'}
        token = kwargs.pop('token', None)
        if token:
            http_headers.update({'Authorization': 'token ' + token})
        s = GitHubPullrequestPoller(owner, repo, **kwargs)
        s._http = yield fakehttpclientservice.HTTPClientService.getFakeService(
            self.master, self, 'http://api.github.com/', headers=http_headers)
        self.attachChangeSource(s)
        s.configureService()
        return s


    # tests everytime we want to test something call s.expect(content_json = ) to load data to the http module

