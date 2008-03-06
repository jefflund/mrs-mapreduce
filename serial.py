# Mrs
# Copyright 2008 Andrew McNabb <amcnabb-mrs@mcnabbs.org>
#
# This file is part of Mrs.
#
# Mrs is free software: you can redistribute it and/or modify it under the
# terms of the GNU Lesser General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version.
#
# Mrs is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for
# more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with Mrs.  If not, see <http://www.gnu.org/licenses/>.

from mapreduce import Implementation

# TODO: rewrite Serial implementation to use job and to be more general
class Serial(Implementation):
    """MapReduce execution on a single processor
    """
    def run(self):
        """Run a MapReduce job in serial.
        """
        job = self.job
        job.start()

        # Run Tasks:
        while not job.done():
            # do stuff here

            job.check_done()

        job.join()


class MockParallel(Implementation):
    """MapReduce execution on POSIX shared storage, such as NFS
    
    Specify a directory located in shared storage which can be used as scratch
    space.

    Note that progress times often seem wrong in mockparallel.  The reason is
    that most of the execution time is in I/O, and mockparallel tries to load
    the input for all reduce tasks before doing the first reduce task.
    """
    def run(self):
        job = self.job
        job.start()

        # Run Tasks:
        while not job.done():
            task = job.schedule()
            # FIXME (busy loop):
            if task is None:
                continue
            task.active()
            task.run()
            task.finished()
            job.check_done()

        job.join()

# vim: et sw=4 sts=4
