# -*- Mode: python; coding: utf-8; tab-width: 4; indent-tabs-mode: nil; -*-
"""Performance entry point for CoverArt Browser.

The original plugin implementation is kept in coverart_browser_legacy.py.
This thin entry point applies low-risk performance improvements before
exporting the original plugin class to Rhythmbox.
"""

import coverart_album
import coverart_utils


def _fast_uniquify_and_sort(iterable):
    """Deduplicate in O(n) membership time, then sort once."""
    seen = set()
    unique = []
    for element in iterable:
        if element not in seen:
            seen.add(element)
            unique.append(element)
    return sorted(unique)


# Album metadata is recalculated frequently while a large library is loaded.
# The previous list-membership implementation was O(n^2) for duplicate checks.
coverart_utils.uniquify_and_sort = _fast_uniquify_and_sort
coverart_album.uniquify_and_sort = _fast_uniquify_and_sort


# Album.add_track() used to emit "modified" for every track. Keep the first
# notification synchronous so a newly created album is visible immediately,
# then coalesce subsequent notifications into one idle callback per album.
def _fast_album_add_track(self, track):
    was_empty = not self._tracks

    self._tracks.append(track)
    ids = (
        track.connect('modified', self._track_modified),
        track.connect('deleted', self._track_deleted)
    )
    self._signals_id[track] = ids

    if was_empty:
        self.emit('modified')
    elif not getattr(self, '_opti_modified_idle_id', 0):
        self._opti_modified_idle_id = coverart_album.GLib.idle_add(
            _emit_album_modified, self)


def _emit_album_modified(album):
    album._opti_modified_idle_id = 0
    album.emit('modified')
    return False


coverart_album.Album.add_track = _fast_album_add_track

# Avoid debug stdout traffic in two hot track-change callbacks.
def _quiet_track_modified(self, track):
    if track.album != self.name:
        self._track_deleted(track)
    else:
        self.emit('modified')


def _quiet_track_deleted(self, track):
    self._tracks.remove(track)
    for signal_id in self._signals_id[track]:
        track.disconnect(signal_id)
    del self._signals_id[track]

    if len(self._tracks) == 0:
        self.emit('emptied')
    else:
        self.emit('modified')


coverart_album.Album._track_modified = _quiet_track_modified
coverart_album.Album._track_deleted = _quiet_track_deleted


# Load the original Rhythmbox plugin class unchanged apart from the targeted
# patches above.
from coverart_browser_legacy import *  # noqa: F401,F403,E402
