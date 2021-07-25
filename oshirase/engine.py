import dbus
import dbus.service
import urllib.parse
from dataclasses import dataclass

from gi.repository import Gtk, Gdk, GLib, GdkPixbuf
from gi.repository.GdkPixbuf import Pixbuf

from . import window

style_provider = Gtk.CssProvider()
style_provider.load_from_data(window.css.encode())
Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), style_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

@dataclass
class Notification:
	window: Gtk.Window
	timeout: int
	timeout_id: int

class Oshirase(dbus.service.Object):
	def __init__(self, *args):
		super().__init__(*args)
		self.notif = {}
		self.timeout = {}
		self.timeout_id = {}
		self.id = 0

	@dbus.service.method("org.freedesktop.Notifications", in_signature="", out_signature="ssss", byte_arrays=True)
	def GetServerInformation(self): # -> (name, vendor, version, spec_version)
		return "Oshirase", "Kyuuhachi", "0.1", "1.1"

	@dbus.service.method("org.freedesktop.Notifications", in_signature="", out_signature="as", byte_arrays=True)
	def GetCapabilities(self): # -> (caps)
		return window.capabilities

	@dbus.service.method("org.freedesktop.Notifications", in_signature="u", out_signature="", byte_arrays=True)
	def CloseNotification(self, id): # -> ()
		self.NotificationClosed(id, 3)

	@dbus.service.signal("org.freedesktop.Notifications", signature="uu")
	def NotificationClosed(self, id, reason):
		try:
			if id in self.notif:
				self.notif.pop(id).destroy()
				self.reflow()
			if id in self.timeout:
				del self.timeout[id]
				del self.timeout_id[id]
		except Exception:
			import traceback
			traceback.print_exc()
			raise

	@dbus.service.method("org.freedesktop.Notifications", in_signature="susssasa{sv}i", out_signature="u", byte_arrays=True)
	def Notify(self, app_name, id, icon, summary, body, actions, hints, timeout): # -> (id)
		app_name = undbus(app_name)
		id = undbus(id)
		icon = undbus(icon)
		summary = undbus(summary)
		body = undbus(body)
		actions = undbus(actions)
		hints = undbus(hints)
		timeout = undbus(timeout)

		try:
			if id == 0:
				self.id += 1
				id = self.id

			if timeout == -1:
				timeout = [3500, 5000, 0][hints.get("urgency", 0)]
			if timeout != 0:
				self.timeout[id] = timeout
				self.start_timeout(id)

			data = {}
			if app_name: data["app_name"] = str(app_name)
			if summary:  data["title"] = str(summary)
			if body:     data["body"] = str(body)

			if actions:
				data["actions"] = {}
				for action, name in zip(*[map(str, actions)]*2):
					data["actions"][name] = lambda *a, action=action: self.ActionInvoked(id, action)
			data["close"] = lambda *a: self.NotificationClosed(id, 2)

			hints["icon"] = icon
			if image := get_image(hints):
				image.show()
				data["image"] = image
			for key in ["image-data", "image_data", "icon_data", "icon", "image-path", "image_path"]:
				if key in hints:
					del hints[key]

			data.update(hints)

			if id not in self.notif:
				win = Gtk.Window(type_hint=Gdk.WindowTypeHint.NOTIFICATION, decorated=False, app_paintable=True)
				win.set_visual(Gdk.Screen.get_default().get_rgba_visual())
				win.realize()
				win.get_window().set_override_redirect(True)

				win.connect("enter-notify-event", lambda *a: self.stop_timeout(id))
				win.connect("leave-notify-event", lambda *a: self.start_timeout(id))
				self.notif[id] = win

			win = self.notif[id]
			window.show(win, data)
			win.resize(1,1)
			self.reflow()

			return id
		except Exception:
			import traceback
			traceback.print_exc()
			raise

	@dbus.service.signal("org.freedesktop.Notifications", signature="us")
	def ActionInvoked(self, id, action): pass

	def reflow(self):
		d = Gdk.Display.get_default()
		ys = {}
		for win in self.notif.values():
			mon = d.get_monitor_at_window(win.get_window())
			w = mon.get_geometry().width * mon.get_scale_factor()
			size = win.get_size()
			y = ys.get(mon, 0)
			win.get_window().move_resize(w - size.width, y, size.width, size.height)
			win.show()

			ys[mon] = y + size.height

	def stop_timeout(self, id):
		if id in self.timeout_id:
			GLib.source_remove(self.timeout_id.pop(id))

	def start_timeout(self, id):
		self.stop_timeout(id)
		if id in self.timeout:
			self.timeout_id[id] = GLib.timeout_add(self.timeout[id], lambda *a: self.NotificationClosed(id, 2))

def get_image(hints):
	def from_pixbuf(pixbuf):
		width, height = pixbuf.get_width(), pixbuf.get_height()
		factor = window.IMAGE_SIZE / max(width, height)
		if factor < 1:
			pixbuf = pixbuf.scale_simple(width * factor, height * factor, GdkPixbuf.InterpType.BILINEAR)
		return Gtk.Image.new_from_pixbuf(pixbuf)
	for key in ["image-data", "image_data", "icon_data"]:
		if key in hints:
			(width, height, rowstride, hasalpha, bits, nchan, buf) = hints[key]
			return from_pixbuf(Pixbuf.new_from_bytes(GLib.Bytes(buf), GdkPixbuf.Colorspace.RGB, hasalpha, bits, width, height, rowstride))

	for key in ["icon", "image-path", "image_path"]:
		if key in hints:
			icon = hints[key]
			if icon.startswith("file://"):
				return from_pixbuf(Pixbuf.new_from_file(urllib.parse.unquote(icon[7:])))
			elif icon.startswith("/"):
				return from_pixbuf(Pixbuf.new_from_file(icon))
			elif icon:
				return Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.DIALOG)

def undbus(v):
	if isinstance(v, dbus.Boolean): return bool(v)
	if isinstance(v, int): return int(v)
	if isinstance(v, str): return str(v)
	if isinstance(v, bytes): return bytes(v)
	if isinstance(v, dict): return dict((undbus(k), undbus(v)) for k, v in v.items())
	if isinstance(v, list): return list(undbus(v) for v in v)
	if isinstance(v, tuple): return tuple(undbus(v) for v in v)
	print(type(v))
	return v
