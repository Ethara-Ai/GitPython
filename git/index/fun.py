# This module is part of GitPython and is released under the
# 3-Clause BSD License: https://opensource.org/license/bsd-3-clause/

"""Standalone functions to accompany the index implementation and make it more
versatile."""

__all__ = [
    "write_cache",
    "read_cache",
    "write_tree_from_cache",
    "entry_key",
    "stat_mode_to_index_mode",
    "S_IFGITLINK",
    "run_commit_hook",
    "hook_path",
]

from io import BytesIO
import os
import os.path as osp
from pathlib import Path
from stat import S_IFDIR, S_IFLNK, S_IFMT, S_IFREG, S_ISDIR, S_ISLNK, S_IXUSR
import subprocess
import sys

from gitdb.base import IStream
from gitdb.typ import str_tree_type

from git.cmd import handle_process_output, safer_popen
from git.compat import defenc, force_bytes, force_text, safe_decode
from git.exc import HookExecutionError, UnmergedEntriesError
from git.objects.fun import (
    traverse_tree_recursive,
    traverse_trees_recursive,
    tree_to_stream,
)
from git.util import IndexFileSHA1Writer, finalize_process

from .typ import CE_EXTENDED, BaseIndexEntry, IndexEntry, CE_NAMEMASK, CE_STAGESHIFT
from .util import pack, unpack

# typing -----------------------------------------------------------------------------

from typing import Dict, IO, List, Sequence, TYPE_CHECKING, Tuple, Type, Union, cast

from git.types import PathLike

if TYPE_CHECKING:
    from git.db import GitCmdObjectDB
    from git.objects.tree import TreeCacheTup

    from .base import IndexFile

# ------------------------------------------------------------------------------------

S_IFGITLINK = S_IFLNK | S_IFDIR
"""Flags for a submodule."""

CE_NAMEMASK_INV = ~CE_NAMEMASK


def hook_path(name: str, git_dir: PathLike) -> str:
    """:return: path to the given named hook in the given git repository directory"""
    return osp.join(git_dir, "hooks", name)


def _has_file_extension(path: str) -> str:
    return osp.splitext(path)[1]


def run_commit_hook(name: str, index: "IndexFile", *args: str) -> None:
    """Run the commit hook of the given name. Silently ignore hooks that do not exist.

    :param name:
        Name of hook, like ``pre-commit``.

    :param index:
        :class:`~git.index.base.IndexFile` instance.

    :param args:
        Arguments passed to hook file.

    :raise git.exc.HookExecutionError:
    """
    hp = hook_path(name, index.repo.git_dir)
    if not os.access(hp, os.X_OK):
        return

    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = safe_decode(os.fspath(index.path))
    env["GIT_EDITOR"] = ":"
    cmd = [hp]
    try:
        if sys.platform == "win32" and not _has_file_extension(hp):
            # Windows only uses extensions to determine how to open files
            # (doesn't understand shebangs). Try using bash to run the hook.
            relative_hp = Path(hp).relative_to(index.repo.working_dir).as_posix()
            cmd = ["bash.exe", relative_hp]

        process = safer_popen(
            cmd + list(args),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=index.repo.working_dir,
        )
    except Exception as ex:
        raise HookExecutionError(hp, ex) from ex
    else:
        stdout_list: List[str] = []
        stderr_list: List[str] = []
        handle_process_output(process, stdout_list.append, stderr_list.append, finalize_process)
        stdout = "".join(stdout_list)
        stderr = "".join(stderr_list)
        if process.returncode != 0:
            stdout = force_text(stdout, defenc)
            stderr = force_text(stderr, defenc)
            raise HookExecutionError(hp, process.returncode, stderr, stdout)
    # END handle return code


def stat_mode_to_index_mode(mode: int) -> int:
    """Convert the given mode from a stat call to the corresponding index mode and
    return it."""
    if S_ISLNK(mode):  # symlinks
        return S_IFLNK
    if S_ISDIR(mode) or S_IFMT(mode) == S_IFGITLINK:  # submodules
        return S_IFGITLINK
    return S_IFREG | (mode & S_IXUSR and 0o755 or 0o644)  # blobs with or without executable bit


def write_cache(
    entries: Sequence[Union[BaseIndexEntry, "IndexEntry"]],
    stream: IO[bytes],
    extension_data: Union[None, bytes] = None,
    ShaStreamCls: Type[IndexFileSHA1Writer] = IndexFileSHA1Writer,
) -> None:
    """Write the cache represented by entries to a stream.

    :param entries:
        **Sorted** list of entries.

    :param stream:
        Stream to wrap into the AdapterStreamCls - it is used for final output.

    :param ShaStreamCls:
        Type to use when writing to the stream. It produces a sha while writing to it,
        before the data is passed on to the wrapped stream.

    :param extension_data:
        Any kind of data to write as a trailer, it must begin a 4 byte identifier,
        followed by its size (4 bytes).
    """
    # Wrap the stream into a compatible writer.
    stream_sha = ShaStreamCls(stream)

    tell = stream_sha.tell
    write = stream_sha.write

    # Header
    version = 3 if any(entry.extended_flags for entry in entries) else 2
    write(b"DIRC")
    write(pack(">LL", version, len(entries)))

    # Body
    for entry in entries:
        beginoffset = tell()
        write(entry.ctime_bytes)  # ctime
        write(entry.mtime_bytes)  # mtime
        path_str = str(entry.path)
        path: bytes = force_bytes(path_str, encoding=defenc)
        plen = len(path) & CE_NAMEMASK  # Path length
        assert plen == len(path), "Path %s too long to fit into index" % entry.path
        flags = plen | (entry.flags & CE_NAMEMASK_INV)  # Clear possible previous values.
        if entry.extended_flags:
            flags |= CE_EXTENDED
        write(
            pack(
                ">LLLLLL20sH",
                entry.dev,
                entry.inode,
                entry.mode,
                entry.uid,
                entry.gid,
                entry.size,
                entry.binsha,
                flags,
            )
        )
        if entry.extended_flags:
            write(pack(">H", entry.extended_flags))
        write(path)
        real_size = (tell() - beginoffset + 8) & ~7
        write(b"\0" * ((beginoffset + real_size) - tell()))
    # END for each entry

    # Write previously cached extensions data.
    if extension_data is not None:
        stream_sha.write(extension_data)

    # Write the sha over the content.
    stream_sha.write_sha()


def read_header(stream: IO[bytes]) -> Tuple[int, int]:
    """Return tuple(version_long, num_entries) from the given stream."""
    pass


def entry_key(*entry: Union[BaseIndexEntry, PathLike, int]) -> Tuple[PathLike, int]:
    """
    :return:
        Key suitable to be used for the
        :attr:`index.entries <git.index.base.IndexFile.entries>` dictionary.

    :param entry:
        One instance of type BaseIndexEntry or the path and the stage.
    """

    # def is_entry_key_tup(entry_key: Tuple) -> TypeGuard[Tuple[PathLike, int]]:
    #     return isinstance(entry_key, tuple) and len(entry_key) == 2

    if len(entry) == 1:
        entry_first = entry[0]
        assert isinstance(entry_first, BaseIndexEntry)
        return (entry_first.path, entry_first.stage)
    else:
        # assert is_entry_key_tup(entry)
        entry = cast(Tuple[PathLike, int], entry)
        return entry
    # END handle entry


def read_cache(
    stream: IO[bytes],
) -> Tuple[int, Dict[Tuple[PathLike, int], "IndexEntry"], bytes, bytes]:
    """Read a cache file from the given stream.

    :return:
        tuple(version, entries_dict, extension_data, content_sha)

        * *version* is the integer version number.
        * *entries_dict* is a dictionary which maps IndexEntry instances to a path at a
          stage.
        * *extension_data* is ``""`` or 4 bytes of type + 4 bytes of size + size bytes.
        * *content_sha* is a 20 byte sha on all cache file contents.
    """
    pass


def write_tree_from_cache(
    entries: List[IndexEntry], odb: "GitCmdObjectDB", sl: slice, si: int = 0
) -> Tuple[bytes, List["TreeCacheTup"]]:
    R"""Create a tree from the given sorted list of entries and put the respective
    trees into the given object database.

    :param entries:
        **Sorted** list of :class:`~git.index.typ.IndexEntry`\s.

    :param odb:
        Object database to store the trees in.

    :param si:
        Start index at which we should start creating subtrees.

    :param sl:
        Slice indicating the range we should process on the entries list.

    :return:
        tuple(binsha, list(tree_entry, ...))

        A tuple of a sha and a list of tree entries being a tuple of hexsha, mode, name.
    """
    tree_items: List["TreeCacheTup"] = []

    ci = sl.start
    end = sl.stop
    while ci < end:
        entry = entries[ci]
        if entry.stage != 0:
            raise UnmergedEntriesError(entry)
        # END abort on unmerged
        ci += 1
        rbound = entry.path.find("/", si)
        if rbound == -1:
            # It's not a tree.
            tree_items.append((entry.binsha, entry.mode, entry.path[si:]))
        else:
            # Find common base range.
            base = entry.path[si:rbound]
            xi = ci
            while xi < end:
                oentry = entries[xi]
                orbound = oentry.path.find("/", si)
                if orbound == -1 or oentry.path[si:orbound] != base:
                    break
                # END abort on base mismatch
                xi += 1
            # END find common base

            # Enter recursion.
            # ci - 1 as we want to count our current item as well.
            sha, _tree_entry_list = write_tree_from_cache(entries, odb, slice(ci - 1, xi), rbound + 1)
            tree_items.append((sha, S_IFDIR, base))

            # Skip ahead.
            ci = xi
        # END handle bounds
    # END for each entry

    # Finally create the tree.
    sio = BytesIO()
    tree_to_stream(tree_items, sio.write)  # Writes to stream as bytes, but doesn't change tree_items.
    sio.seek(0)

    istream = odb.store(IStream(str_tree_type, len(sio.getvalue()), sio))
    return (istream.binsha, tree_items)


def _tree_entry_to_baseindexentry(tree_entry: "TreeCacheTup", stage: int) -> BaseIndexEntry:
    pass


def aggressive_tree_merge(odb: "GitCmdObjectDB", tree_shas: Sequence[bytes]) -> List[BaseIndexEntry]:
    R"""
    :return:
        List of :class:`~git.index.typ.BaseIndexEntry`\s representing the aggressive
        merge of the given trees. All valid entries are on stage 0, whereas the
        conflicting ones are left on stage 1, 2 or 3, whereas stage 1 corresponds to the
        common ancestor tree, 2 to our tree and 3 to 'their' tree.

    :param tree_shas:
        1, 2 or 3 trees as identified by their binary 20 byte shas. If 1 or two, the
        entries will effectively correspond to the last given tree. If 3 are given, a 3
        way merge is performed.
    """
    pass
