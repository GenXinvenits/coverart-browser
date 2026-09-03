import os
# -*- Mode: python; coding: utf-8; tab-width: 4; indent-tabs-mode: nil; -*-
#
# Copyright (C) 2012 - fossfreedom
# Copyright (C) 2012 - Agustin Carrasco
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301  USA.

# define plugin
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import RB
from gi.repository import Peas
from gi.repository import Gio
from gi.repository import GLib

import rb

# CoverArt Browser compatibility helper for user-installed plugin data.
# The original plugin expects the old rb.find_plugin_file() installation
# layout, which does not resolve this hyphenated user plugin directory.
def _coverart_find_plugin_file(plugin, filename):
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        filename
    )
    if os.path.exists(path):
        return path
    return None


rb.find_plugin_file = _coverart_find_plugin_file

from coverart_browser_prefs import GSetting
from coverart_browser_prefs import CoverLocale
from coverart_browser_prefs import Preferences
from coverart_browser_source import CoverArtBrowserSource
from coverart_listview import ListView
from coverart_queueview import QueueView
from coverart_toolbar import TopToolbar


class CoverArtBrowserEntryType(RB.RhythmDBEntryType):
    '''
    Entry type for our source.
    '''

    def __init__(self):
        '''
        Initializes the entry type.
        '''
        RB.RhythmDBEntryType.__init__(
            self,
            name='CoverArtBrowserEntryType'
        )


class CoverArtBrowserPlugin(GObject.Object, Peas.Activatable):
    '''
    Main class of the plugin. Manages the activation and deactivation of the
    plugin.
    '''

    __gtype_name = 'CoverArtBrowserPlugin'
    object = GObject.property(type=GObject.Object)

    def __init__(self):
        '''
        Initialises the plugin object.
        '''
        GObject.Object.__init__(self)

        self._coverart_icon_theme = None
        self._coverart_icon_file = None
        self._coverart_settings = None
        self._coverart_theme_signal = None

    def _update_coverart_icon(self):
        '''
        Render the symbolic CoverArt icon using the current GTK theme.
        '''

        icon_theme_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'icons'
        )

        # Use the application's existing icon theme, but only temporarily
        # add the CoverArt icon directory so other plugins are unaffected.
        original_search_path = self._coverart_icon_theme.get_search_path()

        self._coverart_icon_theme.prepend_search_path(
            icon_theme_path
        )

        try:
            icon_info = self._coverart_icon_theme.lookup_icon(
                'coverart-browser-symbolic',
                16,
                0
            )

            if icon_info is None:
                print(
                    "CoverArt Browser: symbolic icon not found"
                )
                return False

            # Get the current GTK foreground color.
            window = Gtk.Window()
            context = window.get_style_context()

            foreground = context.get_color(
                Gtk.StateFlags.NORMAL
            )

            window.destroy()

            # Render the symbolic SVG using the current foreground color.
            pixbuf, was_symbolic = icon_info.load_symbolic(
                foreground
            )

            cache_dir = os.path.dirname(
                self._coverart_icon_file
            )

            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir)

            pixbuf.savev(
                self._coverart_icon_file,
                'png',
                [],
                []
            )

            return True

        except Exception as error:
            print(
                "CoverArt Browser: unable to render symbolic icon: %s"
                % error
            )
            return False

        finally:
            # IMPORTANT:
            # Restore the original GTK icon search path so CoverArt's
            # private icon directory does not affect other plugins.
            self._coverart_icon_theme.set_search_path(
                original_search_path
            )

    def _coverart_theme_changed(self, settings, param):
        '''
        Update the CoverArt icon when the GTK theme changes.
        '''

        if self._update_coverart_icon():
            if hasattr(self, 'source') and self.source is not None:
                self.source.props.icon = Gio.FileIcon.new(
                    Gio.File.new_for_path(
                        self._coverart_icon_file
                    )
                )

    def do_activate(self):
        '''
        Called by Rhythmbox when the plugin is activated. It creates the
        plugin's source and connects signals to manage the plugin's
        preferences.
        '''

        print("CoverArtBrowser DEBUG - do_activate")

        self.shell = self.object
        self.db = self.shell.props.db

        self.entry_type = CoverArtBrowserEntryType()
        self.db.register_entry_type(self.entry_type)

        cl = CoverLocale()
        cl.switch_locale(cl.Locale.LOCALE_DOMAIN)

        self.entry_type.category = RB.RhythmDBEntryCategory.NORMAL

        group = RB.DisplayPageGroup.get_by_id('library')

        # ------------------------------------------------------------------
        # CoverArt Browser symbolic icon
        # ------------------------------------------------------------------

        self._coverart_icon_theme = Gtk.IconTheme.get_default()

        self._coverart_icon_file = os.path.join(
            GLib.get_user_cache_dir(),
            'rhythmbox-coverart-browser-icon.png'
        )

        # Generate the initial icon using the current GTK theme.
        self._update_coverart_icon()

        # Watch for Light/Dark GTK theme changes.
        self._coverart_settings = Gtk.Settings.get_default()

        self._coverart_theme_signal = (
            self._coverart_settings.connect(
                'notify::gtk-theme-name',
                self._coverart_theme_changed
            )
        )

        # ------------------------------------------------------------------
        # CoverArt Browser source
        # ------------------------------------------------------------------

        self.source = CoverArtBrowserSource(
            shell=self.shell,
            name=_("CoverArt"),
            entry_type=self.entry_type,
            plugin=self,
            icon=Gio.FileIcon.new(
                Gio.File.new_for_path(
                    self._coverart_icon_file
                )
            ),
            query_model=self.shell.props.library_source.props.base_query_model
        )

        self.shell.register_entry_type_for_source(
            self.source,
            self.entry_type
        )

        self.shell.append_display_page(
            self.source,
            group
        )

        self.source.props.query_model.connect(
            'complete',
            self.load_complete
        )

        self._externalmenu = ExternalPluginMenu(self)

        cl.switch_locale(cl.Locale.RB)

        print("CoverArtBrowser DEBUG - end do_activate")

    def do_deactivate(self):
        '''
        Called by Rhythmbox when the plugin is deactivated. It makes sure to
        free all the resources used by the plugin.
        '''

        print("CoverArtBrowser DEBUG - do_deactivate")

        # Disconnect the GTK theme-change signal.
        if (
            self._coverart_settings is not None
            and self._coverart_theme_signal is not None
        ):
            try:
                self._coverart_settings.disconnect(
                    self._coverart_theme_signal
                )
            except Exception:
                pass

        self._coverart_theme_signal = None
        self._coverart_settings = None

        self.source.delete_thyself()

        if self._externalmenu:
            self._externalmenu.cleanup()

        del self.shell
        del self.db
        del self.source

        print("CoverArtBrowser DEBUG - end do_deactivate")

    def load_complete(self, *args, **kwargs):
        '''
        Called when Rhythmbox has completed loading all data.
        Used to automatically switch to the browser if the user
        has set this in the preferences.
        '''

        gs = GSetting()
        setting = gs.get_setting(gs.Path.PLUGIN)

        if setting[gs.PluginKey.AUTOSTART]:
            GLib.idle_add(
                self.shell.props.display_page_tree.select,
                self.source
            )

    def _translation_helper(self):
        '''
        A method just to help out with translation strings.
        It is not meant to be called by itself.
        '''

        # Define .plugin text strings used for translation.
        plugin = _('CoverArt Browser')
        desc = _('Browse and play your albums through their covers')

        # TRANSLATORS: This is the icon-grid view that the user sees.
        tile = _('Tiles')

        # TRANSLATORS: This is the cover-flow view the user sees.
        artist = _('Flow')

        # TRANSLATORS: Percentage size that the image will be expanded.
        scale = _('Scale by %:')

        # Stop PyCharm removing the Preference import on optimisation.
        pref = Preferences()


class ExternalPluginMenu(GObject.Object):
    toolbar_pos = GObject.property(
        type=str,
        default=TopToolbar.name
    )

    def __init__(self, plugin):
        super(ExternalPluginMenu, self).__init__()

        self.plugin = plugin
        self.shell = plugin.shell
        self.source = plugin.source
        self.app_id = None

        from coverart_browser_source import Views

        self._views = Views(self.shell)

        self._connect_properties()
        self._connect_signals()

        self._create_menu()

    def _connect_signals(self):
        self.connect(
            'notify::toolbar-pos',
            self._on_notify_toolbar_pos
        )

        self.shell.props.display_page_tree.connect(
            "selected",
            self.on_page_change
        )

    def _connect_properties(self):
        gs = GSetting()
        setting = gs.get_setting(gs.Path.PLUGIN)

        setting.bind(
            gs.PluginKey.TOOLBAR_POS,
            self,
            'toolbar_pos',
            Gio.SettingsBindFlags.GET
        )

    def _on_notify_toolbar_pos(self, *args):
        if self.toolbar_pos == TopToolbar.name:
            self._create_menu()
        else:
            self.cleanup()

    def cleanup(self):
        if self.app_id:
            app = Gio.Application.get_default()

            for location in self.locations:
                app.remove_plugin_menu_item(
                    location,
                    self.app_id
                )

            self.app_id = None

    def _create_menu(self):
        app = Gio.Application.get_default()

        self.app_id = 'coverart-browser'

        self.locations = [
            'library-toolbar',
            'queue-toolbar',
            'playsource-toolbar'
        ]

        action_name = 'coverart-browser-views'

        self.action = Gio.SimpleAction.new_stateful(
            action_name,
            GLib.VariantType.new('s'),
            self._views.get_action_name(ListView.name)
        )

        self.action.connect(
            "activate",
            self.view_change_cb
        )

        app.add_action(self.action)

        menu_item = Gio.MenuItem()
        section = Gio.Menu()
        menu = Gio.Menu()
        toolbar_item = Gio.MenuItem()

        for view_name in self._views.get_view_names():
            menu_item.set_label(
                self._views.get_menu_name(view_name)
            )

            menu_item.set_action_and_target_value(
                'app.' + action_name,
                self._views.get_action_name(view_name)
            )

            section.append_item(menu_item)

        menu.append_section(
            None,
            section
        )

        cl = CoverLocale()
        cl.switch_locale(cl.Locale.LOCALE_DOMAIN)

        toolbar_item.set_label('…')

        cl.switch_locale(cl.Locale.RB)

        toolbar_item.set_submenu(menu)

        for location in self.locations:
            app.add_plugin_menu_item(
                location,
                self.app_id,
                toolbar_item
            )

    def on_page_change(self, display_page_tree, page):
        '''
        Called when the display page changes. Grabs query models and sets the
        active view.
        '''

        if page == self.shell.props.library_source:
            self.action.set_state(
                self._views.get_action_name(ListView.name)
            )

        elif page == self.shell.props.queue_source:
            self.action.set_state(
                self._views.get_action_name(QueueView.name)
            )

            # elif page == self.source.playlist_source:
            #     self._views.get_action_name(PlaySourceView.name)

    def view_change_cb(self, action, current):
        '''
        Called when the view state on a page is changed.
        '''

        action.set_state(current)

        view_name = self._views.get_view_name_for_action(
            current
        )

        if view_name != ListView.name and \
                view_name != QueueView.name:

            # view_name != PlaySourceView.name:
            gs = GSetting()
            setting = gs.get_setting(gs.Path.PLUGIN)

            setting[gs.PluginKey.VIEW_NAME] = view_name

            player = self.shell.props.shell_player
            player.set_selected_source(
                self.source.playlist_source
            )

            GLib.idle_add(
                self.shell.props.display_page_tree.select,
                self.source
            )

        elif view_name == ListView.name:
            GLib.idle_add(
                self.shell.props.display_page_tree.select,
                self.shell.props.library_source
            )

        elif view_name == QueueView.name:
            GLib.idle_add(
                self.shell.props.display_page_tree.select,
                self.shell.props.queue_source
            )

