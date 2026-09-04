"""CoverArt Browser Rhythmbox startup policy.

The performance entry point remains in ``coverart_browser``.  This wrapper
keeps the CoverArt source registered, prevents Rhythmbox's startup source
restore from initializing the browser, and keeps CoverArt's internal album
scan out of Rhythmbox's global loading/task bar.
"""

from coverart_browser import *  # noqa: F401,F403
from coverart_browser_source import CoverArtBrowserSource
from coverart_album import AlbumLoader


_original_source_do_selected = CoverArtBrowserSource.do_selected
_original_load_albums = AlbumLoader.load_albums


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


def _silent_get_status(self, *args):
    """Never expose CoverArt's internal loading progress as a global task."""
    # CoverArt has its own request/search status widgets. The album discovery
    # and cached-art loading progress should not create Rhythmbox's global
    # "Loading..." bar when the source is opened.
    return (self.status, '', 1)


def _startup_guarded_do_selected(self, *args, **kwargs):
    """Ignore a CoverArt source selection restored during Rhythmbox startup."""
    plugin = getattr(self.props, 'plugin', None)

    if plugin is not None and not getattr(plugin, '_startup_complete', False):
        print("CoverArtBrowser DEBUG - startup source selection ignored")
        return None

    print("CoverArtBrowser DEBUG - manual CoverArt selection")
    return _original_source_do_selected(self, *args, **kwargs)


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


# Keep the automatic library scan, but make it background work and completely
# separate from Rhythmbox's global loading indicator.
AlbumLoader.load_albums = _background_load_albums
CoverArtBrowserSource.do_get_status = _silent_get_status
CoverArtBrowserSource.do_selected = _startup_guarded_do_selected
CoverArtBrowserPlugin.load_complete = _disable_startup_autostart
