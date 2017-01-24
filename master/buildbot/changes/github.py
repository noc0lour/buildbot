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

import os
import time
from datetime import datetime

from twisted.internet import defer
from twisted.internet import reactor
from twisted.web import client

from buildbot.changes import base
from buildbot.util.state import StateMixin
from buildbot.util import ascii2unicode
from buildbot.util import datetime2epoch
from buildbot.util import epoch2datetime
from buildbot.util import httpclientservice
from buildbot.util.logger import Logger

log = Logger()

HOSTED_BASE_URL = "https://api.github.com"


class GitHubPullrequestPoller(base.PollingChangeSource, StateMixin):
    compare_attrs = ("owner", "repo", "token", "branches", "pollInterval",
                     "useTimestamps", "category", "project", "pollAtLaunch")
    name = "GitHubPullrequestPoller"
    db_class_name = 'GitHubPullrequestPoller'

    def __init__(self,
                 owner,
                 repo,
                 **kwargs):
        if not kwargs.get("name"):
            kwargs["name"] = "GitHubPullrequestPoller:"+owner+"/"+repo
        base.PollingChangeSource.__init__(self, owner, repo, **kwargs)

    @defer.inlineCallbacks
    def reconfigService(self,
                        owner,
                        repo,
                        branches=None,
                        pollInterval=10 * 60,
                        useTimestamps=True,
                        category=None,
                        baseURL=None,
                        project='',
                        pullrequest_filter=True,
                        token=None,
                        name=None,
                        encoding='utf-8',
                        pollAtLaunch=False,
                        **kwargs):

        if name is None:
            kwargs["name"] = "GitHubPullrequestPoller:"+owner+"/"+repo
        yield base.PollingChangeSource.reconfigService(self, **kwargs)

        if baseURL is None:
            baseURL = HOSTED_BASE_URL
        if baseURL.endswith('/'):
            baseURL = baseURL[:-1]

        http_headers = {'User-Agent': 'Buildbot'}
        if not token is None:
            http_headers.update({'Authorization': 'token ' + token})

        self._http = yield httpclientservice.HTTPClientService.getService(
            self.master, baseURL, headers=http_headers)

        if not branches:
            branches = ['master']

        self.token = token
        self.owner = owner
        self.repo = repo
        self.branches = branches
        self.project = project
        self.encoding = encoding
        self.pollInterval = pollInterval

        if callable(pullrequest_filter):
            self.pullrequest_filter = pullrequest_filter
        else:
            self.pullrequest_filter = (lambda _: pullrequest_filter)

        self.lastChange = time.time()
        self.lastPoll = time.time()
        self.useTimestamps = useTimestamps
        self.category = category if callable(category) else ascii2unicode(
            category)
        self.project = ascii2unicode(project)

    def describe(self):
        return "GitHubPullrequestPoller watching the "\
            "GitHub repository %s/%s, branch: %s" % (
                self.owner, self.repo, self.branch)

    @defer.inlineCallbacks
    def _getPulls(self):
        self.lastPoll = time.time()
        log.debug("GitHubPullrequestPoller: polling "
                "GitHub repository %s/%s, branches: %s" %
                (self.owner, self.repo, self.branches))
        result = yield self._http.get(
            '/'.join(['/repos', self.owner, self.repo, 'pulls']),
            timeout=self.pollInterval)
        my_json = yield result.json()
        defer.returnValue(my_json)
        return

    @defer.inlineCallbacks
    def _getEmail(self, user):
        result = yield self._http.get("/".join(['/users', user]),
                                      timeout=self.pollInterval)
        my_json = yield result.json()
        defer.returnValue(my_json["email"])
        return

    @defer.inlineCallbacks
    def _getFiles(self, prnumber):
        result = yield self._http.get("/".join([
            '/repos', self.owner, self.repo, 'pulls', str(prnumber), 'files'
        ]),
                                      timeout=self.pollInterval)
        my_json = yield result.json()

        defer.returnValue([f["filename"] for f in my_json])
        return

    @defer.inlineCallbacks
    def _getCurrentRev(self, prnumber):
        # Get currently assigned revision of PR number

        result = yield self._getStateObjectId()
        rev = yield self.master.db.state.getState(result,
                                             'pull_request%d' % prnumber, None)
        defer.returnValue(rev)
        return

    @defer.inlineCallbacks
    def _setCurrentRev(self, prnumber, rev):
        # Set the updated revision for PR number.

        result = yield self._getStateObjectId()
        yield self.master.db.state.setState(result,
                                             'pull_request%d' % prnumber, rev)
    @defer.inlineCallbacks
    def _getStateObjectId(self):
        # Return a deferred for object id in state db.
        result = yield self.master.db.state.getObjectId(
            '%s/%s' % (self.owner, self.repo), self.db_class_name)
        defer.returnValue(result)
        return

    @defer.inlineCallbacks
    def _processChanges(self, github_result):
        for pr in github_result:
            # Track PRs for specified branches
            base_branch = pr['base']['ref']
            prnumber = pr['number']
            revision = pr['head']['sha']

            # Check to see if the branch is set or matches
            if base_branch not in self.branches:
                return
            current = yield self._getCurrentRev(prnumber)
            if not current or current[0:12] != revision[0:12]:
                # Access title, repo, html link, and comments
                branch = pr['head']['ref']
                title = pr['title']
                repo = pr['head']['repo']['name']
                revlink = pr['html_url']
                comments = pr['body']
                if self.useTimestamps:
                    updated = datetime.strptime(pr['updated_at'],
                                                '%Y-%m-%dT%H:%M:%SZ')
                else:
                    updated = epoch2datetime(reactor.seconds())

                # update database
                yield self._setCurrentRev(prnumber, revision)

                author = pr['user']['login']

                dl = defer.DeferredList(
                    [self._getFiles(prnumber), self._getEmail(author)],
                    consumeErrors=True)

                results = yield dl
                failures = [r[1] for r in results if not r[0]]
                if failures:
                    for failure in failures:
                        log.err(failure, "while processing changes for "
                                "Pullrequest {} revision {}".format(prnumber,
                                                                    revision))
                        # Fail on the first error!
                        failures[0].raiseException()
                [files, email] = [r[1] for r in results]

                if email is not None or email is not "null":
                    author += " <" + str(email) + ">"

                # emit the change
                yield self.master.data.updates.addChange(
                    author=ascii2unicode(author),
                    revision=ascii2unicode(revision),
                    revlink=ascii2unicode(revlink),
                    comments=u'pull-request #%d: %s\n%s\n%s' %
                    (prnumber, title, revlink, comments),
                    when_timestamp=datetime2epoch(updated),
                    branch=branch,
                    category=self.category,
                    project=self.project,
                    repository=ascii2unicode(repo),
                    files=files,
                    src=u'git')

    def _processChangesFailure(self, f):
        log.err('GitHubPullrequestPoller: json api poll failed')
        log.err(f)
        # eat the failure to continue along the defered chain - we still want
        # to catch up
        return None

    @defer.inlineCallbacks
    def poll(self):
        result = yield self._getPulls()
        self._processChanges(result)
