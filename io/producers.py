# Mrs
# Copyright 2008 Andrew McNabb <amcnabb-mrs@mcnabbs.org>
#
# This file is part of Mrs.
#
# Mrs is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# Mrs is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# Mrs.  If not, see <http://www.gnu.org/licenses/>.

# If BLOCKSIZE is too big, then latency will be high; if it's too low, then
# throughput will be low.
BLOCKSIZE = 1000

#TEST_HOST = 'www.mcnabbs.org'
TEST_HOST = 'cs.byu.edu'
TEST_PORT = 80

from twisted.web.client import HTTPClientFactory, HTTPPageDownloader
from twisted.internet import defer, reactor, abstract, interfaces, main
from zope.interface import implements

# TODO: make Buffer test with a StringIO, so we can make better tests.

class FileProducer(object):
    """Producer which reads data from a file.

    >>> FILENAME = '/etc/passwd'
    >>> consumer = TestConsumer()
    >>> producer = FileProducer(FILENAME, consumer)
    >>> producer.blocksize = 100
    >>> reactor.running = True
    >>> reactor.mainLoop()
    >>>

    After EOF in the FileProducer, the TestConsumer should have killed the
    reactor.  So, at this point, all of the data from the file should be
    in consumer.buffer.  Now we just need to make sure that the buffer
    contains the correct contents.

    >>> real_data = open(FILENAME).read()
    >>> real_data == consumer.buffer
    True
    >>>
    """

    implements(interfaces.IPushProducer, interfaces.IReadDescriptor)

    blocksize = BLOCKSIZE

    def __init__(self, filename, consumer):
        super(FileProducer, self).__init__()

        self.file = open(filename)
        self.fdnum = self.file.fileno()

        consumer.registerProducer(self, streaming=True)
        self.consumer = consumer

        self.start_reading()

    def doRead(self):
        """Called when data are available for reading

        To avoid blocking, read() will only be called once on the underlying
        file object.
        """
        newdata = self.file.read(self.blocksize)
        if newdata:
            self.consumer.write(newdata)
        else:
            # end-of-file
            return main.CONNECTION_DONE

    def start_reading(self):
        """Register with the Twisted reactor."""
        reactor.addReader(self)

    def stop_reading(self):
        """Unregister with the Twisted reactor."""
        reactor.removeReader(self)

    def pauseProducing(self):
        self.stop_reading()

    def resumeProducing(self):
        self.start_reading()

    def stopProducing(self):
        from twisted.python import failure
        connDone = failure.Failure(main.CONNECTION_DONE)
        self.connectionLost(connDone)

    def fileno(self):
        """Return the filenumber of the underlying file

        This will obviously fail if file is None or has no fileno.

        >>> consumer = TestConsumer()
        >>> b = FileProducer('/etc/passwd', consumer)
        >>> b.fileno() > 2
        True
        >>>
        """
        return self.fdnum

    def connectionLost(self, reason):
        self.stop_reading()
        self.consumer.unregisterProducer()

        # Cleanup
        self.file.close()
        self.file = None

    def logPrefix(self):
        return 'FileProducer'


class HTTPClientProducerProtocol(HTTPPageDownloader):
    """A varient of HTTPPageDownloader that lets you limit the buffer size."""

    def connectionMade(self):
        self.transport.bufferSize = self.factory.blocksize
        HTTPPageDownloader.connectionMade(self)


class HTTPClientProducerFactory(HTTPClientFactory):
    """Twisted protocol factory which serves as a Push Producer

    Set up the URL we will use for testing:
    >>> import sys
    >>> url = 'http://%s:%s/' % (TEST_HOST, TEST_PORT)
    >>>


    >>> consumer = TestConsumer()
    >>> factory = HTTPClientProducerFactory(url, consumer)
    >>> connector = reactor.connectTCP(TEST_HOST, TEST_PORT, factory)
    >>> factory.blocksize = 100
    >>> reactor.running = True
    >>> reactor.mainLoop()
    >>>

    After downloading completes, the TestConsumer should have killed the
    reactor.  So, at this point, all of the data from the file should be
    in consumer.buffer.  Now we just need to make sure that the buffer
    contains the correct contents.

    >>> import urllib
    >>> real_data = urllib.urlopen(url).read()
    >>> real_data == consumer.buffer
    True
    >>> open('file1', 'w').write(real_data)
    >>> open('file2', 'w').write(consumer.buffer)
    >>>
    """
    implements(interfaces.IPushProducer)

    blocksize = BLOCKSIZE
    protocol = HTTPClientProducerProtocol

    def __init__(self, url, consumer, **kwds):
        HTTPClientFactory.__init__(self, url, **kwds)

        self.in_progress = True
        self.consumer = consumer
        self.consumer.registerProducer(self, streaming=True)

    def buildProtocol(self, addr):
        import sys
        print >>sys.stderr, 'buildProtocol'
        self.protocol_instance = HTTPClientFactory.buildProtocol(self, addr)
        return self.protocol_instance

    def pageStart(self, partialContent):
        """Called by the protocol instance when connection starts."""
        if self.waiting:
            self.waiting = 0

    def pagePart(self, data):
        """Called by the protocol instance when a piece of data arrives."""
        import sys
        #print >>sys.stderr, 'pagePart'
        self.consumer.write(data)

    def pageEnd(self):
        """Called by the protocol instance when downloading is complete."""
        import sys
        #print >>sys.stderr, 'pageEnd'
        self.in_progress = False
        self.consumer.unregisterProducer()
        self.deferred.callback(None)

    def noPage(self, reason):
        """Called by the protocol instance when an error occurs."""
        import sys
        #print >>sys.stderr, 'noPage'
        self.consumer.unregisterProducer()
        if self.in_progress:
            self.deferred.errback(reason)

    def pauseProducing(self):
        """Called to pause streaming to the consumer."""
        self.protocol_instance.transport.stopReading()

    def resumeProducing(self):
        """Called to unpause streaming to the consumer."""
        self.protocol_instance.transport.startReading()

    def stopProducing(self):
        """Called to ask the producer to die."""
        self.protocol_instance.transport.loseConnection()


class TestConsumer(object):
    """Simple consumer for doctests."""

    implements(interfaces.IConsumer)

    def __init__(self):
        self.buffer = ''

    def registerProducer(self, producer, streaming):
        self.producer = producer
        self.streaming = streaming

    def unregisterProducer(self):
        self.producer = None
        import sys
        #print >>sys.stderr, "unregisterProducer"
        #reactor.stop()
        reactor.running = False

    def write(self, data):
        self.buffer += data
        if not self.streaming:
            self.producer.resumeProducing()


def test():
    import doctest
    #reactor.startRunning(installSignalHandlers=False)
    reactor.startRunning()
    reactor.running = False
    doctest.testmod()
    print 'done with testmod'

if __name__ == "__main__":
    test()

# vim: et sw=4 sts=4
