"""A system tray icon for KDE (and any StatusNotifier host), written directly on D-Bus so it needs no extra libraries.

Implements org.kde.StatusNotifierItem plus a small com.canonical.dbusmenu menu (Show / New session / Quit).
"""
import os

from gi.repository import Gio, GLib

ITEM_XML = """<node><interface name="org.kde.StatusNotifierItem">
<property name="Category" type="s" access="read"/><property name="Id" type="s" access="read"/>
<property name="Title" type="s" access="read"/><property name="Status" type="s" access="read"/>
<property name="WindowId" type="u" access="read"/><property name="IconThemePath" type="s" access="read"/>
<property name="IconName" type="s" access="read"/><property name="IconPixmap" type="a(iiay)" access="read"/>
<property name="OverlayIconName" type="s" access="read"/><property name="AttentionIconName" type="s" access="read"/>
<property name="AttentionIconPixmap" type="a(iiay)" access="read"/><property name="AttentionMovieName" type="s" access="read"/>
<property name="ToolTip" type="(sa(iiay)ss)" access="read"/><property name="ItemIsMenu" type="b" access="read"/>
<property name="Menu" type="o" access="read"/>
<method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
<signal name="NewTitle"/><signal name="NewIcon"/><signal name="NewAttentionIcon"/><signal name="NewOverlayIcon"/>
<signal name="NewToolTip"/><signal name="NewStatus"><arg type="s"/></signal>
</interface></node>"""

MENU_XML = """<node><interface name="com.canonical.dbusmenu">
<property name="Version" type="u" access="read"/><property name="TextDirection" type="s" access="read"/>
<property name="Status" type="s" access="read"/><property name="IconThemePath" type="as" access="read"/>
<method name="GetLayout"><arg type="i" direction="in"/><arg type="i" direction="in"/><arg type="as" direction="in"/>
<arg type="u" direction="out"/><arg type="(ia{sv}av)" direction="out"/></method>
<method name="GetGroupProperties"><arg type="ai" direction="in"/><arg type="as" direction="in"/><arg type="a(ia{sv})" direction="out"/></method>
<method name="GetProperty"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/></method>
<method name="Event"><arg type="i" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="in"/><arg type="u" direction="in"/></method>
<method name="EventGroup"><arg type="a(isvu)" direction="in"/><arg type="ai" direction="out"/></method>
<method name="AboutToShow"><arg type="i" direction="in"/><arg type="b" direction="out"/></method>
<method name="AboutToShowGroup"><arg type="ai" direction="in"/><arg type="ai" direction="out"/><arg type="ai" direction="out"/></method>
<signal name="ItemsPropertiesUpdated"><arg type="a(ia{sv})"/><arg type="a(ias)"/></signal>
<signal name="LayoutUpdated"><arg type="u"/><arg type="i"/></signal>
<signal name="ItemActivationRequested"><arg type="i"/><arg type="u"/></signal>
</interface></node>"""

ITEM_PATH, MENU_PATH = "/StatusNotifierItem", "/MenuBar"


class Tray:
    """on_show / on_new / on_quit are called on the GLib main loop."""

    def __init__(self, app_id, title, icon_name, icon_dir, on_show, on_new, on_quit):
        self.app_id, self.title, self.icon, self.icon_dir = app_id, title, icon_name, icon_dir
        self.on_show, self.on_new, self.on_quit = on_show, on_new, on_quit
        self.status, self.tip = "Active", title
        self.registered = False
        self.conn = None
        self.items = [(1, "Show " + title), (2, "New session"), (3, None), (4, "Quit")]
        self._item_info = Gio.DBusNodeInfo.new_for_xml(ITEM_XML).interfaces[0]
        self._menu_info = Gio.DBusNodeInfo.new_for_xml(MENU_XML).interfaces[0]
        self.name = "org.kde.StatusNotifierItem-%d-1" % os.getpid()
        self._owner = Gio.bus_own_name(Gio.BusType.SESSION, self.name, Gio.BusNameOwnerFlags.NONE, self._on_bus, None, None)

    # ---- bus plumbing ----
    def _on_bus(self, conn, _name):
        self.conn = conn
        conn.register_object(ITEM_PATH, self._item_info, self._item_call, self._item_get, None)
        conn.register_object(MENU_PATH, self._menu_info, self._menu_call, self._menu_get, None)
        conn.call("org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher", "org.kde.StatusNotifierWatcher",
                  "RegisterStatusNotifierItem", GLib.Variant("(s)", (self.name,)), None, Gio.DBusCallFlags.NONE, 3000, None,
                  self._registered)

    def _registered(self, conn, res):
        try:
            conn.call_finish(res)
            self.registered = True
        except GLib.Error:
            self.registered = False  # no tray host (e.g. a bare compositor): the app simply runs without one

    def _emit(self, name, params=None):
        if self.conn:
            self.conn.emit_signal(None, ITEM_PATH, "org.kde.StatusNotifierItem", name, params)

    # ---- state ----
    def set_attention(self, on, tip=None):
        status = "NeedsAttention" if on else "Active"
        if tip is not None and tip != self.tip:
            self.tip = tip
            self._emit("NewToolTip")
        if status != self.status:
            self.status = status
            self._emit("NewStatus", GLib.Variant("(s)", (status,)))

    def close(self):
        """Gives up the bus name, which makes the tray host drop the icon."""
        Gio.bus_unown_name(self._owner)
        self.registered = False
        self.conn = None

    # ---- org.kde.StatusNotifierItem ----
    def _item_get(self, _c, _s, _p, _i, prop):
        v = GLib.Variant
        return {
            "Category": v("s", "ApplicationStatus"), "Id": v("s", self.app_id), "Title": v("s", self.title),
            "Status": v("s", self.status), "WindowId": v("u", 0), "IconThemePath": v("s", self.icon_dir),
            "IconName": v("s", self.icon), "IconPixmap": v("a(iiay)", []), "OverlayIconName": v("s", ""),
            "AttentionIconName": v("s", self.icon), "AttentionIconPixmap": v("a(iiay)", []), "AttentionMovieName": v("s", ""),
            "ToolTip": v("(sa(iiay)ss)", (self.icon, [], self.title, self.tip)), "ItemIsMenu": v("b", False),
            "Menu": v("o", MENU_PATH),
        }.get(prop)

    def _item_call(self, _c, _s, _p, _i, method, _params, inv):
        if method in ("Activate", "SecondaryActivate"):
            GLib.idle_add(lambda: self.on_show() and False)
        inv.return_value(None)

    # ---- com.canonical.dbusmenu ----
    def _props(self, ident):
        v = GLib.Variant
        if ident == 0:
            return {"children-display": v("s", "submenu")}
        label = dict(self.items).get(ident)
        if label is None:
            return {"type": v("s", "separator")}
        return {"label": v("s", label), "enabled": v("b", True), "visible": v("b", True)}

    def _menu_get(self, _c, _s, _p, _i, prop):
        return {"Version": GLib.Variant("u", 3), "TextDirection": GLib.Variant("s", "ltr"),
                "Status": GLib.Variant("s", "normal"), "IconThemePath": GLib.Variant("as", [])}.get(prop)

    def _menu_call(self, _c, _s, _p, _i, method, params, inv):
        v = GLib.Variant
        if method == "GetLayout":
            kids = [v("(ia{sv}av)", (i, self._props(i), [])) for i, _ in self.items]
            inv.return_value(v("(u(ia{sv}av))", (1, (0, self._props(0), kids))))
        elif method == "GetGroupProperties":
            ids = params.unpack()[0] or [0] + [i for i, _ in self.items]
            inv.return_value(v("(a(ia{sv}))", ([(i, self._props(i)) for i in ids],)))
        elif method == "GetProperty":
            ident, name = params.unpack()
            inv.return_value(v("(v)", (self._props(ident).get(name, v("s", "")),)))
        elif method == "Event":
            ident, event, _data, _ts = params.unpack()
            inv.return_value(None)
            if event == "clicked":
                self._clicked(ident)
        elif method == "EventGroup":
            for ident, event, _d, _t in params.unpack()[0]:
                if event == "clicked":
                    self._clicked(ident)
            inv.return_value(v("(ai)", ([],)))
        elif method == "AboutToShow":
            inv.return_value(v("(b)", (False,)))
        elif method == "AboutToShowGroup":
            inv.return_value(v("(aiai)", ([], [])))
        else:
            inv.return_value(None)

    def _clicked(self, ident):
        fn = {1: self.on_show, 2: self.on_new, 4: self.on_quit}.get(ident)
        if fn:
            GLib.idle_add(lambda: fn() and False)
