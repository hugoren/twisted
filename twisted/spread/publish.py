# Twisted, the Framework of Your Internet
# Copyright (C) 2001 Matthew W. Lefkowitz
# 
# This library is free software; you can redistribute it and/or
# modify it under the terms of version 2.1 of the GNU Lesser General Public
# License as published by the Free Software Foundation.
# 
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
# 
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

# Twisted imports
from twisted.internet import defer

# sibling imports
import jelly
import banana
import flavors

# System Imports
import time
import copy

class Publishable(flavors.Cacheable):
    """An object whose cached state persists across sessions.
    """
    def __init__(self, publishedID):
        self.republish()
        self.publishedID = publishedID

    def republish(self):
        """Set the timestamp to current and (TODO) update all observers.
        """
        self.timestamp = time.time()

    def view_getStateToPublish(self, perspective):
        '(internal)'
        return self.getStateToPublishFor(perspective)
    
    def getStateToPublishFor(self, perspective):
        """Implement me to special-case your state for a perspective.
        """
        return self.getStateToPublish()

    def getStateToPublish(self):
        """Implement me to return state to copy as part of the publish phase.
        """
        raise NotImplementedError("%s.getStateToPublishFor" % self.__class__)

    def getStateToCacheAndObserveFor(self, perspective, observer):
        """Get all necessary metadata to keep a clientside cache.
        """
        if perspective:
            pname = perspective.perspectiveName
            sname = perspective.getService().serviceName
        else:
            pname = "None"
            sname = "None"

        return {"remote": flavors.ViewPoint(perspective, self),
                "publishedID": self.publishedID,
                "perspective": pname,
                "service": sname,
                "timestamp": self.timestamp}

class RemotePublished(flavors.RemoteCache):
    """The local representation of remote Publishable object.
    """
    isActivated = 0
    _wasCleanWhenLoaded = 0
    def getFileName(self, ext='pub'):
        return ("%s-%s-%s.%s" %
                (self.service, self.perspective, str(self.publishedID), ext))
    
    def setCopyableState(self, state):
        self.__dict__.update(state)
        self._activationListeners = []
        try:
            data = open(self.getFileName()).read()
        except IOError:
            recent = 0
        else:
            newself = jelly.unjelly(banana.decode(data))
            recent = (newself.timestamp == self.timestamp)
        if recent:
            self._cbGotUpdate(newself.__dict__)
            self._wasCleanWhenLoaded = 1
        else:
            self.remote.callRemote('getStateToPublish').addCallbacks(self._cbGotUpdate)

    def __getstate__(self):
        other = copy.copy(self.__dict__)
        # Remove PB-specific attributes
        del other['broker']
        del other['remote']
        del other['luid']
        # remove my own runtime-tracking stuff
        del other['_activationListeners']
        del other['isActivated']
        return other

    def _cbGotUpdate(self, newState):
        self.__dict__.update(newState)
        self.isActivated = 1
        # send out notifications
        for listener in self._activationListeners:
            listener(self)
        self._activationListeners = []
        self.activated()
        open(self.getFileName(), "wb").write(banana.encode(jelly.jelly(self)))

    def activated(self):
        """Implement this method if you want to be notified when your
        publishable subclass is activated.
        """
        
    def callWhenActivated(self, callback):
        """Externally register for notification when this publishable has received all relevant data.
        """
        if self.isActivated:
            callback(self)
        else:
            self._activationListeners.append(callback)

def whenReady(d):
    """
    Wrap a deferred returned from a pb method in another deferred that
    expects a RemotePublished as a result.  This will allow you to wait until
    the result is really available.

    Idiomatic usage would look like:

        publish.whenReady(serverObject.getMeAPublishable()).addCallback(lookAtThePublishable)
    """
    d2 = defer.Deferred()
    d.addCallbacks(_pubReady, d2.armAndErrback,
                   callbackArgs=(d2,))
    return d2

def _pubReady(result, d2):
    '(internal)'
    result.callWhenActivated(d2.armAndCallback)
