def __main__():
	import dbus
	import dbus.service
	import signal

	import gi
	gi.require_version("Gtk", "3.0")
	from gi.repository import Gtk

	from dbus.mainloop.glib import DBusGMainLoop

	from .engine import Oshirase

	DBusGMainLoop(set_as_default=True)
	session_bus = dbus.SessionBus()
	dbus.service.BusName("org.freedesktop.Notifications", session_bus)
	Oshirase(session_bus, "/org/freedesktop/Notifications")

	signal.signal(signal.SIGINT, lambda s, f: Gtk.main_quit())
	Gtk.main()
