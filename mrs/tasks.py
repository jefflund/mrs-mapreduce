# Mrs
# Copyright 2008-2011 Brigham Young University
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
#
# Inquiries regarding any further use of Mrs, please contact the Copyright
# Licensing Office, Brigham Young University, 3760 HBLL, Provo, UT 84602,
# (801) 422-9339 or 422-3821, e-mail copyright@byu.edu.

"""MapReduce Tasks.

A Task represents a unit of work and the mechanism for carrying it out.
"""

from . import datasets
from . import fileformats
from . import util


class Task(object):
    """Manage input and output for a piece of a map or reduce operation.

    The `task_index` determines the split of the input dataset that will be
    used by this Task, as well as the source number that will be created by
    this Task.
    """
    #def __init__(self, op, input, task_index, splits, storage, format,
    #        permanent):
    def __init__(self, dataset_id, task_index, op, input, splits, storage,
            format, permanent):
        self.dataset_id = dataset_id
        self.task_index = task_index
        self.op = op
        self.input = input
        self.splits = splits
        self.storage = storage
        if format is None:
            format = fileformats.default_write_format
        self.format = format
        self.permanent = permanent

        self.output = None

    def outurls(self):
        return [(b.split, b.url) for b in self.output[:, :] if len(b)]

    @staticmethod
    def from_op(op, *args):
        if isinstance(op, ReduceMapOperation):
            task_class = ReduceMapTask
        elif isinstance(op, MapOperation):
            task_class = MapTask
        elif isinstance(op, ReduceOperation):
            task_class = ReduceTask
        else:
            raise RuntimeError('Unknown operation type')
        return task_class(op, *args)


class MapTask(Task):
    def run(self, program, serial=False):
        assert isinstance(self.op, MapOperation)

        # SETUP INPUT
        self.input.fetchall()
        if serial:
            all_input = self.input.data()
        else:
            all_input = self.input.splitdata(self.task_index)

        if self.storage and (self.splits > 1):
            prefix = 'source_%s_' % self.task_index
            subdir = util.mktempdir(self.storage, prefix)
        else:
            subdir = self.storage

        # MAP PHASE
        map_itr = self.op.map(program, all_input)
        self.output = datasets.LocalData(map_itr, self.splits,
                source=self.task_index, parter=self.op.parter(program),
                dir=subdir, format=self.format, permanent=self.permanent)


class ReduceTask(Task):
    def run(self, program, serial=False):
        assert isinstance(self.op, ReduceOperation)

        # SORT PHASE
        self.input.fetchall()
        if serial:
            all_input = self.input.data()
        else:
            all_input = self.input.splitdata(self.task_index)
        sorted_input = sorted(all_input)

        if self.storage and (self.splits > 1):
            prefix = 'source_%s_' % self.task_index
            subdir = util.mktempdir(self.storage, prefix)
        else:
            subdir = self.storage

        # Do the following if external sort is necessary (i.e., the input
        # files are too big to fit in memory):
        #fd, sorted_name = tempfile.mkstemp(prefix='mrs.sorted_')
        #os.close(fd)
        #io.hexfile_sort(interm_names, sorted_name)

        # REDUCE PHASE
        reduce_itr = self.op.reduce(program, sorted_input)
        self.output = datasets.LocalData(reduce_itr, self.splits,
                source=self.task_index, parter=self.op.parter(program),
                dir=subdir, format=self.format, permanent=self.permanent)


class ReduceMapTask(Task):
    def run(self, program, serial=False):
        assert isinstance(self.op, ReduceMapOperation)

        # SETUP INPUT
        self.input.fetchall()
        if serial:
            all_input = self.input.data()
        else:
            all_input = self.input.splitdata(self.task_index)
        sorted_input = sorted(all_input)

        if self.storage and (self.splits > 1):
            prefix = 'source_%s_' % self.task_index
            subdir = util.mktempdir(self.storage, prefix)
        else:
            subdir = self.storage

        # REDUCEMAP PHASE
        reduce_itr = self.op.reduce(program, sorted_input)
        map_itr = self.op.map(program, reduce_itr)
        self.output = datasets.LocalData(map_itr, self.splits,
                source=self.task_index, parter=self.op.parter(program),
                dir=subdir, format=self.format, permanent=self.permanent)


class Operation(object):
    def __init__(self, part_name):
        self.part_name = part_name

    def parter(self, program):
        return getattr(program, self.part_name)


class MapOperation(Operation):
    def __init__(self, **kwds):
        map_name = kwds['map_name']
        del kwds['map_name']
        super(MapOperation, self).__init__(**kwds)
        self.map_name = map_name
        self.id = '%s' % self.map_name

    def map(self, program, input):
        """Yields map output iterating over the entries in input."""
        if self.map_name is None:
            mapper = None
        else:
            mapper = getattr(program, self.map_name)

        for inkey, invalue in input:
            for key, value in mapper(inkey, invalue):
                yield (key, value)


class ReduceOperation(Operation):
    def __init__(self, **kwds):
        reduce_name = kwds['reduce_name']
        del kwds['reduce_name']
        super(ReduceOperation, self).__init__(**kwds)
        self.reduce_name = reduce_name
        self.id = '%s' % self.reduce_name

    def reduce(self, program, input):
        """Yields reduce output iterating over the entries in input.

        A reducer is an iterator taking a key and an iterator over values for
        that key.  It yields values for that key.
        """
        if self.reduce_name is None:
            reducer = None
        else:
            reducer = getattr(program, self.reduce_name)

        for key, iterator in grouped_read(input):
            for value in reducer(key, iterator):
                yield (key, value)


class ReduceMapOperation(MapOperation, ReduceOperation):
    def __init__(self, **kwds):
        super(ReduceMapOperation, self).__init__(**kwds)
        self.id = '%s_%s' % (self.reduce_name, self.map_name)


def grouped_read(input_file):
    """Yields key-iterator pairs over a sorted input_file.

    This is very similar to itertools.groupby, except that we assume that
    the input_file is sorted, and we assume key-value pairs.
    """
    input_itr = iter(input_file)
    input = next(input_itr)
    next_pair = list(input)

    def subiterator():
        # Closure warning: don't rebind next_pair anywhere in this function
        group_key, value = next_pair

        while True:
            yield value
            try:
                input = next(input_itr)
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

# vim: et sw=4 sts=4