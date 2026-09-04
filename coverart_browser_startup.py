"""CoverArt Browser Rhythmbox startup policy.

CoverArt Browser must not initialize or scan the library merely because the
plugin is loaded or because Rhythmbox restores its last selected page.
The full album scan is still performed when the user explicitly selects
CoverArt Browser.
"""

from coverart_browser import *  # noqa: F401,F403
from coverart_browser_source import CoverArtBrowserSource
import coverart_browser_legacy
from gi.repository import Gtk


class _CoverArtBrowserSourceStartupSafe(CoverArtBrowserSource):
    """Prevent Rhythmbox's programmatic startup page restore from activating CoverArt."""

    def do_selected(self):
        plugin = getattr(self.props, 'plugin', None)

        # Rhythmbox restores the last selected source programmatically, without
        # a GTK input event. A real user selection from the sidebar/keyboard is
        # delivered while GTK is processing an input event. Do not confuse the
        # two: startup restoration must never trigger AlbumLoader.
        if plugin is not None and not getattr(plugin, '_coverart_user_activated', False):
            event = Gtk.get_current_event()
            if event is None:
                print("CoverArtBrowser DEBUG - blocked startup source restore")
                return None

            plugin._coverart_user_activated = True
            print("CoverArtBrowser DEBUG - explicit user activation")

        return super().do_selected()


# CoverArtBrowserPlugin.do_activate() resolves CoverArtBrowserSource from the
# globals of coverart_browser_legacy.py. Replace that reference before the
# plugin instance is activated so the real GObject source subclass is used.
coverart_browser_legacy.CoverArtBrowserSource = _CoverArtBrowserSourceStartupSafe


def _disable_startup_autostart(self, *args, **kwargs):
    """Never select CoverArt automatically after the Rhythmbox library loads."""
    print("CoverArtBrowser DEBUG - automatic CoverArt selection disabled")
    return None


CoverArtBrowserPlugin.load_complete = _disable_startup_autostart
