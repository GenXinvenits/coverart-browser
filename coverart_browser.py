# -*- Mode: python; coding: utf-8; tab-width: 4; indent-tabs-mode: nil; -*-
"""Performance entry point for CoverArt Browser.

The original plugin implementation remains in coverart_browser_legacy.py.
This module applies safe, behaviour-preserving optimisations to the model,
filter and cover-view hot paths before exporting the original plugin class.

The cover-art search-provider implementation is deliberately not modified.
"""

import gi
gi.require_version("PangoCairo", "1.0")

from collections import OrderedDict, deque

from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import Gtk
from gi.repository import Pango
from gi.repository import PangoCairo
from gi.repository import GdkPixbuf
from gi.repository import RB

import coverart_album
import coverart_covericonview
import coverart_utils


# ---------------------------------------------------------------------------
# Common collection hot path
# ---------------------------------------------------------------------------

def _fast_uniquify_and_sort(iterable):
    """Deduplicate in O(n), then sort once.

    The original helper used a list membership check while collecting unique
    values, making the duplicate-heavy case O(n^2).
    """
    seen = set()
    unique = []
    for element in iterable:
        if element not in seen:
            seen.add(element)
            unique.append(element)
    return sorted(unique)


coverart_utils.uniquify_and_sort = _fast_uniquify_and_sort
coverart_album.uniquify_and_sort = _fast_uniquify_and_sort


# ---------------------------------------------------------------------------
# Album metadata caches
# ---------------------------------------------------------------------------
# Album properties are read repeatedly by sorting, filtering, markup,
# tooltips and the views.  Keep None as the explicit "not cached" state so
# legitimate empty/zero results are cached as well.
def _album_artist_sort(self):
    if self._opt_album_artist_sort is None:
        self._opt_album_artist_sort = coverart_album.uniquify_and_sort(
            track.album_artist_sort for track in self._tracks)
    return self._opt_album_artist_sort


def _album_sort(self):
    if self._opt_album_sort is None:
        self._opt_album_sort = coverart_album.uniquify_and_sort(
            track.album_sort for track in self._tracks)
    return self._opt_album_sort


def _artists(self):
    if self._opt_artists is None:
        self._opt_artists = ', '.join(set(track.artist for track in self._tracks))
    return self._opt_artists


def _track_titles(self):
    if self._opt_titles is None:
        self._opt_titles = ' '.join(set(track.title for track in self._tracks))
    return self._opt_titles


def _composers(self):
    if self._opt_composers is None:
        composers = [track.composer for track in self._tracks if track.composer]
        self._opt_composers = ' '.join(set(composers)) if composers else None
    return self._opt_composers


def _year(self):
    if self._opt_year is None:
        real_years = [track.year for track in self._tracks if track.year != 0]
        self._opt_year = min(real_years) if real_years else 0
    return self._opt_year


def _genres(self):
    if self._opt_genres is None:
        self._opt_genres = set(track.genre for track in self._tracks)
    return self._opt_genres


def _rating(self):
    if self._opt_rating is None:
        ratings = [track.rating for track in self._tracks
                   if track.rating and track.rating != 0]
        self._opt_rating = sum(ratings) / len(self._tracks) if ratings else 0
    return self._opt_rating


def _duration(self):
    if self._opt_duration is None:
        self._opt_duration = sum(track.duration for track in self._tracks)
    return self._opt_duration


coverart_album.Album.album_artist_sort = property(_album_artist_sort)
coverart_album.Album.album_sort = property(_album_sort)
coverart_album.Album.artists = property(_artists)
coverart_album.Album.track_titles = property(_track_titles)
coverart_album.Album.composers = property(_composers)
coverart_album.Album.year = property(_year)
coverart_album.Album.genres = property(_genres)
coverart_album.Album.rating = property(
    _rating, coverart_album.Album.rating.fset)
coverart_album.Album.duration = property(_duration)

_original_album_init = coverart_album.Album.__init__
_original_album_modified = coverart_album.Album.do_modified
_original_album_add_track = coverart_album.Album.add_track
_original_album_track_deleted = coverart_album.Album._track_deleted
_original_album_get_tracks = coverart_album.Album.get_tracks


def _reset_album_caches(self):
    self._opt_album_artist_sort = None
    self._opt_album_sort = None
    self._opt_artists = None
    self._opt_titles = None
    self._opt_composers = None
    self._opt_year = None
    self._opt_genres = None
    self._opt_rating = None
    self._opt_duration = None
    self._opt_search_fields = None
    self._opt_folded_fields = None
    self._opt_folded_genres = None
    self._opt_sorted_tracks = None


def _optimized_album_init(self, name, artist, cover):
    _original_album_init(self, name, artist, cover)
    _reset_album_caches(self)


def _optimized_album_modified(self):
    _reset_album_caches(self)
    _original_album_modified(self)


def _optimized_album_add_track(self, track):
    # Invalidate before the signal is emitted as well as through do_modified.
    # This keeps the caches correct even if a consumer changes signal handling.
    _reset_album_caches(self)
    return _original_album_add_track(self, track)


def _optimized_album_track_deleted(self, track):
    _reset_album_caches(self)
    return _original_album_track_deleted(self, track)


def _optimized_get_tracks(self, rating_threshold=0):
    """Reuse the canonical track-number ordering.

    The legacy implementation sorts the complete track list on every call.
    Sorting is unnecessary when the album has not changed.  A fresh list is
    returned to preserve the legacy method's list-returning behaviour.
    """
    sorted_tracks = self._opt_sorted_tracks
    if sorted_tracks is None:
        sorted_tracks = sorted(
            self._tracks,
            key=lambda track: (track.disc_number, track.track_number))
        self._opt_sorted_tracks = sorted_tracks

    if not rating_threshold:
        return list(sorted_tracks)

    return [track for track in sorted_tracks
            if track.rating >= rating_threshold]


coverart_album.Album.__init__ = _optimized_album_init
coverart_album.Album.do_modified = _optimized_album_modified
coverart_album.Album.add_track = _optimized_album_add_track
coverart_album.Album._track_deleted = _optimized_album_track_deleted
coverart_album.Album.get_tracks = _optimized_get_tracks


# ---------------------------------------------------------------------------
# Cached folded album fields
# ---------------------------------------------------------------------------
def _search_fields(album):
    fields = album._opt_search_fields
    if fields is None:
        fields = tuple(
            RB.search_fold(value)
            for value in (
                album.name,
                album.artist,
                album.artists,
                album.track_titles,
                album.composers,
            )
            if value
        )
        album._opt_search_fields = fields
    return fields


def _folded_album_fields(album):
    fields = album._opt_folded_fields
    if fields is None:
        fields = {
            'name': RB.search_fold(album.name or ''),
            'artist': RB.search_fold(album.artist or ''),
            'artists': RB.search_fold(album.artists or ''),
            'track': RB.search_fold(album.track_titles or ''),
            'composers': RB.search_fold(album.composers or ''),
        }
        album._opt_folded_fields = fields
    return fields


def _folded_genres(album):
    genres = album._opt_folded_genres
    if genres is None:
        genres = RB.search_fold(' '.join(album.genres))
        album._opt_folded_genres = genres
    return genres


def _optimized_global_filter(cls, searchtext=None):
    if not searchtext:
        return lambda album: True

    words = tuple(RB.search_fold(searchtext).split())

    def filt(album):
        fields = _search_fields(album)
        return all(any(word in field for field in fields) for word in words)

    return filt


def _optimized_album_artist_filter(cls, searchtext=None):
    if not searchtext:
        return lambda album: True
    folded = RB.search_fold(searchtext)
    return lambda album: folded in _folded_album_fields(album)['artist']


def _optimized_artist_filter(cls, searchtext=None):
    if not searchtext:
        return lambda album: True
    folded = RB.search_fold(searchtext)
    return lambda album: folded in _folded_album_fields(album)['artists']


def _optimized_similar_artist_filter(cls, searchtext=None):
    if not searchtext:
        return lambda album: True

    words = tuple(RB.search_fold(searchtext).split())

    def filt(album):
        fields = _folded_album_fields(album)
        artist = fields['artist']
        artists = fields['artists']
        return all(word in artist or word in artists for word in words)

    return filt


def _optimized_album_name_filter(cls, searchtext=None):
    if not searchtext:
        return lambda album: True
    folded = RB.search_fold(searchtext)
    return lambda album: folded in _folded_album_fields(album)['name']


def _optimized_track_title_filter(cls, searchtext=None):
    if not searchtext:
        return lambda album: True
    folded = RB.search_fold(searchtext)
    return lambda album: folded in _folded_album_fields(album)['track']


def _optimized_composer_filter(cls, searchtext=None):
    if not searchtext:
        return lambda album: True
    folded = RB.search_fold(searchtext)
    return lambda album: folded in _folded_album_fields(album)['composers']


def _optimized_genre_filter(cls, searchtext=None):
    if not searchtext:
        return lambda album: True
    folded = RB.search_fold(searchtext)
    return lambda album: folded in _folded_genres(album)


def _optimized_model_filter(cls, model=None):
    if not model or not len(model):
        return lambda x: False

    albums = set()
    for row in model:
        entry = model[row.path][0]
        albums.add(entry.get_string(RB.RhythmDBPropType.ALBUM))

    return lambda album: album.name in albums


coverart_album.AlbumFilters.global_filter = classmethod(_optimized_global_filter)
coverart_album.AlbumFilters.album_artist_filter = classmethod(_optimized_album_artist_filter)
coverart_album.AlbumFilters.artist_filter = classmethod(_optimized_artist_filter)
coverart_album.AlbumFilters.similar_artist_filter = classmethod(_optimized_similar_artist_filter)
coverart_album.AlbumFilters.album_name_filter = classmethod(_optimized_album_name_filter)
coverart_album.AlbumFilters.track_title_filter = classmethod(_optimized_track_title_filter)
coverart_album.AlbumFilters.composer_filter = classmethod(_optimized_composer_filter)
coverart_album.AlbumFilters.genre_filter = classmethod(_optimized_genre_filter)
coverart_album.AlbumFilters.model_filter = classmethod(_optimized_model_filter)

# Keep the dispatch table in sync with the patched class methods.
coverart_album.AlbumFilters.keys['all'] = coverart_album.AlbumFilters.global_filter
coverart_album.AlbumFilters.keys['album_artist'] = coverart_album.AlbumFilters.album_artist_filter
coverart_album.AlbumFilters.keys['artist'] = coverart_album.AlbumFilters.artist_filter
coverart_album.AlbumFilters.keys['quick_artist'] = coverart_album.AlbumFilters.artist_filter
coverart_album.AlbumFilters.keys['similar_artist'] = coverart_album.AlbumFilters.similar_artist_filter
coverart_album.AlbumFilters.keys['album_name'] = coverart_album.AlbumFilters.album_name_filter
coverart_album.AlbumFilters.keys['track'] = coverart_album.AlbumFilters.track_title_filter
coverart_album.AlbumFilters.keys['composers'] = coverart_album.AlbumFilters.composer_filter
coverart_album.AlbumFilters.keys['genre'] = coverart_album.AlbumFilters.genre_filter
coverart_album.AlbumFilters.keys['model'] = coverart_album.AlbumFilters.model_filter


# ---------------------------------------------------------------------------
# AlbumsModel filter hot path
# ---------------------------------------------------------------------------
# Keep the original AlbumsModel implementation and optimize only the
# allocation in _album_filter. No filter state is cached because filters
# are mutable and the original implementation evaluates the current filter
# set on every call.
# ---------------------------------------------------------------------------

def _optimized_album_filter(self, album):
    for filter_func in self._filters.values():
        if not filter_func(album):
            return False
    return True

coverart_album.AlbumsModel._album_filter = _optimized_album_filter

# ---------------------------------------------------------------------------
# CoverRequester queue
# ---------------------------------------------------------------------------
# The original queue uses list membership plus pop(0), which becomes O(n^2)
# for large cover-search batches.  Keep the same one-at-a-time request
# semantics with deque + a membership set.
_original_requester_init = coverart_album.CoverRequester.__init__


def _optimized_requester_init(self, cover_db):
    _original_requester_init(self, cover_db)
    self._queue = deque()
    self._queue_set = set()


def _optimized_requester_add_to_queue(self, coverobjects, callback):
    for coverobject in coverobjects:
        if coverobject not in self._queue_set:
            self._queue.append(coverobject)
            self._queue_set.add(coverobject)
    self._start_process(callback)


def _optimized_requester_replace_queue(self, coverobjects, callback):
    self._queue.clear()
    self._queue_set.clear()
    for coverobject in coverobjects:
        if coverobject not in self._queue_set:
            self._queue.append(coverobject)
            self._queue_set.add(coverobject)
    self._start_process(callback)


def _optimized_requester_process_queue(self):
    while self._queue:
        coverobject = self._queue.popleft()
        self._queue_set.discard(coverobject)

        if coverobject.cover is self.unknown_cover:
            break
    else:
        coverobject = None

    if coverobject:
        self._callback(coverobject)
        self._queue_id += 1
        self._search_for_cover(coverobject, self._queue_id)
        Gdk.threads_add_timeout_seconds(
            GLib.PRIORITY_DEFAULT_IDLE, 40, self._next, self._queue_id)
    else:
        self._running = False
        self._callback(None)


def _optimized_requester_stop(self):
    self._queue.clear()
    self._queue_set.clear()


coverart_album.CoverRequester.__init__ = _optimized_requester_init
coverart_album.CoverRequester.add_to_queue = _optimized_requester_add_to_queue
coverart_album.CoverRequester.replace_queue = _optimized_requester_replace_queue
coverart_album.CoverRequester._process_queue = _optimized_requester_process_queue
coverart_album.CoverRequester.stop = _optimized_requester_stop


# ---------------------------------------------------------------------------
# Cover rendering cache
# ---------------------------------------------------------------------------
# Gtk reuses CellRendererThumb instances while scrolling. Cache scaled
# pixbufs per source pixbuf and target dimensions, but keep the cache bounded.
def _optimized_render(self, cr, widget, background_area, cell_area, flags):
    pixbuf = self.props.pixbuf
    if pixbuf is None:
        return

    target_width = cell_area.width - 2
    target_height = cell_area.height - 2
    if target_width <= 0 or target_height <= 0:
        return

    cache = getattr(self, '_scaled_pixbuf_cache', None)
    if cache is None:
        cache = OrderedDict()
        self._scaled_pixbuf_cache = cache

    cache_key = (pixbuf, target_width, target_height)
    scaled = cache.get(cache_key)
    if scaled is not None:
        cache.move_to_end(cache_key)
    else:
        scaled = pixbuf.scale_simple(
            target_width,
            target_height,
            GdkPixbuf.InterpType.NEAREST)
        if scaled is not None:
            cache[cache_key] = scaled
            cache.move_to_end(cache_key)
            while len(cache) > 32:
                cache.popitem(last=False)

    x_offset = cell_area.x + 1
    y_offset = cell_area.y + 1
    if scaled is not None:
        Gdk.cairo_set_source_pixbuf(cr, scaled, x_offset, y_offset)
        cr.paint()

    alpha = 0.40
    if flags & Gtk.CellRendererState.PRELIT:
        alpha -= 0.15
        if self.cell_area_source.hover_pixbuf:
            _, calc_x_offset, calc_y_offset = self.cell_area_source.calc_play_icon_offset(
                x_offset, y_offset)
            Gdk.cairo_set_source_pixbuf(
                cr,
                self.cell_area_source.hover_pixbuf,
                calc_x_offset,
                calc_y_offset - coverart_covericonview.PLAY_SIZE_Y)
            cr.paint()

    if not (self.cell_area_source.display_text and
            self.cell_area_source.display_text_pos is False):
        return

    layout_width = cell_area.width - 2
    pango_layout = PangoCairo.create_layout(cr)
    pango_layout.set_markup(self.markup, -1)
    pango_layout.set_alignment(self.cell_area_source.text_alignment)
    pango_layout.set_font_description(self.font_description)
    pango_layout.set_width(int(layout_width * Pango.SCALE))
    pango_layout.set_wrap(Pango.WrapMode.WORD_CHAR)
    _, he = pango_layout.get_pixel_size()

    rect_offset = y_offset + int((2.0 * self.cell_area_source.cover_size) / 3.0)
    rect_height = int(self.cell_area_source.cover_size / 3.0)

    if he > rect_height:
        pango_layout.set_ellipsize(Pango.EllipsizeMode.END)
        pango_layout.set_height(int((self.cell_area_source.cover_size / 3.0) * Pango.SCALE))
        _, he = pango_layout.get_pixel_size()

    cr.set_source_rgba(0.0, 0.0, 0.0, alpha)
    cr.set_line_width(0)
    cr.rectangle(x_offset, rect_offset, cell_area.width - 1, rect_height - 1)
    cr.fill()

    cr.set_source_rgba(1.0, 1.0, 1.0, 1.0)
    cr.move_to(
        x_offset,
        y_offset + 2.0 * self.cell_area_source.cover_size / 3.0
        + (((self.cell_area_source.cover_size / 3.0) - he) / 2.0))
    PangoCairo.show_layout(cr, pango_layout)


coverart_covericonview.CellRendererThumb.do_render = _optimized_render


# Load the original Rhythmbox plugin class unchanged apart from the targeted
# patches above.
from coverart_browser_legacy import *  # noqa: F401,F403,E402
