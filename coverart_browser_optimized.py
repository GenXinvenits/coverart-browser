# -*- Mode: python; coding: utf-8; tab-width: 4; indent-tabs-mode: nil; -*-
"""Small performance layer for the CoverArt Browser plugin.

The original implementation remains in coverart_browser.py. This module keeps
the public plugin class unchanged while applying safe hot-path caches for
album metadata, album search and cover rendering.
"""

from gi.repository import Gdk
from gi.repository import Gtk
from gi.repository import Pango
from gi.repository import PangoCairo
from gi.repository import GdkPixbuf
from gi.repository import RB

import coverart_browser as _browser
import coverart_album as _album
from coverart_album import Album, AlbumFilters
from coverart_covericonview import CellRendererThumb

# Re-export the real plugin class for libpeas.
CoverArtBrowserPlugin = _browser.CoverArtBrowserPlugin


# ---------------------------------------------------------------------------
# Album metadata caches
# ---------------------------------------------------------------------------

def _album_artist_sort(self):
    if self._opt_album_artist_sort is None:
        self._opt_album_artist_sort = _album.uniquify_and_sort(
            [track.album_artist_sort for track in self._tracks])
    return self._opt_album_artist_sort


def _album_sort(self):
    if self._opt_album_sort is None:
        self._opt_album_sort = _album.uniquify_and_sort(
            [track.album_sort for track in self._tracks])
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
    if not getattr(self, '_optimized_composers_ready', False):
        composers = [track.composer for track in self._tracks if track.composer]
        self._opt_composers = ' '.join(set(composers)) if composers else None
        self._optimized_composers_ready = True
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


Album.album_artist_sort = property(_album_artist_sort)
Album.album_sort = property(_album_sort)
Album.artists = property(_artists)
Album.track_titles = property(_track_titles)
Album.composers = property(_composers)
Album.year = property(_year)
Album.genres = property(_genres)
Album.rating = property(_rating, Album.rating.fset)
Album.duration = property(_duration)

_original_do_modified = Album.do_modified


def _optimized_do_modified(self):
    self._opt_album_artist_sort = None
    self._opt_album_sort = None
    self._opt_artists = None
    self._opt_titles = None
    self._opt_composers = None
    self._optimized_composers_ready = False
    self._opt_year = None
    self._opt_genres = None
    self._opt_rating = None
    self._opt_duration = None
    self._optimized_search_text = None
    _original_do_modified(self)


Album.do_modified = _optimized_do_modified

_original_album_init = Album.__init__


def _optimized_album_init(self, name, artist, cover):
    _original_album_init(self, name, artist, cover)
    self._opt_album_artist_sort = None
    self._opt_album_sort = None
    self._opt_artists = None
    self._opt_titles = None
    self._opt_composers = None
    self._optimized_composers_ready = False
    self._opt_year = None
    self._opt_genres = None
    self._opt_rating = None
    self._opt_duration = None
    self._optimized_search_text = None


Album.__init__ = _optimized_album_init


# ---------------------------------------------------------------------------
# Cached global album search
# ---------------------------------------------------------------------------
@classmethod
def _optimized_global_filter(cls, searchtext=None):
    if not searchtext:
        return lambda album: True

    words = RB.search_fold(searchtext).split()

    def filt(album):
        search_cache = getattr(album, '_optimized_search_text', None)
        if search_cache is None:
            values = (
                album.name,
                album.artist,
                album.artists,
                album.track_titles,
                album.composers,
            )
            search_cache = ' '.join(
                RB.search_fold(value) for value in values if value)
            album._optimized_search_text = search_cache

        return all(word in search_cache for word in words)

    return filt


AlbumFilters.global_filter = _optimized_global_filter


# ---------------------------------------------------------------------------
# Cover renderer scaling cache
# ---------------------------------------------------------------------------

def _optimized_render(self, cr, widget, background_area, cell_area, flags):
    pixbuf = self.props.pixbuf
    if pixbuf is None:
        return

    target_width = cell_area.width - 2
    target_height = cell_area.height - 2
    if target_width <= 0 or target_height <= 0:
        return

    # Gtk reuses the renderer while scrolling. Keep a bounded cache so the
    # same source image is not repeatedly scaled for the same cell size.
    cache = getattr(self, '_scaled_pixbuf_cache', None)
    if cache is None:
        cache = {}
        self._scaled_pixbuf_cache = cache

    cache_key = (id(pixbuf), target_width, target_height)
    scaled = cache.get(cache_key)
    if scaled is None:
        scaled = pixbuf.scale_simple(
            target_width,
            target_height,
            GdkPixbuf.InterpType.NEAREST)
        if scaled is not None:
            if len(cache) >= 32:
                cache.pop(next(iter(cache)))
            cache[cache_key] = scaled

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
                calc_y_offset - 30)
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


CellRendererThumb.do_render = _optimized_render
