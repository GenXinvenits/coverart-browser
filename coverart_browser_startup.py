"""CoverArt Browser Rhythmbox startup policy.

The performance entry point remains in ``coverart_browser``.  This wrapper
keeps the CoverArt source registered, prevents Rhythmbox's startup source
restore from initializing the browser, and keeps CoverArt's internal album
scan out of Rhythmbox's global loading/task bar.
"""

from coverart_browser import *  # noqa: F401,F403
from coverart_browser_source import CoverArtBrowserSource
from coverart_album import AlbumLoader
import coverart_browser_legacy
from gi.repository import GLib


_original_source_do_selected = CoverArtBrowserSource.do_selected
_original_load_albums = AlbumLoader.load_albums


class _CoverArtBrowserSourceNoGlobalTask(CoverArtBrowserSource):
    """CoverArt source that never publishes its album scan as a global task."""

    def do_get_status(self, *args):
        """Keep CoverArt's library scan out of Rhythmbox's task list.

        The legacy implementation creates RB.TaskProgressSimple here and
        registers it with the shell task list while AlbumLoader is scanning.
        That is the exact source of the bottom ``Loading...`` progress bar.
        CoverArt has its own status/search UI, so exposing this internal scan
        as a global Rhythmbox task is unnecessary.
        """
        return (self.status, '', 1)

    def do_selected(self):
        """Ignore source selection restored before Rhythmbox startup ends."""
        plugin = getattr(self.props, 'plugin', None)

        if plugin is not None and not getattr(plugin, '_startup_complete', False):
            print("CoverArtBrowser DEBUG - startup source selection ignored")
            return None

        print("CoverArtBrowser DEBUG - manual CoverArt selection")
        return super().do_selected()


# The source is instantiated by CoverArtBrowserPlugin.do_activate() from the
# legacy module's global namespace. Replace that symbol with the real GObject
# subclass rather than monkey-patching the already-registered source vfuncs.
# GObject virtual methods such as do_get_status are resolved through the class
# type, so this is required for Rhythmbox to actually use the override.
coverart_browser_legacy.CoverArtBrowserSource = _CoverArtBrowserSourceNoGlobalTask


def _background_load_albums(self, query_model):
    """Defer the initial library scan until the UI has been displayed."""
    if getattr(self, '_coverart_initial_scan_scheduled', False):
        return _original_load_albums(self, query_model)

    self._coverart_initial_scan_scheduled = True
    print("CoverArtBrowser DEBUG - scheduling background album scan")

    def start_scan():
        print("CoverArtBrowser DEBUG - starting background album scan")
        _original_load_albums(self, query_model)
        return False

    # Let GTK paint the CoverArt page first. AlbumLoader itself remains
    # chunked/idle based, so the scan does not block the UI afterwards.
    GLib.timeout_add(100, start_scan)


# Keep the automatic library scan, but make it background work. Do not expose
# its progress through Rhythmbox's global task list.
AlbumLoader.load_albums = _background_load_albums


def _disable_startup_autostart(self, *args, **kwargs):
    """Mark startup complete without automatically selecting CoverArt."""
    self._startup_complete = True
    print("CoverArtBrowser DEBUG - startup complete; autostart disabled")

    # If Rhythmbox restored CoverArt as the previous page before the library
    # completed, move back to Library now. This leaves CoverArt available for
    # explicit manual selection afterwards.
    try:
        if self.shell.props.selected_page == self.source:
            GLib.idle_add(
                self.shell.props.display_page_tree.select,
                self.shell.props.library_source
            )
    except Exception as error:
        print("CoverArtBrowser DEBUG - startup page reset failed: %s" % error)

    return None


# Keep the original plugin callback for the AUTOSTART preference disabled.
CoverArtBrowserPlugin.load_complete = _disable_startup_autostart
