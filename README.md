# CoverArt Browser

CoverArt Browser is a Rhythmbox plugin for browsing and playing albums through their cover artwork.

This fork is maintained for **Rhythmbox 3.4.9** and is intended for modern manual, per-user installation.

## Compatibility

- **Rhythmbox 3.4.9**
- Rhythmbox 3.x with the APIs used by this fork may also work, but Rhythmbox 3.4.9 is the target version.
- This fork is **not intended for Rhythmbox 2.x**.

## Companion plugin

CoverArt Browser requires the companion **CoverArt Search Providers** plugin:

https://github.com/GenXinvenits/coverart-search-providers

Install both plugins before activating CoverArt Browser in Rhythmbox.

## Manual installation

No installer script or Makefile is required.

Install the plugin into the Rhythmbox per-user plugin directory:

```bash
rm -rf ~/.local/share/rhythmbox/plugins/coverart-browser
git clone -b v3.4.9 https://github.com/GenXinvenits/coverart-browser.git ~/.local/share/rhythmbox/plugins/coverart-browser
```

Install the companion search-provider plugin in the same way:

```bash
rm -rf ~/.local/share/rhythmbox/plugins/coverart-search-providers
git clone -b v3.4.9 https://github.com/GenXinvenits/coverart-search-providers.git ~/.local/share/rhythmbox/plugins/coverart-search-providers
```

### GSettings schema

CoverArt Browser uses a GSettings schema. Install and compile it once:

```bash
sudo cp ~/.local/share/rhythmbox/plugins/coverart-browser/schema/org.gnome.rhythmbox.plugins.coverart_browser.gschema.xml /usr/share/glib-2.0/schemas/
sudo glib-compile-schemas /usr/share/glib-2.0/schemas/
```

Then restart Rhythmbox and enable **CoverArt Browser** from **Edit → Plugins**.

## Translations

The `po/` directory contains the plugin's translation catalogs. These are part of the plugin's internationalization support and are kept in the repository.

The old translation installation helper scripts have been removed. If you want to install the translations manually, compile the catalogs with `msgfmt`, for example:

```bash
cd ~/.local/share/rhythmbox/plugins/coverart-browser/po
sudo install -d /usr/share/locale/en_US/LC_MESSAGES
sudo msgfmt -c en_US.po -o /usr/share/locale/en_US/LC_MESSAGES/coverart_browser.mo
```

Repeat for any other locale you want to install.

## Features

- Browse albums using their cover artwork.
- Play or queue albums and tracks from the cover browser.
- Tile, list, and cover-flow views.
- Album and artist artwork support.
- Configurable cover size, sorting, display, and flow options.
- Integration with Rhythmbox's library, queue, and playback controls.
- Support for external Rhythmbox plugins such as Alternative Toolbar.
- Translated into multiple languages.

## Development

The `po/` directory contains the translation source files and `update_all_po.sh`, which is retained for translation development. It is not required for normal plugin installation.

## Credits

Original CoverArt Browser authors:

- Agustín Carrasco (asermax)
- fossfreedom

The plugin incorporates work from the original Rhythmbox CoverArt Browser project and other open-source projects. See `LICENSE.txt` and the `coverflow/LICENSE` file for licensing information.

## License

CoverArt Browser is released under the GPLv3+ license. Components included from other projects retain their respective licenses.
