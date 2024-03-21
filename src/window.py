"""
window.py

Copyright 2024 Cleo Menezes Jr.

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

SPDX-License-Identifier: GPL-3.0-or-later
"""

import array
import io
import os
import xml.etree.ElementTree as ET

from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk, Soup
from PIL import Image


@Gtk.Template(resource_path="/io/github/cleomenezesjr/aurea/window.ui")
class AureaWindow(Adw.ApplicationWindow):
    __gtype_name__ = "AureaWindow"

    stack: Gtk.Stack = Gtk.Template.Child()
    window_title: Adw.WindowTitle = Gtk.Template.Child()
    main_card: Gtk.Box = Gtk.Template.Child()
    icon: Gtk.Image = Gtk.Template.Child()
    title: Gtk.Label = Gtk.Template.Child()
    description: Gtk.Label = Gtk.Template.Child()
    screenshot: Gtk.Picture = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.style_provider = Gtk.CssProvider()
        self.style_manager = Adw.StyleManager.get_default()

    @Gtk.Template.Callback()
    def open_file_dialog(self, action: Gtk.Button) -> None:
        dialog = Gtk.FileDialog()
        dialog.open(self, None, self.on_file_opened)

    def on_file_opened(
        self, dialog: Gtk.FileDialog, result: Gio.Task
    ) -> None | GLib.GError:
        self.stack.props.visible_child_name = "loading_page"
        try:
            file = dialog.open_finish(result)
        except Exception as error:
            self.stack.props.visible_child_name = "welcome_page"
            return error

        def open_file(file) -> Gio.File:
            return file.load_contents_async(None, self.open_file_complete)

        return open_file(file)

    def open_file_complete(self, file, result: Gio.Task) -> None:
        info: Gio.Task = file.query_info(
            "standard::name",
            Gio.FileQueryInfoFlags.NONE,
            None,
        )

        contents: tuple = file.load_contents_finish(result)
        if not contents[0]:
            self.stack.props.visible_child_name = "welcome_page"
            return None

        path: str = file.peek_path()
        file_name: str = info.get_name()
        self.window_title.set_subtitle(file_name)

        icon_path: str = self.get_icon_file_path(
            metainfo_path=path, metainfo_file_name=file_name
        )
        self.set_icon(icon_path)

        xml_tree: ET = ET.parse(file.get_path())
        self.title.set_label(xml_tree.find("name").text)
        self.description.set_label(xml_tree.find("summary").text)

        self.branding_colors = self.get_branding_colors(xml_tree)
        if self.branding_colors:
            self.set_background_card_color(self.branding_colors)

        screenshot_url = (
            xml_tree.find("screenshots").find("screenshot").find("image").text
        )
        self.set_screenshot_image(screenshot_url)
        self.stack.props.visible_child_name = "content_page"

    def get_icon_file_path(
        self, metainfo_path: str, metainfo_file_name: str
    ) -> str | None:
        metainfo_path: str = os.path.dirname(metainfo_path)
        metainfo_str_index: str = metainfo_file_name.find("metainfo")
        icon_name: str = metainfo_file_name[:metainfo_str_index] + "svg"

        for root, dirs, files in os.walk(metainfo_path):
            if icon_name in files:
                return os.path.join(root, icon_name)

    def set_icon(self, icon_path: str) -> None:
        pixbuf: GdkPixbuf.Pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
            icon_path,
            width=380,
            height=380,
            preserve_aspect_ratio=True,
        )
        self.icon.set_from_pixbuf(pixbuf)

    def set_screenshot_image(self, screenshot_url: str) -> None:
        image_bytes: bytes = self.fetch_screenshot_image_bytes(screenshot_url)
        image: Image.Image = self.crop_screenshot_bottom(image_bytes)

        image_array = array.array("B", image.tobytes())
        width, height = image.size
        texture = GdkPixbuf.Pixbuf.new_from_data(
            image_array,
            GdkPixbuf.Colorspace.RGB,
            True,
            8,
            width,
            height,
            width * 4,
        )

        self.screenshot.set_pixbuf(texture)

    def fetch_screenshot_image_bytes(self, url: str) -> bytes | str:
        session = Soup.Session()
        message = Soup.Message(
            method="GET", uri=GLib.Uri.parse(url, GLib.UriFlags.NONE)
        )

        bytes: GLib.Bytes = session.send_and_read(message)
        if message.props.status_code != 200:
            return (
                f"{message.props.status_code} - {message.props.reason_phrase}"
            )

        return bytes.get_data()

    def crop_screenshot_bottom(self, image_bytes: bytes) -> Image.Image:
        image = Image.open(io.BytesIO(image_bytes))
        width, height = image.size
        image = image.crop((0, 0, width, int(height * 0.8)))

        return image

    def set_background_card_color(self, colors: dict) -> str:
        color: str = colors[self.which_color_scheme()]
        self.style_provider.load_from_string(
            f".main-card {{ background-color: {color};}}"
        )

        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            self.style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def get_branding_colors(self, xml_tree: ET) -> dict | str:
        branding = xml_tree.find("./branding")
        if branding is None:
            return "No branding colors"

        light_color = branding.find('./color[@scheme_preference="light"]').text
        dark_color = branding.find('./color[@scheme_preference="dark"]').text

        return {"light": light_color, "dark": dark_color}

    def which_color_scheme(self) -> str:
        is_color_scheme_dark: bool = Adw.StyleManager.get_default().get_dark()
        if is_color_scheme_dark:
            return "dark"

        return "light"

    @Gtk.Template.Callback()
    def cycle_color_scheme(self, widget) -> None:
        self.style_manager.props.color_scheme = (
            Adw.ColorScheme.FORCE_LIGHT
            if self.which_color_scheme() == "dark"
            else Adw.ColorScheme.FORCE_DARK
        )

        if self.branding_colors:
            self.set_background_card_color(self.branding_colors)
