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
from twisted.python import log
from twisted.web import client

from buildbot.changes import base
from buildbot.util.state import StateMixin
from buildbot.util import ascii2unicode
from buildbot.util import datetime2epoch
from buildbot.util import epoch2datetime
from buildbot.util import httpclientservice

HOSTED_BASE_URL = "https://api.github.com"


class GitHubPullrequestPoller(base.PollingChangeSource, StateMixin):
    name = "GitHubPullrequestPoller"

    compare_attrs = ("owner", "repo", "token", "branch", "pollInterval",
                     "useTimestamps", "category", "project", "pollAtLaunch")

    db_class_name = 'GitHubPullrequestPoller'

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

        if hasattr(pullrequest_filter, '__call__'):
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

    def _getPulls(self):
        self.lastPoll = time.time()
        log.msg("GitHubPullrequestPoller: polling "
                "GitHub repository %s/%s, branches: %s" %
                (self.owner, self.repo, self.branches))
        d = self._http.get(
            '/'.join(['/repos', self.owner, self.repo, 'pulls']),
            timeout=self.pollInterval)

        @d.addCallback
        def process(github_json):
            return github_json.json()

        return d

    def _getEmail(self, user):
        d = self._http.get("/".join(['/users', user]),
                           timeout=self.pollInterval)

        @d.addCallback
        def process(github_json):
            email = github_json.json()

            @email.addCallback
            def return_email(result):
                return result["email"]

            return email

        return d

    def _getFiles(self, prnumber):
        log.msg("GitHubPullrequestPoller: fetching changed files"
                "GitHub repository %s/%s, Pullrequest: %s" %
                (self.owner, self.repo, prnumber))
        d = self._http.get("/".join([
            '/repos', self.owner, self.repo, 'pulls', str(prnumber), 'files'
        ]),
                           timeout=self.pollInterval)

        @d.addCallback
        def process(github_json):
            files = github_json.json()

            @files.addCallback
            def return_files(my_files):
                return [f["filename"] for f in my_files]

            return files

        return d

    def _getCurrentRev(self, prnumber):
        # Get currently assigned revision of PR number

        d = self._getStateObjectId()

        @d.addCallback
        def oid_callback(oid):
            current = self.master.db.state.getState(oid, 'pull_request%d' %
                                                    prnumber, None)

            @current.addCallback
            def result_callback(result):
                return result

            return current

        return d

    def _setCurrentRev(self, prnumber, rev):
        # Set the updated revision for PR number.

        d = self._getStateObjectId()

        @d.addCallback
        def oid_callback(oid):
            return self.master.db.state.setState(oid, 'pull_request%d' %
                                                 prnumber, rev)

        return d

    def _getStateObjectId(self):
        # Return a deferred for object id in state db.
        return self.master.db.state.getObjectId(
            '%s/%s' % (self.owner, self.repo), self.db_class_name)

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
        log.msg('GitHubPullrequestPoller: json api poll failed')
        log.err(f)
        # eat the failure to continue along the defered chain - we still want
        # to catch up
        return None

    def poll(self):
        d = self._getPulls()
        d.addCallback(self._processChanges)
        d.addErrback(self._processChangesFailure)
        return d
