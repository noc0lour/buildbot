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
import json

from twisted.internet import defer
from twisted.internet import reactor
from twisted.trial import unittest

from buildbot.test.fake import httpclientservice as fakehttpclientservice
from buildbot.test.fake import fakedb
from buildbot.test.fake.change import Change
from buildbot.changes.github import GitHubPullrequestPoller
from buildbot.test.util import changesource

#Copied port of result from api.github.com/repos/buildbot/buildbot/pulls
gitJsonPayloadPullRequest = """
[
  {
    "html_url": "https://github.com/buildbot/buildbot/pull/4242",
    "number": 4242,
    "locked": false,
    "title": "Update the README with new information",
    "user": {
      "login": "defunkt"
    },
    "body": "This is a pretty simple change that we need to pull into master.",
    "updated_at": "2017-01-25T22:36:21Z",
    "head": {
      "ref": "cmp3",
      "sha": "4c9a7f03e04e551a5e012064b581577f949dd3a4",
      "repo": {
        "name": "buildbot"
      }
    },
    "base": {
      "ref": "master"
    }
  }
]
"""

gitJsonPayloadFiles = """
[
  {
    "filename": "README.md"
  }
]
"""

gitJsonUserPage = """
{
  "login": "defunkt",
  "email": "defunkt@defunkt.null"
}
"""
_CT_ENCODED = 'application/x-www-form-urlencoded'
_CT_JSON = 'application/json'

class TestGitHubPullrequestPoller(changesource.ChangeSourceMixin, unittest.TestCase):

    @defer.inlineCallbacks
    def setUp(self):
        yield self.setUpChangeSource()
        yield self.master.startService()

    @defer.inlineCallbacks
    def tearDown(self):
        yield self.master.stopService()
        yield self.tearDownChangeSource()

    @defer.inlineCallbacks
    def newChangeSource(self, owner, repo, **kwargs):
        http_headers = {'User-Agent': 'Buildbot'}
        token = kwargs.get('token', None)
        if token:
            http_headers.update({'Authorization': 'token ' + token})
        self._http = yield fakehttpclientservice.HTTPClientService.getFakeService(
            self.master, self, 'https://api.github.com', headers=http_headers)
        self.changesource = GitHubPullrequestPoller(owner, repo, pollAtLaunch=True, **kwargs)

    @defer.inlineCallbacks
    def startChangeSource(self):
        yield self.changesource.setServiceParent(self.master)
        yield self.attachChangeSource(self.changesource)

    @defer.inlineCallbacks
    def test_RequestEP(self):
        yield self.newChangeSource(
            'defunkt', 'defunkt', token='1234')
        self._http.expect(
            method='get', ep='/repos/defunkt/defunkt/pulls',
            content_json=json.loads(gitJsonPayloadPullRequest))
        self._http.expect(
            method='get', ep='/repos/defunkt/defunkt/pulls/4242/files',
            content_json=json.loads(gitJsonPayloadFiles))
        self._http.expect(
            method='get', ep='/users/defunkt',
            content_json=json.loads(gitJsonUserPage))
        yield self.startChangeSource()
        yield self.changesource.poll()

        self.assertEqual(1, 1)



    # tests everytime we want to test something call s.expect(content_json = ) to load data to the http module

