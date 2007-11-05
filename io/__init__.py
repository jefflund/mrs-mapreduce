#!/usr/bin/env python

__all__ = ['TextFile', 'HexFile', 'hexfile_sort', 'fileformat', 'openfile']

from textfile import TextFile
from hexfile import HexFile, hexfile_sort

format_map = {
        '.txt': TextFile,
        '.hexfile': HexFile,
        }
default_format = TextFile

def fileformat(filename):
    """Guess the file format according to extension of the given filename."""
    import os
    extension = os.path.splitext(filename)[1]
    return format_map.get(extension, default_format)

# TODO: Find a better way to infer the file format.
def openfile(url, mode='r'):
    """Open a url or file to be read or written as a list of key-value pairs.
    
    The file format is inferred from the filename.
    """
    import urlparse, urllib2
    parsed_url = urlparse.urlparse(url, 'file')
    if parsed_url.scheme == 'file':
        f = open(parsed_url.path, mode)
    else:
        f = urllib2.urlopen(url)
    input_format = fileformat(url)
    return input_format(f)


# TODO: Make Output cache output in memory if it's not so big that it needs
# to be written to disk.
class Output(object):
    """Manage output for a map or reduce task."""
    def __init__(self, partition, n, directory=None, format='hexfile'):
        self.partition = partition
        self.n = n
        self.splits = [([], '') for i in xrange(n)]
        self.format = format

        if directory is None:
            from tempfile import mkdtemp
            self.directory = mkdtemp()
            self.temp = True
        else:
            self.directory = directory
            self.temp = False

    def close(self):
        if self.temp:
            import os
            os.removedirs(self.directory)

    def collect(self, itr):
        """Collect all of the key-value pairs from the given iterator."""
        if self.n == 1:
            bucket, filename = self.splits[0]
            append = bucket.append
            for key, value in itr:
                append((key, value))
            filename = self.path(0)
            self.splits[0] = bucket, filename
        else:
            for key, value in itr:
                split = self.partition(key, self.n)
                bucket, filename = self.splits[split]
                bucket.append((key, value))
                if not filename:
                    self.splits[split] = bucket, self.path(split)

    def path(self, index):
        """Return the path to the output split for the given index."""
        filename = "split_%s.%s" % (index, self.format)
        import os
        return os.path.join(self.directory, filename)

    def filenames(self):
        return [filename for bucket, filename in self.splits]

    def savetodisk(self):
        """Write out all of the key-value pairs to files."""
        for bucket, filename in self.splits:
            if filename is not None:
                f = openfile(filename, 'w')
                for key, value in bucket:
                    f.write(key, value)
                f.close()

# vim: et sw=4 sts=4
