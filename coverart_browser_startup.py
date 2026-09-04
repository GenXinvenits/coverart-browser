"""CoverArt Browser Rhythmbox startup policy.

The performance entry point remains in ``coverart_browser``.  This wrapper
keeps the CoverArt source registered, prevents Rhythmbox's startup source
restore from initializing the browser, and makes the first library scan a
background operation after the CoverArt page has been displayed.
"""

from coverart_browser import *  # noqa: F401,F403
from coverart_browser_source import CoverArtBrowserSource
from coverart_album import AlbumLoader


_original_source_do_selected = CoverArtBrowserSource.do_selected
_original_source_do_get_status = CoverArtBrowserSource.do_get_status
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

    # Give GTK/Rhythmbox a chance to paint the CoverArt page before the
    # library traversal starts.  AlbumLoader itself remains idle/chunk based.
    GLib.timeout_add(100, start_scan)


def _background_status(self, *args):
    """Do not expose the initial album discovery as a Loading screen."""
    if not getattr(self, '_coverart_initial_scan_complete', False):
        return (self.status, '', 1)

    return _original_source_do_get_status(self, *args)


def _mark_initial_scan_complete(source):
    source._coverart_initial_scan_complete = True
    print("CoverArtBrowser DEBUG - initial album scan/model load complete")


def _startup_guarded_do_selected(self, *args, **kwargs):
    """Ignore a CoverArt source selection restored during Rhythmbox startup."""
    plugin = getattr(self.props, 'plugin', None)

    if plugin is not None and not getattr(plugin, '_startup_complete', False):
        print("CoverArtBrowser DEBUG - startup source selection ignored")
        return None

    first_activation = not self.hasActivated
    result = _original_source_do_selected(self, *args, **kwargs)

    if first_activation:
        self._coverart_initial_scan_complete = False
        try:
            self.album_manager.loader.connect(
                'model-load-finished',
                lambda *_args: _mark_initial_scan_complete(self))
        except Exception as error:
            print("CoverArtBrowser DEBUG - scan completion hook failed: %s" % error)

    return result


def _disable_startup_autostart(self, *args, **kwargs):
    """Mark startup complete without automatically selecting CoverArt."""
    self._startup_complete = True
    print("CoverArtBrowser DEBUG - startup complete; autostart disabled")

    # If Rhythmbox restored CoverArt as the previous page before the library
    # completed, move back to Library now.  This prevents the restored page
    # from remaining in a half-initialized state and leaves manual selection
    # available to the user afterwards.
    try:
        if self.shell.props.selected_page == self.source:
            GLib.idle_add(
                self.shell.props.display_page_tree.select,
                self.shell.props.library_source
            )
    except Exception as error:
        print("CoverArtBrowser DEBUG - startup page reset failed: %s" % error)

    return None


AlbumLoader.load_albums = _background_load_albums
CoverArtBrowserSource.do_get_status = _background_status
CoverArtBrowserSource.do_selected = _startup_guarded_do_selected
CoverArtBrowserPlugin.load_complete = _disable_startup_autostart
