"""Non-blocking exclusive file locks on POSIX and Windows."""

import sys

if sys.platform == 'win32':
    import msvcrt

    def try_lock(handle):
        try:
            # Lock one byte at the current offset; the region may lie beyond end of file.
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

else:
    import fcntl

    def try_lock(handle):
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False
