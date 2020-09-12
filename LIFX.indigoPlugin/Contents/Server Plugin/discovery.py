#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# LIFX V6 Controller - Send & Receive Messages © Autolog 2020
#

# TODO: TBA
# -
# -


# noinspection PyUnresolvedReferences
# ============================== Native Imports ===============================
import colorsys
import logging
import Queue
import sys
import threading

# ============================== Custom Imports ===============================
try:
    import indigo
except ImportError:
    pass

# ============================== Plugin Imports ===============================
from constants import *
from lifxlan.lifxlan import *


# ============================== Static Methods ===============================
def calculate_brightness_level_from_sv(arg_saturation, arg_brightness):
    # arguments Saturation and Brightness are (float) values 0.0 to 100.0
    saturation = arg_saturation
    if saturation == 0.0:
        saturation = 1.0
    brightness_level = (arg_brightness / 2.0) + ((100 - saturation) / 2)

    return float(brightness_level)


def set_hsbk(hue, saturation, brightness, kelvin):
    # This method ensures that the HSBK values being passed to lifxlan are valid
    hue = hue if hue > 0 else 0
    hue = hue if hue <= 65535 else 65535
    saturation = saturation if saturation > 0 else 0
    saturation = saturation if saturation <= 65535 else 65535
    brightness = brightness if brightness > 0 else 0
    brightness = brightness if brightness <= 65535 else 65535
    kelvin = kelvin if kelvin > 2500 else 2500
    kelvin = kelvin if kelvin <= 9000 else 9000

    return hue, saturation, brightness, kelvin


def store_discovered_lifx_device(globals_discovery, lifx_device):

    lifx_mac_address = None
    try:
        lifx_mac_address = lifx_device.mac_addr
        lifx_ip_address = lifx_device.ip_addr
        lifx_port = lifx_device.port
        lifx_label = str(lifx_device.label).rstrip()
        lifx_group = lifx_device.group
        lifx_power_level = lifx_device.power_level
        lifx_host_firmware_build_timestamp = lifx_device.host_firmware_build_timestamp
        lifx_host_firmware_version = lifx_device.host_firmware_version
        lifx_wifi_firmware_build_timestamp = lifx_device.wifi_firmware_build_timestamp
        lifx_wifi_firmware_version = lifx_device.wifi_firmware_version
        lifx_vendor = lifx_device.vendor
        lifx_product = lifx_device.product
        lifx_version = lifx_device.version
        lifx_product_name = lifx_device.product_name
        lifx_product_features = lifx_device.product_features
        if lifx_host_firmware_version == lifx_wifi_firmware_version:
            lifx_firmware_ui = lifx_host_firmware_version
        else:
            lifx_firmware_ui = u"{0}|{1}".format(lifx_host_firmware_version, lifx_wifi_firmware_version)

        if lifx_mac_address not in globals_discovery:
            globals_discovery[lifx_mac_address] = dict()
            globals_discovery[lifx_mac_address][K_LABEL] = lifx_label
            globals_discovery[lifx_mac_address][K_IP_ADDRESS] = lifx_ip_address
            globals_discovery[lifx_mac_address][K_PORT] = lifx_port
            globals_discovery[lifx_mac_address][K_GROUP] = lifx_group
            globals_discovery[lifx_mac_address][K_POWER_LEVEL] = lifx_power_level
            globals_discovery[lifx_mac_address][K_HOST_FIRMWARE_BUILD_TIMESTAMP] = lifx_host_firmware_build_timestamp
            globals_discovery[lifx_mac_address][K_HOST_FIRMWARE_VERSION] = lifx_host_firmware_version
            globals_discovery[lifx_mac_address][K_WIFI_FIRMWARE_BUILD_TIMESTAMP] = lifx_wifi_firmware_build_timestamp
            globals_discovery[lifx_mac_address][K_WIFI_FIRMWARE_VERSION] = lifx_wifi_firmware_version
            globals_discovery[lifx_mac_address][K_FIRMWARE_UI] = lifx_firmware_ui
            globals_discovery[lifx_mac_address][K_VENDOR] = lifx_vendor
            globals_discovery[lifx_mac_address][K_PRODUCT] = lifx_product
            globals_discovery[lifx_mac_address][K_VERSION] = lifx_version
            globals_discovery[lifx_mac_address][K_PRODUCT_NAME] = lifx_product_name
            globals_discovery[lifx_mac_address][K_PRODUCT_FEATURES] = lifx_product_features
            globals_discovery[lifx_mac_address][K_CHANGED_INFO] = False

        if globals_discovery[lifx_mac_address][K_LABEL] != lifx_label:
            globals_discovery[lifx_mac_address][K_LABEL] = lifx_label
            globals_discovery[lifx_mac_address][K_CHANGED_INFO] = True
        if globals_discovery[lifx_mac_address][K_IP_ADDRESS] != lifx_ip_address:
            globals_discovery[lifx_mac_address][K_IP_ADDRESS] = lifx_ip_address
            globals_discovery[lifx_mac_address][K_CHANGED_INFO] = True
        if globals_discovery[lifx_mac_address][K_PORT] != lifx_port:
            globals_discovery[lifx_mac_address][K_PORT] = lifx_port
            globals_discovery[lifx_mac_address][K_CHANGED_INFO] = True
        if globals_discovery[lifx_mac_address][K_GROUP] != lifx_group:
            globals_discovery[lifx_mac_address][K_GROUP] = lifx_group
            globals_discovery[lifx_mac_address][K_CHANGED_INFO] = True
        if globals_discovery[lifx_mac_address][K_POWER_LEVEL] != lifx_power_level:
            globals_discovery[lifx_mac_address][K_POWER_LEVEL] = lifx_power_level
            globals_discovery[lifx_mac_address][K_CHANGED_INFO] = True
        if globals_discovery[lifx_mac_address][K_HOST_FIRMWARE_BUILD_TIMESTAMP] != lifx_host_firmware_build_timestamp:
            globals_discovery[lifx_mac_address][K_HOST_FIRMWARE_BUILD_TIMESTAMP] = lifx_host_firmware_build_timestamp
            globals_discovery[lifx_mac_address][K_CHANGED_INFO] = True
        if globals_discovery[lifx_mac_address][K_HOST_FIRMWARE_VERSION] != lifx_host_firmware_version:
            globals_discovery[lifx_mac_address][K_HOST_FIRMWARE_VERSION] = lifx_host_firmware_version
            globals_discovery[lifx_mac_address][K_CHANGED_INFO] = True
        if globals_discovery[lifx_mac_address][K_WIFI_FIRMWARE_BUILD_TIMESTAMP] != lifx_wifi_firmware_build_timestamp:
            globals_discovery[lifx_mac_address][K_WIFI_FIRMWARE_BUILD_TIMESTAMP] = lifx_wifi_firmware_build_timestamp
            globals_discovery[lifx_mac_address][K_CHANGED_INFO] = True
        if globals_discovery[lifx_mac_address][K_WIFI_FIRMWARE_VERSION] != lifx_wifi_firmware_version:
            globals_discovery[lifx_mac_address][K_WIFI_FIRMWARE_VERSION] = lifx_wifi_firmware_version
            globals_discovery[lifx_mac_address][K_CHANGED_INFO] = True
        if globals_discovery[lifx_mac_address][K_FIRMWARE_UI] != lifx_firmware_ui:
            globals_discovery[lifx_mac_address][K_FIRMWARE_UI] = lifx_firmware_ui
            globals_discovery[lifx_mac_address][K_CHANGED_INFO] = True
        if globals_discovery[lifx_mac_address][K_VENDOR] != lifx_vendor:
            globals_discovery[lifx_mac_address][K_VENDOR] = lifx_vendor
            globals_discovery[lifx_mac_address][K_CHANGED_INFO] = True
        if globals_discovery[lifx_mac_address][K_PRODUCT] != lifx_product:
            globals_discovery[lifx_mac_address][K_PRODUCT] = lifx_product
            globals_discovery[lifx_mac_address][K_CHANGED_INFO] = True
        if globals_discovery[lifx_mac_address][K_VERSION] != lifx_version:
            globals_discovery[lifx_mac_address][K_VERSION] = lifx_version
            globals_discovery[lifx_mac_address][K_CHANGED_INFO] = True
        if globals_discovery[lifx_mac_address][K_PRODUCT_NAME] != lifx_product_name:
            globals_discovery[lifx_mac_address][K_PRODUCT_NAME] = lifx_product_name
            globals_discovery[lifx_mac_address][K_CHANGED_INFO] = True
        if globals_discovery[lifx_mac_address][K_PRODUCT_FEATURES] != lifx_product_features:
            globals_discovery[lifx_mac_address][K_PRODUCT_FEATURES] = lifx_product_features
            globals_discovery[lifx_mac_address][K_CHANGED_INFO] = True

        if K_INDIGO_DEVICE_ID not in globals_discovery[lifx_mac_address]:
            globals_discovery[lifx_mac_address][K_INDIGO_DEVICE_ID] = 0  # Default to no Indigo device

        return True, None

    except StandardError as standard_error_message:
        error_details = (sys.exc_traceback.tb_lineno, standard_error_message)
        if lifx_mac_address is not None:
            del globals_discovery[lifx_mac_address]
        return False, error_details


# noinspection PyUnresolvedReferences,PyPep8Naming
class ThreadDiscovery(threading.Thread):

    # This class manages discovery of LIFX devices

    def __init__(self, pluginGlobals, event):

        threading.Thread.__init__(self)

        self.globals = pluginGlobals

        self.d_logger = logging.getLogger("Plugin.DISCOVERY")
        self.d_logger.debug(u"Debugging Discovery Thread")

        self.thread_stop = event

        self.lifxlan = None

    def run(self):
        try:
            self.d_logger.debug(u"Discovery Thread initialised")

            while not self.thread_stop.is_set():
                try:
                    lifx_queued_entry = self.globals[K_QUEUES][K_DISCOVERY][K_QUEUE].get(True, 5)

                    # lifx_queued_entry format:
                    #   - Priority
                    #   - Command

                    lifx_queue_priority, lifx_command = lifx_queued_entry

                    # Debug info to log
                    self.d_logger.debug(u"Dequeued Discovery Command '{0}' to process with priority: {1}"
                                        .format(CMD_TRANSLATION[lifx_command], lifx_queue_priority))

                    if lifx_command == CMD_STOP_THREAD:
                        break  # Exit While loop and quit thread

                    if lifx_command == CMD_DISCOVERY:
                        self.discovery()

                except Queue.Empty:
                    pass

        except StandardError as standard_error_message:
            self.d_logger.error(u"StandardError detected in LIFX Discovery Thread. Line {0} has error: {1}"
                                .format(sys.exc_traceback.tb_lineno, standard_error_message))

        self.d_logger.debug(u"LIFX Discovery Thread ended.")

    def discovery(self):
        # Discover LIFX Lamps on demand
        try:
            self.d_logger.info(u"LIFX device discovery starting (this can take up to 60 seconds) . . .")

            # Search LAN for LIF Lamps
            lifxlan = LifxLAN(None)
            lifxlan_devices = lifxlan.get_lights()

            number_of_lifx_devices_detected = len(lifxlan_devices)

            max_len_label = 0
            number_of_lifx_devices_discovered = 0
            for lifx_device in lifxlan_devices:
                try:
                    lifx_device.refresh()
                except WorkflowException:
                    self.d_logger.error(u"Refresh Error for LIFX device:\n{0}\n".format(lifx_device))
                    continue

                #  Now store information about the discovered LIFX device
                return_ok, return_message = store_discovered_lifx_device(self.globals[K_DISCOVERY], lifx_device)
                if not return_ok:
                    self.d_logger.error(u"StandardError detected in 'store_discovered_lifx_device'. Line {0} has error: {1}"
                                        .format(return_message[0], return_message[1]))
                    continue

                lifx_label = str(lifx_device.label).rstrip()
                if len(lifx_label) > max_len_label:
                    max_len_label = len(lifx_label)

                number_of_lifx_devices_discovered += 1

                self.d_logger.debug(u"FEATURES: {0} - [{1}\n{2}\n".format(str(lifx_device.label).rstrip(), lifx_device.product, lifx_device.product_features))

            discoveryMessage = u"\n\nLIFX device discovery has completed."
            if number_of_lifx_devices_detected == number_of_lifx_devices_discovered:
                discoveryMessage = (u"{0} {1} LIFX device(s) have been discovered as follows:\n"
                                    .format(discoveryMessage, number_of_lifx_devices_discovered))
            else:
                discoveryMessage = (u"{0} {1} LIFX device(s) have been detected and {2} LIFX device(s) fully discovered as follows:\n"
                                    .format(discoveryMessage, number_of_lifx_devices_detected, number_of_lifx_devices_discovered))

            max_len_label += 2  # Adjust length to takae accout of enclosing single quotes (see below)

            discoveryMessage = u"{0}\nStart of discovered LIFX devices list ---->\n".format(discoveryMessage)

            discovery_lines = []
            for lifx_key, lifx_value in self.globals[K_DISCOVERY].items():
                lifx_mac_address = lifx_key
                lifx_label = (u"'{0}'".format(lifx_value[K_LABEL])).ljust(max_len_label)
                lifx_ip_address = lifx_value[K_IP_ADDRESS]
                discovery_lines.append(u"  {0} [{1}] at {2}\n".format(lifx_label, lifx_mac_address, lifx_ip_address))
            discovery_lines.sort()

            for discovery_line in discovery_lines:
                discoveryMessage += discovery_line

            discoveryMessage = u"{0}<---- End of discovered LIFX devices list.\n".format(discoveryMessage)
            self.d_logger.info(discoveryMessage)

            # At this point we have discovered all the LIFX Lamps that can currently be detected.

            # Now check for Indigo LIFX Devices and update the self.globals[K_DISCOVERY] dictionary with the Indigo device Ids

            for dev in indigo.devices.iter("self"):
                if dev.address in self.globals[K_DISCOVERY]:
                    self.globals[K_DISCOVERY][dev.address][K_INDIGO_DEVICE_ID] = dev.id
                    connected = True
                    discovered = True
                else:
                    connected = False
                    discovered = False
                    # discovery_ui += (u"LIFX Device {0}: '{1}' [{2}] is not yet visible on the network"
                    #                  u" and therefore a further discovery is required.\n"
                    #                  .format(index_ui, dev.name, dev.address))
                keyValueList = [
                    {"key": "connected", "value": connected},
                    {"key": "discovered", "value": discovered}]
                dev.updateStatesOnServer(keyValueList)

            self.globals[K_INITIAL_DISCOVERY_COMPLETE] = True  # used by plugin startup method

            if not self.globals[K_PLUGIN_CONFIG_DEFAULT][K_AUTO_CREATE_LIFX_DEVICES]:
                return

            # Now check if any lamps need to be auto-created as Indigo devices.

            for lifx_key, lifx_value in self.globals[K_DISCOVERY].items():
                lifx_mac_address = lifx_key
                lifx_label = lifx_value[K_LABEL]
                lifx_ip_address = lifx_value[K_IP_ADDRESS]
                lifx_indigo_device_id = lifx_value[K_INDIGO_DEVICE_ID]
                lifx_product_name = lifx_value[K_PRODUCT_NAME]
                lifx_product_features = lifx_value[K_PRODUCT_FEATURES]
                lifx_product_feature_color = lifx_product_features["color"]
                lifx_product_feature_temperature = lifx_product_features["temperature"]
                lifx_product_feature_min_kelvin = lifx_product_features["min_kelvin"]
                lifx_product_feature_max_kelvin = lifx_product_features["max_kelvin"]
                lifx_product_feature_chain = lifx_product_features["chain"]
                lifx_product_feature_multizone = lifx_product_features["multizone"]
                lifx_product_feature_infrared = lifx_product_features["infrared"]
                lifx_firmware_ui = lifx_value[K_FIRMWARE_UI]

                if lifx_indigo_device_id == 0:  # Create Indigo LIFX devices
                    self.d_logger.info(u"Auto creating Indigo device for LIFX device '{0}' - '{1}'".format(lifx_product_name, lifx_label))

                    dev = (indigo.device.create(protocol=indigo.kProtocol.Plugin,
                                                address=lifx_mac_address,
                                                name=lifx_label,
                                                description="LIFX Device",
                                                pluginId="com.autologplugin.indigoplugin.lifxcontroller",
                                                deviceTypeId="lifxDevice",
                                                props={"version": lifx_firmware_ui,
                                                       "onBrightensToLast": True,
                                                       "SupportsColor": lifx_product_feature_color,
                                                       "SupportsRGB": lifx_product_feature_color,
                                                       "SupportsWhite": lifx_product_feature_temperature,
                                                       "SupportsTwoWhiteLevels": False,
                                                       "SupportsWhiteTemperature": lifx_product_feature_temperature,
                                                       "WhiteTemperatureMin": lifx_product_feature_min_kelvin,
                                                       "WhiteTemperatureMax": lifx_product_feature_max_kelvin,
                                                       "chain": lifx_product_feature_chain,
                                                       "multizone": lifx_product_feature_multizone,
                                                       "supports_infrared": lifx_product_feature_infrared,
                                                       "mac_address": lifx_mac_address,
                                                       "ip_address": lifx_ip_address,
                                                       "lifx_label": lifx_label,
                                                       "set_name_from_lifx_label": True,
                                                       "lifx_device_list": lifx_mac_address},
                                                folder=self.globals[K_FOLDERS][K_DEVICES_ID]))

                    dev.model = lifx_product_name
                    dev.replaceOnServer()

                    self.globals[K_DISCOVERY][lifx_mac_address][K_INDIGO_DEVICE_ID] = dev.id

        except StandardError as standard_error_message:
            self.d_logger.error(u"StandardError detected in 'discovery'. Line {0} has error: {1}".format(
                sys.exc_traceback.tb_lineno, standard_error_message))
