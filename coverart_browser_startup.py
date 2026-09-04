"""CoverArt Browser Rhythmbox startup policy.

CoverArt Browser must initialize its UI when Rhythmbox restores the last
selected page, but that restore should not automatically trigger the expensive
library album scan. The scan is deferred until the user explicitly selects
CoverArt Browser again.

The plugin's original AUTOSTART preference remains fully functional: when it
is enabled, the plugin's own programmatic selection is treated as intentional
and the normal album load is allowed.
"""

from coverart_browser import *  # noqa: F401,F403
from coverart_browser_source import CoverArtBrowserSource
from coverart_album import AlbumLoader
from coverart_browser_prefs import GSetting
import coverart_browser_legacy
from gi.repository import Gtk


class _CoverArtBrowserSourceStartupSafe(CoverArtBrowserSource):
    """Keep startup page restore lightweight without producing a blank page."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._coverart_defer_album_load = False

    def _startup_restore_should_defer(self):
        plugin = getattr(self.props, 'plugin', None)
        if plugin is None:
            return False

        # The v3.4.9 AUTOSTART preference deliberately selects CoverArt when
        # Rhythmbox finishes loading. Preserve that original behavior.
        try:
            setting = GSetting().get_setting(GSetting.Path.PLUGIN)
            if setting[GSetting.PluginKey.AUTOSTART]:
                return False
        except Exception:
            pass

        # Rhythmbox's restoration of the last selected page is programmatic and
        # has no current GTK input event. A real user selection does.
        return Gtk.get_current_event() is None

    def do_selected(self):
        print("CoverArtBrowser DEBUG - do_selected")

        # If the source was initialized during startup restore, its UI already
        # exists. The first subsequent explicit selection is the point at which
        # we start the deferred album load.
        if self.hasActivated and self._coverart_defer_album_load:
            print("CoverArtBrowser DEBUG - starting deferred album load")
            self._coverart_defer_album_load = False
            self.album_manager.loader.load_albums(self.props.base_query_model)

        if not self.hasActivated:
            if self._startup_restore_should_defer():
                self._coverart_defer_album_load = True
                print("CoverArtBrowser DEBUG - deferring startup album scan")

            # Always run normal source activation. This creates the CoverArt UI
            # and prevents the blank-page regression caused by blocking
            # do_selected() entirely.
            self.do_impl_activate()
            self.hasActivated = True

        print("CoverArtBrowser DEBUG - end do_selected")

    def do_impl_activate(self):
        # _setup_source() calls AlbumLoader.load_albums() synchronously. For a
        # deferred startup restore, temporarily replace only that class method
        # while normal UI initialization runs. The original method is restored
        # immediately after activation, so normal/manual loads are untouched.
        if not self._coverart_defer_album_load:
            return super().do_impl_activate()

        original_load_albums = AlbumLoader.load_albums

        def deferred_load_albums(loader, query_model):
            print("CoverArtBrowser DEBUG - startup album scan deferred")

        AlbumLoader.load_albums = deferred_load_albums
        try:
            super().do_impl_activate()
        finally:
            AlbumLoader.load_albums = original_load_albums


# CoverArtBrowserPlugin.do_activate() resolves CoverArtBrowserSource from the
# globals of coverart_browser_legacy.py. Replace that reference before the
# plugin instance is activated so the startup-safe subclass is instantiated.
coverart_browser_legacy.CoverArtBrowserSource = _CoverArtBrowserSourceStartupSafe
