# This module is part of GitPython and is released under the
# 3-Clause BSD License: https://opensource.org/license/bsd-3-clause/

"""Functions that are supposed to be as fast as possible."""

__all__ = [
    "tree_to_stream",
    "tree_entries_from_data",
    "traverse_trees_recursive",
    "traverse_tree_recursive",
]

from stat import S_ISDIR

from git.compat import safe_decode, defenc

# typing ----------------------------------------------

from typing import (
    Callable,
    List,
    MutableSequence,
    Sequence,
    Tuple,
    TYPE_CHECKING,
    Union,
    overload,
)

if TYPE_CHECKING:
    from _typeshed import ReadableBuffer

    from git import GitCmdObjectDB

EntryTup = Tuple[bytes, int, str]  # Same as TreeCacheTup in tree.py.
EntryTupOrNone = Union[EntryTup, None]

# ---------------------------------------------------


def tree_to_stream(entries: Sequence[EntryTup], write: Callable[["ReadableBuffer"], Union[int, None]]) -> None:
    """Write the given list of entries into a stream using its ``write`` method.

    :param entries:
        **Sorted** list of tuples with (binsha, mode, name).

    :param write:
        A ``write`` method which takes a data string.
    """
    ord_zero = ord("0")
    bit_mask = 7  # 3 bits set.

    for binsha, mode, name in entries:
        mode_str = b""
        for i in range(6):
            mode_str = bytes([((mode >> (i * 3)) & bit_mask) + ord_zero]) + mode_str
        # END for each 8 octal value

        # git slices away the first octal if it's zero.
        if mode_str[0] == ord_zero:
            mode_str = mode_str[1:]
        # END save a byte

        # Here it comes: If the name is actually unicode, the replacement below will not
        # work as the binsha is not part of the ascii unicode encoding - hence we must
        # convert to an UTF-8 string for it to work properly. According to my tests,
        # this is exactly what git does, that is it just takes the input literally,
        # which appears to be UTF-8 on linux.
        if isinstance(name, str):
            name_bytes = name.encode(defenc)
        else:
            name_bytes = name  # type: ignore[unreachable]  # check runtime types - is always str?
        write(b"".join((mode_str, b" ", name_bytes, b"\0", binsha)))
    # END for each item


def tree_entries_from_data(data: bytes) -> List[EntryTup]:
    """Read the binary representation of a tree and returns tuples of
    :class:`~git.objects.tree.Tree` items.

    :param data:
        Data block with tree data (as bytes).

    :return:
        list(tuple(binsha, mode, tree_relative_path), ...)
    """
    pass


def _find_by_name(tree_data: MutableSequence[EntryTupOrNone], name: str, is_dir: bool, start_at: int) -> EntryTupOrNone:
    """Return data entry matching the given name and tree mode or ``None``.

    Before the item is returned, the respective data item is set None in the `tree_data`
    list to mark it done.
    """
    pass


@overload
def _to_full_path(item: None, path_prefix: str) -> None: ...


@overload
def _to_full_path(item: EntryTup, path_prefix: str) -> EntryTup: ...


def _to_full_path(item: EntryTupOrNone, path_prefix: str) -> EntryTupOrNone:
    """Rebuild entry with given path prefix."""
    pass


def traverse_trees_recursive(
    odb: "GitCmdObjectDB", tree_shas: Sequence[Union[bytes, None]], path_prefix: str
) -> List[Tuple[EntryTupOrNone, ...]]:
    """
    :return:
        List of list with entries according to the given binary tree-shas.

        The result is encoded in a list
        of n tuple|None per blob/commit, (n == len(tree_shas)), where:

        * [0] == 20 byte sha
        * [1] == mode as int
        * [2] == path relative to working tree root

        The entry tuple is ``None`` if the respective blob/commit did not exist in the
        given tree.

    :param tree_shas:
        Iterable of shas pointing to trees. All trees must be on the same level.
        A tree-sha may be ``None``, in which case ``None``.

    :param path_prefix:
        A prefix to be added to the returned paths on this level.
        Set it ``""`` for the first iteration.

    :note:
        The ordering of the returned items will be partially lost.
    """
    pass


def traverse_tree_recursive(odb: "GitCmdObjectDB", tree_sha: bytes, path_prefix: str) -> List[EntryTup]:
    """
    :return:
        List of entries of the tree pointed to by the binary `tree_sha`.

        An entry has the following format:

        * [0] 20 byte sha
        * [1] mode as int
        * [2] path relative to the repository

    :param path_prefix:
        Prefix to prepend to the front of all returned paths.
    """
    pass
