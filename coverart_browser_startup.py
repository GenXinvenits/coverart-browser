"""CoverArt Browser Rhythmbox startup policy.

The performance entry point remains in ``coverart_browser``.  This wrapper
keeps the CoverArt source registered, but prevents Rhythmbox's startup source
restore from initializing the browser before the library has finished loading.

Once the library is fully loaded, normal manual selection of CoverArt Browser
is allowed and the existing library scan can start at that point.
"""

from coverart_browser import *  # noqa: F401,F403
from coverart_browser_source import CoverArtBrowserSource


_original_source_do_selected = CoverArtBrowserSource.do_selected


def _startup_guarded_do_selected(self, *args, **kwargs):
    """Ignore a CoverArt source selection restored during Rhythmbox startup."""
    plugin = getattr(self.props, 'plugin', None)

    if plugin is not None and not getattr(plugin, '_startup_complete', False):
        print("CoverArtBrowser DEBUG - startup source selection ignored")
        return None

    return _original_source_do_selected(self, *args, **kwargs)


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


CoverArtBrowserSource.do_selected = _startup_guarded_do_selected
CoverArtBrowserPlugin.load_complete = _disable_startup_autostart
