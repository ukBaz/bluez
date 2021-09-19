# SPDX-License-Identifier: LGPL-2.1-or-later
from collections import deque
from xml.etree import ElementTree as ET

from gi.repository import Gio

SERVICE_NAME = "org.bluez"
ADAPTER_INTERFACE = SERVICE_NAME + ".Adapter1"
DEVICE_INTERFACE = SERVICE_NAME + ".Device1"
OBJ_MNGR_IFACE = "org.freedesktop.DBus.ObjectManager"
INTROSPECT_IACE = "org.freedesktop.DBus.Introspectable"
PROPERTIES_IACE = "org.freedesktop.DBus.Properties"

bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)


class NoBluezAdapterFound(Exception):
    """Custom exception for when no Adapter is found"""


class NoBluezDeviceFound(Exception):
    """Custom exception for when no Device is found"""


def get_proxy(dbus_object: str, interface: str) -> Gio.DBusProxy:
    """
    Returns a proxy for accessing interface_name on the dbus_object
    """
    return Gio.DBusProxy.new_for_bus_sync(
        bus_type=Gio.BusType.SYSTEM,
        flags=Gio.DBusProxyFlags.NONE,
        info=None,
        name=SERVICE_NAME,
        object_path=dbus_object,
        interface_name=interface,
        cancellable=None,
    )


def get_managed_objects() -> dict:
    """
    Return the dictionary from GetManagedObjects for the `org.bluez`
    D-Bus service
    """
    manager = get_proxy("/", OBJ_MNGR_IFACE)
    return manager.GetManagedObjects()


def find_adapter(pattern: str = None) -> Gio.DBusProxy:
    """
    Return D-Bus proxy for adapter with given pattern.
    Pattern can be the end of the D-Bus path object for the adapter (e.g. hci0)
    or the mac address (e.g. 00:11:22:33:44:55).
    If no pattern is given then the first adapter found in the managed objects
    is return.
    If no adapter is found then a `NoBluezAdapterFound` exception is raised.
    """
    try:
        return _find_adapter_in_objects(get_managed_objects(), pattern)
    except NoBluezAdapterFound:
        raise


def _find_adapter_in_objects(objects, pattern=None):
    for path, ifaces in objects.items():
        address = ifaces.get(ADAPTER_INTERFACE, {}).get("Address")
        if pattern is None and address:
            return get_proxy(path, ADAPTER_INTERFACE)
        elif pattern and (
            pattern.upper() == address or path.endswith(pattern.casefold())
        ):
            return get_proxy(path, ADAPTER_INTERFACE)
    raise NoBluezAdapterFound("Bluetooth adapter not found")


def find_device(device_address: str, adapter_pattern: str = None) -> Gio.DBusProxy:
    """
    Return D-Bus proxy for device with given address.
    If adapter_pattern is specified then it will only return if the
    device address is found on adapter that matches the pattern.
    Pattern for adapter can be the end of the D-Bus path object for the
    adapter (e.g. hci0) or the mac address (e.g. 00:11:22:33:44:55).
    The address for the device is the mac address (e.g. 00:11:22:33:44:55).
    If no device is found then a `NoBluezDeviceFound` exception is raised.
    If no adapter is found matching the `adapter_pattern then a
    `NoBluezAdapterFound` exception is raised.
    """
    try:
        return _find_device_in_objects(
            get_managed_objects(), device_address, adapter_pattern
        )
    except NoBluezAdapterFound:
        raise
    except NoBluezDeviceFound:
        raise


def _find_device_in_objects(objects, device_address, adapter_pattern=None):
    path_prefix = ""
    if adapter_pattern:
        try:
            adapter = _find_adapter_in_objects(objects, adapter_pattern)
        except NoBluezAdapterFound:
            raise
        path_prefix = adapter.object_path
    for path, ifaces in objects.items():
        address = ifaces.get(DEVICE_INTERFACE, {}).get("Address")
        if address == device_address.upper() and path.startswith(path_prefix):
            return get_proxy(path, DEVICE_INTERFACE)

    raise NoBluezDeviceFound("Bluetooth device not found")


def _et_to_dict(xml_data):
    _introspect = dict()
    _pointer = deque()
    for node in xml_data.iter():
        if node.tag == "interface":
            _pointer.clear()
            _pointer.append(node.attrib.get("name"))
            _introspect[_pointer[0]] = {"method": [], "property": [], "signal": []}
        elif node.tag in ["method", "signal", "property"]:
            while len(_pointer) > 1:
                _pointer.pop()
            _pointer.append(node.tag)
            _pointer.append(node.attrib.get("name"))
            if node.tag == "property":
                _introspect[_pointer[0]][_pointer[1]].append(node.attrib)
            else:
                _introspect[_pointer[0]][_pointer[1]].append({_pointer[2]: []})
        elif node.tag == "arg":
            _introspect[_pointer[0]][_pointer[1]][-1][_pointer[2]].append(node.attrib)
    return _introspect


def introspect(object_path: str) -> dict:
    """
    Return the introspect information for a D-Bus object path
    in a Python dictionary
    """
    introspectable = get_proxy(object_path, INTROSPECT_IACE)
    ret = introspectable.Introspect()
    xml_object = ET.fromstring(ret)
    path_data = _et_to_dict(xml_object)
    return path_data


if __name__ == "__main__":
    # Examples of how to use some of the functions in this file
    from pprint import pprint

    print("Managed Object Data:")
    pprint(get_managed_objects())
    dongle = find_adapter("hci0")
    print("Adapter found", dongle.get_object_path())
    data = introspect(dongle.get_object_path())
    print("Introspection data for Adapter")
    pprint(data)
    for path, iface in get_managed_objects().items():
        dev_addr = iface.get(DEVICE_INTERFACE, {}).get("Address")
        if dev_addr:
            found_device = find_device(dev_addr)
            print(f"Device found: " f"{found_device.get_object_path()} ({dev_addr})")
