#!/usr/bin/env python

# TODO: right now we assume that input files are pre-split.
# TODO: start up and close down mappers and reducers.

import threading

class Program(object):
    """Mrs Program (mapper, reducer, etc.)"""
    def __init__(self, mapper, reducer, partition):
        self.mapper = mapper
        self.reducer = reducer
        self.partition = partition

class Operation(object):
    """Specifies a map phase followed by a reduce phase.
    
    The output_format is a file format, such as HexFile or TextFile.
    """
    def __init__(self, mrs_prog, map_tasks=1, reduce_tasks=1,
            output_format=None):
        self.mrs_prog = mrs_prog
        self.map_tasks = map_tasks
        self.reduce_tasks = reduce_tasks

        if output_format is None:
            import io
            self.output_format = io.TextFile
        else:
            self.output_format = output_format


class Job(threading.Thread):
    """Keeps track of the parameters of the MR job and carries out the work.

    There are various ways to implement MapReduce:
    - serial execution on one processor
    - parallel execution on a shared-memory system
    - parallel execution with shared storage on a POSIX filesystem (like NFS)
    - parallel execution with a non-POSIX distributed filesystem

    To execute, make sure to do:
    job.inputs.append(input_filename)
    job.operations.append(mrs_operation)

    By the way, since Job inherits from threading.Thread, you can execute a
    MapReduce operation as a thread.  Slick, eh?
    """
    def __init__(self, **kwds):
        threading.Thread.__init__(self, **kwds)
        self.inputs = []
        self.operations = []

    def add_input(self, input):
        """Add a filename to be used for input to the map task.
        """
        self.inputs.append(input)

    def run(self):
        raise NotImplementedError(
                "I think you should have instantiated a subclass of Job.")

def interm_dir(basedir, reduce_id):
    """Pathname for the directory for intermediate output to reduce_id.
    """
    import os
    return os.path.join(basedir, 'interm_%s' % reduce_id)

def interm_file(basedir, map_id, reduce_id):
    """Pathname for intermediate output from map_id to reduce_id.
    """
    import os
    return os.path.join(basedir, 'interm_%s' % reduce_id, 'from_%s' % map_id)


class MapTask(threading.Thread):
    def __init__(self, taskid, mrs_prog, input, jobdir, reduce_tasks,
            **kwds):
        threading.Thread.__init__(self, **kwds)
        self.taskid = taskid
        self.mrs_prog = mrs_prog
        self.input = input
        self.jobdir = jobdir
        self.reduce_tasks = reduce_tasks

    def run(self):
        import os
        import io
        input_file = io.openfile(self.input)

        # create a new interm_name for each reducer
        interm_dirs = [interm_dir(self.jobdir, i)
                for i in xrange(self.reduce_tasks)]
        interm_filenames = [os.path.join(d, 'from_%s.hexfile' % self.taskid)
                for d in interm_dirs]
        interm_files = [io.HexFile(open(name, 'w'))
                for name in interm_filenames]

        mrs_map(self.mrs_prog.mapper, input_file, interm_files,
                partition=self.mrs_prog.partition)

        input_file.close()
        for f in interm_files:
            f.close()


# TODO: allow configuration of output format
class ReduceTask(threading.Thread):
    def __init__(self, taskid, mrs_prog, outdir, jobdir, **kwds):
        threading.Thread.__init__(self, **kwds)
        self.taskid = taskid
        self.mrs_prog = mrs_prog
        self.outdir = outdir
        self.jobdir = jobdir

    def run(self):
        import io
        import os, tempfile

        # SORT PHASE
        fd, sorted_name = tempfile.mkstemp(prefix='mrs.sorted_')
        os.close(fd)
        indir = interm_dir(self.jobdir, self.taskid)
        interm_names = [os.path.join(indir, s) for s in os.listdir(indir)]
        io.hexfile_sort(interm_names, sorted_name)

        # REDUCE PHASE
        sorted_file = io.HexFile(open(sorted_name))
        basename = 'reducer_%s' % self.taskid
        output_name = os.path.join(self.outdir, basename)
        #output_file = op.output_format(open(output_name, 'w'))
        output_file = io.TextFile(open(output_name, 'w'))

        mrs_reduce(self.mrs_prog.reducer, sorted_file, output_file)

        sorted_file.close()
        output_file.close()


def default_partition(x, n):
    return hash(x) % n

def mrs_map(mapper, input_file, output_files, partition=None):
    """Perform a map from the entries in input_file into output_files.

    If partition is None, output_files should be a single file.  Otherwise,
    output_files is a list, and partition is a function that takes a key and
    returns the index of the file in output_files to which that key should be
    written.
    """
    if partition is not None:
        N = len(output_files)
    while True:
        try:
            input = input_file.next()
            if partition is None:
                for key, value in mapper(*input):
                    output_files.write(key, value)
            else:
                for key, value in mapper(*input):
                    index = partition(key, N)
                    output_files[index].write(key, value)
        except StopIteration:
            return

def grouped_read(input_file):
    """An iterator that yields key-iterator pairs over a sorted input_file.

    This is very similar to itertools.groupby, except that we assume that the
    input_file is sorted, and we assume key-value pairs.
    """
    input_itr = iter(input_file)
    input = input_itr.next()
    next_pair = list(input)

    def subiterator():
        # Closure warning: don't rebind next_pair anywhere in this function
        group_key, value = next_pair

        while True:
            yield value
            try:
                input = input_itr.next()
            except StopIteration:
                next_pair[0] = None
                return
            key, value = input
            if key != group_key:
                # A new key has appeared.
                next_pair[:] = key, value
                return

    while next_pair[0] is not None:
        yield next_pair[0], subiterator()
    raise StopIteration


def mrs_reduce(reducer, input_file, output_file):
    """Perform a reduce from the entries in input_file into output_file.

    A reducer is an iterator taking a key and an iterator over values for that
    key.  It yields values for that key.
    """
    for key, iterator in grouped_read(input_file):
        for value in reducer(key, iterator):
            output_file.write(key, value)

# vim: et sw=4 sts=4
