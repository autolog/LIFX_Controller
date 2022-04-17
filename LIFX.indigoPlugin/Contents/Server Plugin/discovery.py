#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# LIFX V7 Controller © Autolog 2020-2022
#

# TODO: TBA
# -
# -


# noinspection PyUnresolvedReferences
# ============================== Native Imports ===============================
import colorsys

try:
    # Python 3
    import queue
except ImportError:
    # Python 2
    import Queue as queue

import sys
import threading
import traceback

# ============================== Custom Imports ===============================
try:
    import indigo
except ImportError:
    pass

# ============================== Plugin Imports ===============================
from constants import *
from lifxlan.lifxlan import *


def store_discovered_lifx_device(globals_discovery, lifx_device):

    lifx_mac_address = None
    try:
        lifx_mac_address = lifx_device.mac_addr
        lifx_ip_address = lifx_device.ip_addr
        lifx_port = lifx_device.port
        lifx_label = str(lifx_device.label).rstrip()
        lifx_group = lifx_device.group
        lifx_location = lifx_device.location
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
            lifx_firmware_ui = f"{lifx_host_firmware_version}|{lifx_wifi_firmware_version}"

        if lifx_mac_address not in globals_discovery:
            globals_discovery[lifx_mac_address] = dict()
            globals_discovery[lifx_mac_address][K_LABEL] = lifx_label
            globals_discovery[lifx_mac_address][K_IP_ADDRESS] = lifx_ip_address
            globals_discovery[lifx_mac_address][K_PORT] = lifx_port
            globals_discovery[lifx_mac_address][K_GROUP] = lifx_group
            globals_discovery[lifx_mac_address][K_LOCATION] = lifx_location
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
        if globals_discovery[lifx_mac_address][K_LOCATION] != lifx_location:
            globals_discovery[lifx_mac_address][K_LOCATION] = lifx_location
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

    except Exception as exception_error:
        filename, line_number, method, statement = traceback.extract_tb(sys.exc_info()[2])[-1]
        module = filename.split('/')

        if lifx_mac_address is not None:
            del globals_discovery[lifx_mac_address]
        log_message = f"'{exception_error}' in module '{module[-1]}', method '{method}'\n   Failing statement [line {line_number}]: '{statement}'"

        return False, log_message


# noinspection PyUnresolvedReferences,PyPep8Naming
class ThreadDiscovery(threading.Thread):

    # This class manages discovery of LIFX devices

    def __init__(self, pluginGlobals, event):

        threading.Thread.__init__(self)

        self.globals = pluginGlobals

        self.d_logger = logging.getLogger("Plugin.DISCOVERY")
        self.d_logger.debug("Debugging Discovery Thread")

        self.thread_stop = event

        self.lifxlan = None

    def exception_handler(self, exception_error_message, log_failing_statement):
        filename, line_number, method, statement = traceback.extract_tb(sys.exc_info()[2])[-1]
        module = filename.split('/')
        log_message = f"'{exception_error_message}' in module '{module[-1]}', method '{method}'"
        if log_failing_statement:
            log_message = log_message + f"\n   Failing statement [line {line_number}]: '{statement}'"
        else:
            log_message = log_message + f" at line {line_number}"
        self.d_logger.error(log_message)

    def run(self):
        try:
            self.d_logger.debug("Discovery Thread initialised")

            while not self.thread_stop.is_set():
                try:
                    lifx_queued_entry = self.globals[K_QUEUES][K_DISCOVERY][K_QUEUE].get(True, 5)

                    # lifx_queued_entry format:
                    #   - Priority
                    #   - Command

                    lifx_queue_priority, lifx_command = lifx_queued_entry

                    # Debug info to log
                    self.d_logger.debug(f"Dequeued Discovery Command '{CMD_TRANSLATION[lifx_command]}' to process with priority: {lifx_queue_priority}")

                    if lifx_command == CMD_STOP_THREAD:
                        break  # Exit While loop and quit thread

                    if lifx_command == CMD_DISCOVERY:
                        self.discovery()

                except queue.Empty:
                    pass

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

        self.d_logger.debug("LIFX Discovery Thread ended.")

    def discovery(self):
        # Discover LIFX Lamps on demand
        try:
            self.d_logger.info("LIFX device discovery starting (this can take up to 60 seconds) . . .")

            # Search LAN for LIF Lamps
            lifxlan = LifxLAN(None)
            lifxlan_devices = lifxlan.get_lights()

            number_of_lifx_devices_detected = len(lifxlan_devices)

            max_len_label = 0
            max_len_ip_address = 0
            number_of_lifx_devices_discovered = 0
            for lifx_device in lifxlan_devices:
                try:
                    lifx_device.refresh()
                except WorkflowException:
                    self.d_logger.error(f"Refresh Error for LIFX device:\n{lifx_device}\n")
                    continue

                #  Now store information about the discovered LIFX device
                return_ok, return_message = store_discovered_lifx_device(self.globals[K_DISCOVERY], lifx_device)
                if not return_ok:
                    self.d_logger.error(return_message)
                    continue

                lifx_label = str(lifx_device.label).rstrip()
                if len(lifx_label) > max_len_label:
                    max_len_label = len(lifx_label)

                lifx_ip_address = str(lifx_device.ip_addr).rstrip()
                if len(lifx_ip_address) > max_len_ip_address:
                    max_len_ip_address = len(lifx_ip_address)

                number_of_lifx_devices_discovered += 1

                self.d_logger.debug(f"FEATURES: {str(lifx_device.label).rstrip()} - [{lifx_device.product}\n{lifx_device.product_features}\n")

            discoveryMessage = "\n\nLIFX device discovery has completed."
            if number_of_lifx_devices_detected == number_of_lifx_devices_discovered:
                discoveryMessage = (f"{discoveryMessage} {number_of_lifx_devices_discovered} LIFX device(s) have been discovered as follows:\n")
            else:
                discoveryMessage = (
                    f"{discoveryMessage} {number_of_lifx_devices_detected} LIFX device(s) have been detected and {number_of_lifx_devices_discovered} LIFX device(s) fully discovered as follows:\n")

            max_len_label += 2  # Adjust length to take account of enclosing single quotes (see below)
            max_len_ip_address += 3  # Adjust length to take account of enclosing single quotes and full-stop (see below)

            discoveryMessage = f"{discoveryMessage}\nStart of discovered LIFX devices list ---->\n"

            discovery_lines = []
            for lifx_key, lifx_value in self.globals[K_DISCOVERY].items():
                lifx_mac_address = lifx_key
                lifx_label = (f"'{lifx_value[K_LABEL]}'").ljust(max_len_label)
                lifx_ip_address = (f"'{lifx_value[K_IP_ADDRESS]}'.").ljust(max_len_ip_address)
                # lifx_ip_address = lifx_value[K_IP_ADDRESS]
                lifx_product = lifx_value[K_PRODUCT]
                lifx_product_name = lifx_value[K_PRODUCT_NAME]
                discovery_lines.append(f"  {lifx_label} [MAC {lifx_mac_address}] at IP {lifx_ip_address} Product {lifx_product}: {lifx_product_name}\n")
            discovery_lines.sort()

            for discovery_line in discovery_lines:
                discoveryMessage += discovery_line

            discoveryMessage = f"{discoveryMessage}<---- End of discovered LIFX devices list.\n"
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
                    # discovery_ui += (f"LIFX Device {index_ui}: '{dev.name}' [{dev.address}] is not yet visible on the network and therefore a further discovery is required.\n")
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
                lifx_product = lifx_value[K_PRODUCT]
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
                    self.d_logger.info(f"Auto creating Indigo device for LIFX device '{lifx_product_name}' - '{lifx_label}'")

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

                    dev.model = f"{lifx_product_name} [{lifx_product}]"
                    dev.replaceOnServer()

                    self.globals[K_DISCOVERY][lifx_mac_address][K_INDIGO_DEVICE_ID] = dev.id

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement
