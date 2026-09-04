"""CoverArt Browser Rhythmbox startup policy.

The performance entry point remains in ``coverart_browser``.  This thin
wrapper disables the legacy AUTOSTART callback so merely activating the plugin
never selects the CoverArt source and starts the library album-art scan.

The scan still occurs when the user explicitly selects CoverArt Browser.
"""

from coverart_browser import *  # noqa: F401,F403


def _disable_startup_autostart(self, *args, **kwargs):
    """Do not auto-select CoverArt Browser after the Rhythmbox library loads."""
    print("CoverArtBrowser DEBUG - startup autostart disabled")
    return None


CoverArtBrowserPlugin.load_complete = _disable_startup_autostart
