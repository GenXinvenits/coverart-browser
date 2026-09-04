"""CoverArt Browser Rhythmbox startup policy.

Keep Rhythmbox's normal source restoration and the plugin's AUTOSTART
preference intact.  The only startup-specific change is to defer the initial
album-model load until the GTK main loop is idle, so CoverArt can finish
constructing and displaying its UI before the expensive library processing
starts.
"""

from coverart_browser import *  # noqa: F401,F403
from coverart_album import AlbumLoader
import coverart_browser_legacy
from gi.repository import GLib


class _CoverArtBrowserSourceStartupSafe(CoverArtBrowserSource):
    """Initialize the normal CoverArt UI before starting its album load."""

    def do_impl_activate(self):
        # _setup_source() calls AlbumLoader.load_albums() synchronously. During
        # startup, replace that one call with an idle callback. The original
        # method is restored immediately after activation, so every later
        # explicit selection behaves exactly like the normal source.
        original_load_albums = AlbumLoader.load_albums

        def schedule_album_load(loader, query_model):
            print("CoverArtBrowser DEBUG - scheduling startup album load")

            def start_album_load():
                print("CoverArtBrowser DEBUG - starting startup album load")
                loader.load_albums(query_model)
                return GLib.SOURCE_REMOVE

            GLib.idle_add(start_album_load, priority=GLib.PRIORITY_DEFAULT_IDLE)

        AlbumLoader.load_albums = schedule_album_load
        try:
            super().do_impl_activate()
        finally:
            AlbumLoader.load_albums = original_load_albums


# CoverArtBrowserPlugin.do_activate() resolves CoverArtBrowserSource from the
# globals of coverart_browser_legacy.py. Replace that reference before the
# plugin instance is activated so the startup-safe subclass is instantiated.
coverart_browser_legacy.CoverArtBrowserSource = _CoverArtBrowserSourceStartupSafe


# ResultsGrid.initialise() attaches the cover-art overlay immediately. The
# normal change_view() path then attaches that same widget again when the
# compact view is selected during initial source setup. GTK rejects attaching
# a widget that already has a parent and emits a critical warning.
#
# Do not change the requested view state. If the overlay is already attached,
# detach it first; the original change_view() implementation will then perform
# its normal attach. This keeps the existing layout and view-switching logic
# unchanged while preventing the duplicate-parent operation.
_original_change_view = ResultsGrid.change_view


def _safe_change_view(self, entry_view, show_coverart):
    if show_coverart and self.overlay.get_parent() is self:
        self.remove(self.overlay)

    _original_change_view(self, entry_view, show_coverart)


ResultsGrid.change_view = _safe_change_view
