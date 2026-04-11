# This module is part of GitPython and is released under the
# 3-Clause BSD License: https://opensource.org/license/bsd-3-clause/

"""Index utilities."""

__all__ = ["TemporaryFileSwap", "post_clear_cache", "default_index", "git_working_dir"]

import contextlib
from functools import wraps
import os
import os.path as osp
import struct
import tempfile
from types import TracebackType

# typing ----------------------------------------------------------------------

from typing import Any, Callable, TYPE_CHECKING, Optional, Type, cast

from git.types import Literal, PathLike, _T

if TYPE_CHECKING:
    from git.index import IndexFile

# ---------------------------------------------------------------------------------

# { Aliases
pack = struct.pack
unpack = struct.unpack
# } END aliases


class TemporaryFileSwap:
    """Utility class moving a file to a temporary location within the same directory and
    moving it back on to where on object deletion."""

    __slots__ = ("file_path", "tmp_file_path")

    def __init__(self, file_path: PathLike) -> None:
        self.file_path = file_path
        dirname, basename = osp.split(file_path)
        fd, self.tmp_file_path = tempfile.mkstemp(prefix=basename, dir=dirname)
        os.close(fd)
        with contextlib.suppress(OSError):  # It may be that the source does not exist.
            os.replace(self.file_path, self.tmp_file_path)

    def __enter__(self) -> "TemporaryFileSwap":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> Literal[False]:
        if osp.isfile(self.tmp_file_path):
            os.replace(self.tmp_file_path, self.file_path)
        return False


# { Decorators


def post_clear_cache(func: Callable[..., _T]) -> Callable[..., _T]:
    """Decorator for functions that alter the index using the git command.

    When a git command alters the index, this invalidates our possibly existing entries
    dictionary, which is why it must be deleted to allow it to be lazily reread later.
    """
    pass


def default_index(func: Callable[..., _T]) -> Callable[..., _T]:
    """Decorator ensuring the wrapped method may only run if we are the default
    repository index.

    This is as we rely on git commands that operate on that index only.
    """
    pass


def git_working_dir(func: Callable[..., _T]) -> Callable[..., _T]:
    """Decorator which changes the current working dir to the one of the git
    repository in order to ensure relative paths are handled correctly."""
    pass


# } END decorators
