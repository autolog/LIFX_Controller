#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# LIFX V7 Controller © Autolog 2020-2022

# noinspection PyUnresolvedReferences
# ============================== Native Imports ===============================
import colorsys
import platform

import queue
import re
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
from discovery import ThreadDiscovery
from discovery import store_discovered_lifx_device
from lifxlanHandler import ThreadLifxlanHandler
from polling import ThreadPolling
from lifxlan.lifxlan import *

import socket  # Must be placed AFTER 'from lifxlan.lifxlan import *' statement!


# noinspection PyPep8Naming,PyUnresolvedReferences
class Plugin(indigo.PluginBase):

    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        # Initialise dictionary to store plugin Globals aka plugin working storage
        self.globals = dict()

        # Initialise Indigo plugin info
        self.globals[K_PLUGIN_INFO] = dict()
        self.globals[K_PLUGIN_INFO][K_PLUGIN_ID] = pluginId
        self.globals[K_PLUGIN_INFO][K_PLUGIN_DISPLAY_NAME] = pluginDisplayName
        self.globals[K_PLUGIN_INFO][K_PLUGIN_VERSION] = pluginVersion
        self.globals[K_PLUGIN_INFO][K_PATH] = indigo.server.getInstallFolderPath()
        self.globals[K_PLUGIN_INFO][K_API_VERSION] = indigo.server.apiVersion
        self.globals[K_PLUGIN_INFO][K_ADDRESS] = indigo.server.address

        # Initialise dictionary for debug log levels in plugin Globals
        self.globals[K_DEBUG] = dict()
        self.globals[K_DEBUG][K_LOG_TO_EVENT_LOG] = logging.DEBUG  # set loglevel fo Indigo Event log

        # Setup Logging
        #
        # Logging info:
        #   self.indigo_log_handler - writes log messages to Indigo Event Log
        #   self.plugin_file_handler - writes log messages to the plugin log

        log_format = logging.Formatter("%(asctime)s.%(msecs)03d\t%(levelname)-12s\t%(name)s.%(funcName)-25s %(msg)s",datefmt="%Y-%m-%d %H:%M:%S")
        self.plugin_file_handler.setFormatter(log_format)
        self.plugin_file_handler.setLevel(K_LOG_LEVEL_INFO)  # Logging Level for plugin log file
        self.indigo_log_handler.setLevel(K_LOG_LEVEL_INFO)   # Logging level for Indigo Event Log

        self.logger = logging.getLogger("Plugin.LIFX")

        # Now logging is set up, output Initialising Message
        startup_message_ui = "\n"  # Start with a line break
        startup_message_ui += f"{' Initialising LIFX Controller Bridge Plugin Plugin ':={'^'}130}\n"
        startup_message_ui += f"{'Plugin Name:':<31} {self.globals[K_PLUGIN_INFO][K_PLUGIN_DISPLAY_NAME]}\n"
        startup_message_ui += f"{'Plugin Version:':<31} {self.globals[K_PLUGIN_INFO][K_PLUGIN_VERSION]}\n"
        startup_message_ui += f"{'Plugin ID:':<31} {self.globals[K_PLUGIN_INFO][K_PLUGIN_ID]}\n"
        startup_message_ui += f"{'Indigo Version:':<31} {indigo.server.version}\n"
        startup_message_ui += f"{'Indigo License:':<31} {indigo.server.licenseStatus}\n"
        startup_message_ui += f"{'Indigo API Version:':<31} {indigo.server.apiVersion}\n"
        machine = platform.machine()
        startup_message_ui += f"{'Architecture:':<31} {machine}\n"
        sys_version = sys.version.replace("\n", "")
        startup_message_ui += f"{'Python Version:':<31} {sys_version}\n"
        startup_message_ui += f"{'Mac OS Version:':<31} {platform.mac_ver()[0]}\n"
        startup_message_ui += f"{'':={'^'}130}\n"
        self.logger.info(startup_message_ui)

        # Initialise dictionary to store internal details about LIFX devices
        self.globals[K_LIFX] = dict()

        # Initialise dictionary to store folder Ids
        self.globals[K_FOLDERS] = dict()
        self.globals[K_FOLDERS][K_DEVICES_ID] = 0  # Id of Devices folder to hold LIFX devices
        self.globals[K_FOLDERS][K_VARIABLES_ID] = 0   # Id of Variables folder to hold LIFX preset variables

        # Initialise dictionary to store per-lamp timers
        self.globals[K_DEVICE_TIMERS] = dict()
        self.globals[K_RECOVERY_TIMERS] = dict()

        # Initialise dictionaries to store message queues
        self.globals[K_QUEUES] = dict()
        self.globals[K_QUEUES][K_LIFXLAN_HANDLER] = dict()
        self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE] = None
        self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_INITIALISED] = False
        self.globals[K_QUEUES][K_DISCOVERY] = dict()
        self.globals[K_QUEUES][K_DISCOVERY][K_QUEUE] = None
        self.globals[K_QUEUES][K_DISCOVERY][K_INITIALISED] = False

        # Initialise dictionary to store threads
        self.globals[K_THREADS] = dict()
        self.globals[K_THREADS][K_POLLING] = dict()  # There is only one "polling" thread for all LIFX devices
        self.globals[K_THREADS][K_DISCOVERY] = dict()  # There is only one "discovery" thread for all LIFX devices
        self.globals[K_THREADS][K_LIFXLAN_HANDLER] = dict()  # There is only one "lifxlanHandler" thread for all LIFX devices

        self.globals[K_THREADS][K_RUN_CONCURRENT_ACTIVE] = False

        # Initialise dictionary for polling (single thread for all LIFX devices)
        self.globals[K_POLLING] = dict()
        self.globals[K_POLLING][K_THREAD_ACTIVE] = False        
        self.globals[K_POLLING][K_STATUS] = False
        self.globals[K_POLLING][K_SECONDS] = float(300.0)  # 5 minutes
        self.globals[K_POLLING][K_FORCE_THREAD_END] = False
        self.globals[K_POLLING][K_QUIESCED] = False

        # Initialise dictionary for constants
        self.globals[K_CONSTANT] = dict()

        # Initialise dictionary for discovery processing
        self.globals[K_DELETING] = dict()

        # Initialise dictionary for managing device deletion
        self.globals[K_DISCOVERY] = dict()
        self.globals[K_INITIAL_DISCOVERY_COMPLETE] = False

        # Initialise dictionary for managing device deletion
        self.globals[K_RECOVERY] = dict()

        # Set Plugin Config Values
        self.globals[K_PLUGIN_CONFIG_DEFAULT] = dict()
        self.closedPrefsConfigUi(pluginPrefs, False)
 
    def __del__(self):

        indigo.PluginBase.__del__(self)

    def exception_handler(self, exception_error_message, log_failing_statement):
        filename, line_number, method, statement = traceback.extract_tb(sys.exc_info()[2])[-1]
        module = filename.split('/')
        log_message = f"'{exception_error_message}' in module '{module[-1]}', method '{method}'"
        if log_failing_statement:
            log_message = log_message + f"\n   Failing statement [line {line_number}]: '{statement}'"
        else:
            log_message = log_message + f" at line {line_number}"
        self.logger.error(log_message)

    def actionControlDevice(self, action, dev):
        try:
            if not dev.states["connected"] or not self.globals[K_LIFX][dev.id][K_CONNECTED]:
                self.logger.info(f"Unable to process  '{action.deviceAction}'' for '{dev.name}' as device not connected - will try to reconnect . . .")
                self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put([QUEUE_PRIORITY_STATUS_MEDIUM, CMD_RECOVERY_STATUS, dev.id, None])
                return

            # ##### TURN ON ######
            if action.deviceAction == indigo.kDeviceAction.TurnOn:
                self.process_turn_on(action, dev)

            # ##### TURN OFF ######
            elif action.deviceAction == indigo.kDeviceAction.TurnOff:
                self.process_turn_off(action, dev)

            # ##### TOGGLE ######
            elif action.deviceAction == indigo.kDeviceAction.Toggle:
                self.process_turn_on_off_toggle(action, dev)

            # ##### SET BRIGHTNESS ######
            elif action.deviceAction == indigo.kDeviceAction.SetBrightness:
                new_brightness = action.actionValue   # action.actionValue contains brightness value (0 - 100)
                self.process_brightness_set(action, dev, new_brightness)

            # ##### BRIGHTEN BY ######
            elif action.deviceAction == indigo.kDeviceAction.BrightenBy:
                if not dev.onState:
                    self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put([QUEUE_PRIORITY_COMMAND_HIGH, CMD_IMMEDIATE_ON,
                                                                           dev.id, None])

                if dev.brightness < 100:
                    brighten_by = action.actionValue  # action.actionValue contains brightness increase value
                    new_brightness = dev.brightness + brighten_by
                    if new_brightness > 100:
                        new_brightness = 100
                    self.logger.info(f"Brightening {dev.name} by {brighten_by} to {new_brightness}")
                    self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put([QUEUE_PRIORITY_COMMAND_HIGH, CMD_BRIGHTEN, dev.id,
                                                                           [new_brightness]])
                    dev.updateStateOnServer("brightnessLevel", new_brightness)
                else:
                    self.logger.info(f"Ignoring Brighten request for {dev.name} as device is already at full brightness")

            # ##### DIM BY ######
            elif action.deviceAction == indigo.kDeviceAction.DimBy:
                if dev.onState and dev.brightness > 0:
                    dim_by = action.actionValue  # action.actionValue contains brightness decrease value
                    new_brightness = dev.brightness - dim_by
                    if new_brightness < 0:
                        new_brightness = 0
                        dev.updateStateOnServer("brightnessLevel", new_brightness)
                        self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put([QUEUE_PRIORITY_COMMAND_HIGH, CMD_OFF, dev.id, None])
                        self.logger.info(f"sent '{dev.name}' dim to off")
                    else:
                        self.logger.info(f"Dimming '{dev.name}'' by {dim_by} to {new_brightness}")
                        self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put([QUEUE_PRIORITY_COMMAND_HIGH, CMD_DIM, dev.id,
                                                                               [new_brightness]])
                        dev.updateStateOnServer("brightnessLevel", new_brightness)
                else:
                    self.logger.info(f"Ignoring Dim request for '{dev.name}'' as device is already Off")

            # ##### SET COLOR LEVELS ######
            elif action.deviceAction == indigo.kDeviceAction.SetColorLevels:
                self.logger.debug(f"SET COLOR LEVELS = '{dev.name}' {action}")
                self.process_set_color_levels(action, dev)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    # =============================================================================
    def closedDeviceConfigUi(self, values_dict=None, user_cancelled=False, type_id="", dev_id=0):
        """
        Indigo method invoked after device configuration dialog is closed.

        -----
        :param values_dict:
        :param user_cancelled:
        :param type_id:
        :param dev_id:
        :return:
        """

        # dev = indigo.devices[int(dev_id)]  # dev is not currently used.

        try:
            if user_cancelled:
                self.logger.debug(f"'closedDeviceConfigUi' called with userCancelled = {user_cancelled}")
                return

            if type_id != "lifxDevice":
                return

            dev = indigo.devices[dev_id]

            # Establish internal store for device
            if dev_id not in self.globals[K_LIFX]:
                self.globals[K_LIFX][dev_id] = dict()

            lifx_mac_address = values_dict["mac_address"]

            if lifx_mac_address in self.globals[K_DISCOVERY]:
                if self.globals[K_DISCOVERY][lifx_mac_address][K_INDIGO_DEVICE_ID] == 0:
                    self.globals[K_DISCOVERY][lifx_mac_address][K_INDIGO_DEVICE_ID] = dev_id

                for key in self.globals[K_DISCOVERY].keys():
                    if key != lifx_mac_address:
                        if self.globals[K_DISCOVERY][key][K_INDIGO_DEVICE_ID] == dev_id:
                            self.globals[K_DISCOVERY][key][K_INDIGO_DEVICE_ID] = 0

                old_ip_address = self.globals[K_DISCOVERY][lifx_mac_address][K_IP_ADDRESS]
                if "ip_address" in values_dict and values_dict["ip_address"] != old_ip_address:
                    new_ip_address = values_dict["ip_address"]
                    self.globals[K_DISCOVERY][lifx_mac_address][K_IP_ADDRESS] = new_ip_address
                    self.logger.warning(f"LIFX Lamp [{lifx_mac_address}] IP Address updated from '{old_ip_address}' to '{new_ip_address}'")

                if "set_name_from_lifx_label" in values_dict and values_dict["set_name_from_lifx_label"]:
                    dev.name = self.globals[K_DISCOVERY][dev.address][K_LABEL]
                    dev.replaceOnServer()

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement
            return

    def closedPrefsConfigUi(self, values_dict, userCancelled):
        try:
            self.logger.debug(f"'closePrefsConfigUi' called with userCancelled = {userCancelled}")

            if userCancelled:
                return

            # Get required Event Log and Plugin Log logging levels
            plugin_log_level = int(values_dict.get("plugin_log_level", K_LOG_LEVEL_INFO))
            event_log_level = int(values_dict.get("event_log_level", K_LOG_LEVEL_INFO))

            # Ensure following logging level messages are output
            self.indigo_log_handler.setLevel(K_LOG_LEVEL_INFO)
            self.plugin_file_handler.setLevel(K_LOG_LEVEL_INFO)

            self.logger.info(f"Logging to Indigo Event Log at the '{K_LOG_LEVEL_TRANSLATION[event_log_level]}' level")
            self.logger.info(f"Logging to LIFX Plugin Log at the '{K_LOG_LEVEL_TRANSLATION[plugin_log_level]}' level")

            # Now set required logging levels
            self.indigo_log_handler.setLevel(event_log_level)
            self.plugin_file_handler.setLevel(plugin_log_level)

            self.globals[K_POLLING][K_STATUS] = bool(values_dict.get("status_polling", False))
            self.globals[K_POLLING][K_SECONDS] = float(values_dict.get("polling_seconds", float(300.0)))  # Default to 5 minutes

            self.globals[K_POLLING][K_MINUTES] = int(values_dict.get("discovery_minutes", int(5)))  # Default to 5 minutes

            self.globals[K_PLUGIN_CONFIG_DEFAULT][K_RECOVERY_ATTEMPTS_LIMIT] = int(
                self.pluginPrefs.get("recovery_attempts_limit", 30))
            self.globals[K_PLUGIN_CONFIG_DEFAULT][K_RECOVERY_FREQUENCY] = float(
                self.pluginPrefs.get("recovery_frequency", 5.0))
            self.globals[K_PLUGIN_CONFIG_DEFAULT][K_HIDE_RECOVERY_MESSAGES] = bool(
                self.pluginPrefs.get("hide_recovery_messages", False))
            self.globals[K_PLUGIN_CONFIG_DEFAULT][K_AUTO_CREATE_LIFX_DEVICES] = bool(
                self.pluginPrefs.get("auto_create_lifx_devices", False))
            self.globals[K_PLUGIN_CONFIG_DEFAULT][K_DURATION_DIM_BRIGHTEN] = float(
                values_dict.get("default_duration_dim_brighten", float(1.0)))  # Default to one second
            self.globals[K_PLUGIN_CONFIG_DEFAULT][K_DURATION_ON] = float(
                self.pluginPrefs.get("default_duration_on", 1.0))
            self.globals[K_PLUGIN_CONFIG_DEFAULT][K_DURATION_OFF] = float(
                self.pluginPrefs.get("default_duration_off", 1.0))
            self.globals[K_PLUGIN_CONFIG_DEFAULT][K_DURATION_COLOR_WHITE] = float(
                self.pluginPrefs.get("default_duration_color_white", 1.0))

            # Following logic checks whether polling is required.
            #
            # If it isn't required, then it checks if a polling thread exists and if it does, it ends it
            # If it is required, then it checks if a polling thread exists and
            #   if a polling thread does not exist it will create one as long as the start logic has completed
            #     and created a LIFX Command Queue.
            #   In the case where a LIFX command queue hasn't been created then it means "Start" is yet to run and so
            #   "Start" will create the polling thread. So this bit of logic is mainly used where polling has been turned off
            #   after starting and then turned on again
            # If polling is required and a polling thread exists, then the logic "sets" an event to cause the polling thread to awaken and
            #   update the polling interval

            if not self.globals[K_POLLING][K_STATUS]:
                if self.globals[K_POLLING][K_THREAD_ACTIVE]:
                    self.globals[K_POLLING][K_FORCE_THREAD_END] = True
                    self.globals[K_THREADS][K_POLLING][K_EVENT].set()  # Stop the Polling Thread
                    self.globals[K_THREADS][K_POLLING][K_THREAD].join(5.0)  # Wait for up t0 5 seconds for it to end
                    # Delete thread so that it can be recreated if polling is turned on again
                    del self.globals[K_THREADS][K_POLLING][K_THREAD]
            else:
                if not self.globals[K_POLLING][K_THREAD_ACTIVE]:
                    if self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_INITIALISED]:
                        self.globals[K_POLLING][K_FORCE_THREAD_END] = False
                        self.globals[K_THREADS][K_POLLING][K_EVENT] = threading.Event()
                        self.globals[K_THREADS][K_POLLING][K_THREAD] = \
                            ThreadPolling(self.globals, self.globals[K_THREADS][K_POLLING][K_EVENT])
                        self.globals[K_THREADS][K_POLLING][K_THREAD].start()
                else:
                    self.globals[K_POLLING][K_FORCE_THREAD_END] = False
                    # cause the Polling Thread to update immediately with potentially new polling seconds value
                    self.globals[K_THREADS][K_POLLING][K_EVENT].set()

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement
            return True

    def deviceDeleted(self, dev):
        try:
            if dev.address in self.globals[K_DISCOVERY]:
                self.globals[K_DISCOVERY][dev.address][K_INDIGO_DEVICE_ID] = 0
            self.globals[K_DELETING][dev.id] = True

        except Exception as exception_error:
            self.logger.error(f"'deviceDeleted' error detected for device '{dev.name}'. Line '{sys.exc_traceback.tb_lineno}' has error='{exception_error}'")

        finally:
            super(Plugin, self).deviceDeleted(dev)

    def deviceStartComm(self, dev):
        try:
            self.logger.info(f"Starting  '{dev.name}' . . . ")

            if dev.deviceTypeId != "lifxDevice":
                self.logger.error(f". . . failed to start device '{dev.name}'. Device type '{dev.deviceTypeId}' not known by plugin.")
                return

            dev_id = dev.id

            if float(indigo.server.apiVersion) >= 2.5:
                if dev.subType != indigo.kDimmerDeviceSubType.ColorBulb:
                    dev.subType = indigo.kDimmerDeviceSubType.ColorBulb
                    dev.replaceOnServer()

            lifx_mac_address = dev.pluginProps.get("mac_address", "")

            if lifx_mac_address == "":
                self.logger.error(f". . . failed to start device '{dev.name}'. Edit device and select a LIFX device to assign to the Indigo device, save and then re-enable.")
                indigo.device.enable(dev_id, value=False)
                return

            if dev.address != lifx_mac_address:
                plugin_props = dev.pluginProps
                plugin_props.update({"address": lifx_mac_address})
                dev.replacePluginPropsOnServer(plugin_props)

            dev.stateListOrDisplayStateIdChanged()  # Ensure that latest devices.xml is being used

            # Establish internal store for device
            if dev_id not in self.globals[K_LIFX]:
                self.globals[K_LIFX][dev_id] = dict()
                self.globals[K_LIFX][dev_id][K_CONNECTED] = False
                self.globals[K_LIFX][dev_id][K_DISCOVERED] = False
                # self.globals[K_LIFX][dev_id][K_NO_ACK_STATE] = False
                self.globals[K_LIFX][dev_id][K_IGNORE_NO_ACK] = bool(dev.pluginProps.get("ignore_no_ack", False))

            # Set LIFX device Timer icon and "... UI state etc
            dev.updateStateImageOnServer(indigo.kStateImageSel.TimerOn)
            dev.updateStateOnServer(key="connected", value=False)
            dev.updateStateOnServer(key="discovered", value=False)
            # dev.updateStateOnServer(key="no_ack_state", value=False)
            dev.updateStateOnServer(key="onOffState", value=False)
            dev.updateStateOnServer(key="brightnessLevel", value=0, uiValue="starting ...")

            if dev.address in self.globals[K_DISCOVERY]:  # dev.address is LIFX lamp MAC address
                match_status_ui = "Previously matched"

                # Check if IP Address has changed

                lifx_props = dev.pluginProps
                ip_address = self.globals[K_DISCOVERY][lifx_mac_address][K_IP_ADDRESS]
                if "ip_address" not in lifx_props or lifx_props["ip_address"] != ip_address:
                    self.logger.warning(f"IP address of LIFX device '{dev.name}' has changed from {lifx_props['ip_address']} to {ip_address}")
                    lifx_props["ip_address"] = ip_address
                    dev.replacePluginPropsOnServer(lifx_props)
                    dev.refreshFromServer()

            else:
                # The Indigo device has not been previously discovered as a LIFX lamp
                match_status_ui = "Newly matched"

            lifx_ip_address = dev.pluginProps.get("ip_address", "")
            if lifx_ip_address == "":
                # Unable to retrieve LIFX device details
                # Stop device at this point?
                return

            try:
                int(dev.states["total_successful_recoveries"])
            except ValueError:
                total_successful_recoveries = 0
                dev.updateStateOnServer(key="total_successful_recoveries", value=total_successful_recoveries)
            try:
                int(dev.states["total_recovery_attempts"])
            except ValueError:
                total_recovery_attempts = 0
                dev.updateStateOnServer(key="total_recovery_attempts", value=total_recovery_attempts)
            try:
                int(dev.states["total_no_ack_events"])
            except ValueError:
                total_no_ack_events = 0
                dev.updateStateOnServer(key="total_no_ack_events", value=total_no_ack_events)

            refresh_count = 0
            refreshed = False
            while refresh_count < 5:
                self.globals[K_LIFX][dev_id][K_LIFX_DEVICE] = Light(lifx_mac_address, lifx_ip_address)
                try:
                    self.globals[K_LIFX][dev_id][K_LIFX_DEVICE].refresh()
                    refreshed = True
                    break
                except (Exception, WorkflowException):
                    if refresh_count == 0:
                        total_recovery_attempts = int(dev.states["total_recovery_attempts"])
                        total_recovery_attempts += 1
                        dev.updateStateOnServer(key="total_recovery_attempts", value=total_recovery_attempts)
                        self.logger.warning(f"Having trouble accessing LIFX device '{dev.name}' with MAC address '{lifx_mac_address}' at IP address '{lifx_ip_address} . . .")

                    self.logger.warning(f". . . Trying again to access '{dev.name}' . . .")
                    self.globals[K_LIFX][dev_id][K_LIFX_DEVICE] = None
                    self.sleep(1.0)
                refresh_count += 1
            if not refreshed:
                self.logger.error(f". . . Giving up! Failed to access LIFX device '{dev.name}' with MAC address '{lifx_mac_address}' at IP address '{lifx_ip_address}")
                # dev.updateStateOnServer(key="no_ack_state", value=True)
                self.globals[K_LIFX][dev_id][K_CONNECTED] = False
                dev.updateStateOnServer(key="connected", value=False)
                if self.globals[K_LIFX][dev_id][K_IGNORE_NO_ACK]:
                    indigo.devices[dev_id].updateStateImageOnServer(indigo.kStateImageSel.PowerOff)
                    indigo.devices[dev_id].updateStateOnServer(key="onOffState",
                                                               value=False,
                                                               clearErrorState=True)
                    indigo.devices[dev_id].updateStateOnServer(key="brightnessLevel", value=0, uiValue="0")

                else:
                    dev.setErrorStateOnServer("no ack")

                total_no_ack_events = int(dev.states["total_no_ack_events"])
                total_no_ack_events += 1
                dev.updateStateOnServer(key="total_no_ack_events", value=total_no_ack_events)

                return
            elif refresh_count > 0:
                total_successful_recoveries = int(dev.states["total_successful_recoveries"])
                total_successful_recoveries += 1
                dev.updateStateOnServer(key="total_successful_recoveries", value=total_successful_recoveries)
                self.logger.info(f". . . Successfully recovered access to LIFX device '{dev.name}' with MAC address '{lifx_mac_address}' at IP address '{lifx_ip_address}")

            return_ok, return_message = store_discovered_lifx_device(self.globals[K_DISCOVERY], self.globals[K_LIFX][dev_id][K_LIFX_DEVICE])
            if not return_ok:
                self.logger.warning(f'Unable to store discovered device: {return_message}')
                # self.exception_handler(return_message, True)  # Log error and display failing statement
                self.globals[K_LIFX][dev_id][K_LIFX_DEVICE] = None
                return

            self.logger.debug(f"{match_status_ui} '{dev.name} to LIFX device type '{self.globals[K_DISCOVERY][dev.address][K_PRODUCT_NAME]}'")

            # Compare the device props with the real LIFX device and update if necessary

            lifx_props = dev.pluginProps

            label = self.globals[K_DISCOVERY][dev.address][K_LABEL]
            if "set_name_from_lifx_label" in lifx_props and lifx_props["set_name_from_lifx_label"]:
                if dev.name != label:
                    dev.name = label
                    dev.replaceOnServer()

            lifx_model = f"{self.globals[K_DISCOVERY][dev.address][K_PRODUCT_NAME]} [{self.globals[K_DISCOVERY][dev.address][K_PRODUCT]}]"
            if dev.model != lifx_model:
                dev.model = lifx_model
                dev.replaceOnServer()

            lifx_props_changed = False

            # TODO: Next 4 lines of code have been moved upwards to take place prior to accessing the LIFX devices
            # ip_address = self.globals[K_DISCOVERY][lifx_mac_address][K_IP_ADDRESS]
            # if "ip_address" not in lifx_props or lifx_props["ip_address"] != ip_address:
            #     lifx_props["ip_address"] = ip_address
            #     lifx_props_changed = True

            port = self.globals[K_DISCOVERY][lifx_mac_address][K_PORT]
            if "port" not in lifx_props or lifx_props["port"] != port:
                lifx_props["port"] = port
                lifx_props_changed = True

            version = self.globals[K_DISCOVERY][lifx_mac_address][K_FIRMWARE_UI]
            if "version" not in lifx_props or lifx_props["version"] != version:
                lifx_props["version"] = version
                lifx_props_changed = True

            min_kelvin = self.globals[K_DISCOVERY][lifx_mac_address][K_PRODUCT_FEATURES]["min_kelvin"]
            if "WhiteTemperatureMin" not in lifx_props or lifx_props["WhiteTemperatureMin"] != min_kelvin:
                lifx_props["WhiteTemperatureMin"] = min_kelvin
                lifx_props_changed = True

            max_kelvin = self.globals[K_DISCOVERY][lifx_mac_address][K_PRODUCT_FEATURES]["max_kelvin"]
            if "WhiteTemperatureMax" not in lifx_props or lifx_props["WhiteTemperatureMax"] != max_kelvin:
                lifx_props["WhiteTemperatureMax"] = max_kelvin
                lifx_props_changed = True

            Supports_color = self.globals[K_DISCOVERY][lifx_mac_address][K_PRODUCT_FEATURES]["color"]
            if ("SupportsColor" not in lifx_props or lifx_props["SupportsColor"] != Supports_color
                    or "SupportsRGB" not in lifx_props or lifx_props["SupportsRGB"] != Supports_color):
                lifx_props["SupportsColor"] = Supports_color
                lifx_props["SupportsRGB"] = Supports_color
                lifx_props_changed = True

            Supports_white = self.globals[K_DISCOVERY][lifx_mac_address][K_PRODUCT_FEATURES]["temperature"]
            if ("SupportsWhite" not in lifx_props or lifx_props["SupportsWhite"] != Supports_white
                    or "SupportsWhiteTemperature" not in lifx_props or lifx_props["SupportsWhiteTemperature"] != Supports_white
                    or "SupportsTwoWhiteLevels" not in lifx_props or lifx_props["SupportsTwoWhiteLevels"] is not False):
                lifx_props["SupportsWhite"] = Supports_white
                lifx_props["SupportsWhiteTemperature"] = Supports_white
                lifx_props["SupportsTwoWhiteLevels"] = False
                lifx_props_changed = True

            #  Indigo "SupportsColor" property has to be set to enable "SupportsWhite" in Indigo
            if Supports_white:
                lifx_props["SupportsColor"] = Supports_white
                lifx_props_changed = True

            supports_infrared = self.globals[K_DISCOVERY][lifx_mac_address][K_PRODUCT_FEATURES]["infrared"]
            if "supports_infrared" not in lifx_props or lifx_props["supports_infrared"] != supports_infrared:
                lifx_props["supports_infrared"] = supports_infrared
                lifx_props_changed = True

            chain = self.globals[K_DISCOVERY][lifx_mac_address][K_PRODUCT_FEATURES]["chain"]
            if "chain" not in lifx_props or lifx_props["chain"] != chain:
                lifx_props["chain"] = chain
                lifx_props_changed = True

            multizone = self.globals[K_DISCOVERY][lifx_mac_address][K_PRODUCT_FEATURES]["multizone"]
            if "multizone" not in lifx_props or lifx_props["multizone"] != multizone:
                lifx_props["multizone"] = multizone
                lifx_props_changed = True

            if lifx_props_changed:
                # self.logger.debug(f'LIFX PROPS [1]:\n{lifx_props}')
                dev.replacePluginPropsOnServer(lifx_props)

            # Cancel any existing timers
            if dev_id in self.globals[K_DEVICE_TIMERS]:
                for timer in self.globals[K_DEVICE_TIMERS][dev_id]:
                    self.globals[K_DEVICE_TIMERS][dev_id][timer].cancel()

            # Initialise LIFX Device Timers dictionary
            self.globals[K_DEVICE_TIMERS][dev_id] = dict()

            dev.updateStateOnServer(key="connected", value=True)
            dev.updateStateOnServer(key="discovered", value=True)

            # Initialise internal to plugin lifx lamp states to default values

            self.globals[K_LIFX][dev_id][K_DISCOVERED] = dev.states["discovered"]
            self.globals[K_LIFX][dev_id][K_CONNECTED] = dev.states["connected"]
            self.globals[K_LIFX][dev_id][K_MAC_ADDRESS] = dev.address  # eg. "d0:73:d5:0a:bc:de"
            self.globals[K_LIFX][dev_id][K_IP_ADDRESS] = lifx_props["ip_address"]
            self.globals[K_LIFX][dev_id][K_PORT] = lifx_props["port"]
            # self.globals[K_LIFX][dev_id][K_NO_ACK_STATE] = dev.states["no_ack_state"]

            self.globals[K_LIFX][dev_id]["lastResponseToPollCount"] = 0
            self.globals[K_LIFX][dev_id][K_LIFX_COMMAND_CURRENT] = ""  # Record of current command invoked for LIFX device (just before Queue Get)
            self.globals[K_LIFX][dev_id][K_LIFX_COMMAND_PREVIOUS] = ""  # Record of last command invoked for LIFX device

            self.globals[K_LIFX][dev_id]["datetimeStarted"] = indigo.server.getTime()

            self.globals[K_LIFX][dev_id]["onState"] = False      # True or False
            self.globals[K_LIFX][dev_id]["onOffState"] = "off"   # "on" or "off"
            self.globals[K_LIFX][dev_id]["turn_on_if_off"] = bool(dev.pluginProps.get("turn_on_if_off", True))

            hsbk = (0, 0, 0, 3500)

            self.globals[K_LIFX][dev_id]["hsbkHue"] = hsbk[0]          # Value between 0 and 65535
            self.globals[K_LIFX][dev_id]["hsbkSaturation"] = hsbk[1]   # Value between 0 and 65535 (e.g. 20% = 13107)
            self.globals[K_LIFX][dev_id]["hsbkBrightness"] = hsbk[2]   # Value between 0 and 65535
            self.globals[K_LIFX][dev_id]["hsbkKelvin"] = hsbk[3]       # Value between 2500 and 9000
            self.globals[K_LIFX][dev_id]["powerLevel"] = 0             # Value between 0 and 65535

            self.globals[K_LIFX][dev_id]["groupLabel"] = self.globals[K_DISCOVERY][dev.address][K_GROUP]
            self.globals[K_LIFX][dev_id]["locationLabel"] = self.globals[K_DISCOVERY][dev.address][K_LOCATION]

            self.globals[K_LIFX][dev_id]["whenLastOnHsbkHue"] = int(0)           # Value between 0 and 65535
            self.globals[K_LIFX][dev_id]["whenLastOnHsbkSaturation"] = int(0)    # Value between 0 and 65535 (e.g. 20% = 13107)
            self.globals[K_LIFX][dev_id]["whenLastOnHsbkBrightness"] = int(0)    # Value between 0 and 65535
            self.globals[K_LIFX][dev_id]["whenLastOnHsbkKelvin"] = int(3500)     # Value between 2500 and 9000
            self.globals[K_LIFX][dev_id]["whenLastOnPowerLevel"] = int(0)        # Value between 0 and 65535

            self.globals[K_LIFX][dev_id]["indigoRed"] = float(0)                 # Value between 0.0 and 100.0
            self.globals[K_LIFX][dev_id]["indigoGreen"] = float(0)               # Value between 0.0 and 100.0
            self.globals[K_LIFX][dev_id]["indigoBlue"] = float(0)                # Value between 0.0 and 100.0

            self.globals[K_LIFX][dev_id]["indigoHue"] = float(0)                 # Value between 0.0 and 360.0
            self.globals[K_LIFX][dev_id]["indigoSaturation"] = float(0)          # Value between 0.0 and 100.0
            self.globals[K_LIFX][dev_id]["indigoBrightness"] = float(0)          # Value between 0.0 and 100.0
            self.globals[K_LIFX][dev_id]["indigoKelvin"] = float(3500)           # Value between 2500 & 9000
            self.globals[K_LIFX][dev_id]["indigoPowerLevel"] = float(0)          # Value between 0.0 and 100.0
            self.globals[K_LIFX][dev_id]["indigoWhiteLevel"] = float(0)          # Value between 0.0 and 100.0

            self.globals[K_LIFX][dev_id]["duration"] = float(1.0)
            if dev.pluginProps.get("overrideDefaultPluginDurations", False):
                self.globals[K_LIFX][dev_id][K_DURATION_DIM_BRIGHTEN] = \
                    float(dev.pluginProps.get("defaultDurationDimBrighten",
                                              self.globals[K_PLUGIN_CONFIG_DEFAULT][K_DURATION_DIM_BRIGHTEN]))
                self.globals[K_LIFX][dev_id][K_DURATION_ON] = \
                    float(dev.pluginProps.get("defaultDurationOn",
                                              self.globals[K_PLUGIN_CONFIG_DEFAULT][K_DURATION_ON]))
                self.globals[K_LIFX][dev_id][K_DURATION_OFF] = \
                    float(dev.pluginProps.get("defaultDurationOff",
                                              self.globals[K_PLUGIN_CONFIG_DEFAULT][K_DURATION_OFF]))
                self.globals[K_LIFX][dev_id][K_DURATION_COLOR_WHITE] = \
                    float(dev.pluginProps.get("defaultDurationColorWhite",
                                              self.globals[K_PLUGIN_CONFIG_DEFAULT][K_DURATION_COLOR_WHITE]))

            else:
                self.globals[K_LIFX][dev_id][K_DURATION_DIM_BRIGHTEN] = \
                    float(self.globals[K_PLUGIN_CONFIG_DEFAULT][K_DURATION_DIM_BRIGHTEN])
                self.globals[K_LIFX][dev_id][K_DURATION_ON] = \
                    float(self.globals[K_PLUGIN_CONFIG_DEFAULT][K_DURATION_ON])
                self.globals[K_LIFX][dev_id][K_DURATION_OFF] = \
                    float(self.globals[K_PLUGIN_CONFIG_DEFAULT][K_DURATION_OFF])
                self.globals[K_LIFX][dev_id][K_DURATION_COLOR_WHITE] = \
                    float(self.globals[K_PLUGIN_CONFIG_DEFAULT][K_DURATION_COLOR_WHITE])

            # variables for holding SETLAMP command values
            self.globals[K_LIFX][dev_id]["lampTarget"] = dict()                # Target states
            self.globals[K_LIFX][dev_id]["lampTarget"]["active"] = False
            self.globals[K_LIFX][dev_id]["lampTarget"]["hue"] = "0.0"          # Value between 0.0 and 65535.0
            self.globals[K_LIFX][dev_id]["lampTarget"]["saturation"] = "0.0"   # Value between 0.0 and 65535.0
            self.globals[K_LIFX][dev_id]["lampTarget"]["kelvin"] = "3500"      # Value between 2500 and 9000
            self.globals[K_LIFX][dev_id]["lampTarget"]["brightness"] = "0"     # Value between 0 and 100
            self.globals[K_LIFX][dev_id]["lampTarget"]["duration"] = "0.0"

            keyValueList = [
                {"key": "lifx_on_state", "value": self.globals[K_LIFX][dev_id]["onState"]},
                {"key": "lifx_on_off_state", "value": self.globals[K_LIFX][dev_id]["onOffState"]},

                {"key": "hsbk_hue", "value": self.globals[K_LIFX][dev_id]["hsbkHue"]},
                {"key": "hsbk_saturation", "value": self.globals[K_LIFX][dev_id]["hsbkSaturation"]},
                {"key": "hsbk_brightness", "value": self.globals[K_LIFX][dev_id]["hsbkBrightness"]},
                {"key": "hsbk_kelvin", "value": self.globals[K_LIFX][dev_id]["hsbkKelvin"]},
                {"key": "power_level", "value": self.globals[K_LIFX][dev_id]["powerLevel"]},

                {"key": "group_label", "value": self.globals[K_LIFX][dev_id]["groupLabel"]},
                {"key": "location_label", "value": self.globals[K_LIFX][dev_id]["locationLabel"]},

                {"key": "when_last_on_hsbk_hue", "value": self.globals[K_LIFX][dev_id]["whenLastOnHsbkHue"]},
                {"key": "when_last_on_hsbk_saturation", "value": self.globals[K_LIFX][dev_id]["whenLastOnHsbkSaturation"]},
                {"key": "when_last_on_hsbk_brightness", "value": self.globals[K_LIFX][dev_id]["whenLastOnHsbkBrightness"]},
                {"key": "when_last_on_hsbk_kelvin", "value": self.globals[K_LIFX][dev_id]["whenLastOnHsbkKelvin"]},
                {"key": "when_last_on_power_level", "value": self.globals[K_LIFX][dev_id]["whenLastOnPowerLevel"]},

                {"key": "indigo_hue", "value": self.globals[K_LIFX][dev_id]["indigoHue"]},
                {"key": "indigo_saturation", "value": self.globals[K_LIFX][dev_id]["indigoSaturation"]},
                {"key": "indigo_brightness", "value": self.globals[K_LIFX][dev_id]["indigoBrightness"]},
                {"key": "indigo_kelvin", "value": self.globals[K_LIFX][dev_id]["indigoKelvin"]},
                {"key": "indigo_power_level", "value": self.globals[K_LIFX][dev_id]["indigoPowerLevel"]},


                {"key": "duration", "value": self.globals[K_LIFX][dev_id]["duration"]},
                {"key": "duration_dim_brighten", "value": self.globals[K_LIFX][dev_id][K_DURATION_DIM_BRIGHTEN]},
                {"key": "duration_on", "value": self.globals[K_LIFX][dev_id][K_DURATION_ON]},
                {"key": "duration_off", "value": self.globals[K_LIFX][dev_id][K_DURATION_OFF]},
                {"key": "duration_color_white", "value": self.globals[K_LIFX][dev_id][K_DURATION_COLOR_WHITE]}]

            props = dev.pluginProps
            if ("SupportsRGB" in props) and props["SupportsRGB"]:
                keyValueList.append({"key": "redLevel", "value": self.globals[K_LIFX][dev_id]["indigoRed"]})
                keyValueList.append({"key": "greenLevel", "value": self.globals[K_LIFX][dev_id]["indigoGreen"]})
                keyValueList.append({"key": "blueLevel", "value": self.globals[K_LIFX][dev_id]["indigoBlue"]})
            if ("SupportsWhiteTemperature" in props) and props["SupportsWhiteTemperature"]:
                keyValueList.append({"key": "whiteTemperature", "value": self.globals[K_LIFX][dev_id]["indigoKelvin"]})
                keyValueList.append({"key": "whiteLevel", "value": self.globals[K_LIFX][dev_id]["indigoBrightness"]})

            dev.updateStatesOnServer(keyValueList, clearErrorState=False)

            self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put([QUEUE_PRIORITY_STATUS_MEDIUM, CMD_STATUS, dev_id, None])

            product_name = self.globals[K_DISCOVERY][dev.address][K_PRODUCT_NAME]
            if product_name[0:5] != "LIFX":
                product_name = f"LIFX {product_name}"
            self.logger.info(f". . . Started '{product_name}' device: '{dev.name}'.")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def deviceStopComm(self, dev):
        try:
            dev_id = dev.id

            if dev_id in self.globals[K_DELETING]:
                self.logger.info(f"Deleting Indigo LIFX device '{dev.name}'")
                del self.globals[K_DELETING][dev_id]
            else:
                self.logger.info(f"Stopping Indigo LIFX device '{dev.name}'")
                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)  # Default to grey circle indicating "offline"
                dev.updateStateOnServer(key="onOffState", value=False, clearErrorState=True)
                dev.updateStateOnServer(key="brightnessLevel", value=0, uiValue="not enabled", clearErrorState=True)
                if dev_id in self.globals[K_LIFX]:
                    self.globals[K_LIFX][dev_id][K_CONNECTED] = False

            # Cancel any existing timers
            if dev_id in self.globals[K_DEVICE_TIMERS]:
                for timer in self.globals[K_DEVICE_TIMERS][dev_id]:
                    self.globals[K_DEVICE_TIMERS][dev_id][timer].cancel()

        except Exception as exception_error:

            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def deviceUpdated(self, orig_dev, new_dev):
        try:
            if orig_dev.deviceTypeId == "lifxDevice" and new_dev.deviceTypeId == "lifxDevice":
                if orig_dev.name != new_dev.name:
                    if bool(new_dev.pluginProps.get("set_lifx_label_from_indigo_device_name", False)):  # Only change LIFX Lamp label if option set
                        self.logger.info(f"Changing LIFX Lamp label from '{orig_dev.name}' to '{new_dev.name}'")
                        self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put([QUEUE_PRIORITY_COMMAND_HIGH, CMD_SET_LABEL, new_dev.id, None])
            indigo.PluginBase.deviceUpdated(self, orig_dev, new_dev)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    # =============================================================================

    def didDeviceCommPropertyChange(self, orig_dev, new_dev):
        """
        Indigo method invoked when a plugin device is changed to check whether
        properties that require a restart have changed. If so, a device start is
        required otherwise a change to other properties won't force a restart

        Properties Requiring Restart:
          ip-address
          Port

        -----
        :param orig_dev:
        :param new_dev:
        :return:
        """

        if new_dev.deviceTypeId != "lifxDevice":
            return False

        try:
            orig_ip_address = orig_dev.pluginProps.get("ip_address", "")
            new_ip_address = new_dev.pluginProps.get("ip_address", "")
            if orig_ip_address != new_ip_address:
                return True

            orig_port = orig_dev.pluginProps.get("port", "")
            new_port = new_dev.pluginProps.get("port", "")
            if orig_port != new_port:
                return True

            return False

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def getActionConfigUiValues(self, pluginProps, type_id, action_id):
        try:
            self.logger.debug(f"getActionConfigUiValues: type_id [{type_id}], action_id [{action_id}], pluginProps[{pluginProps}]")

            error_dict = indigo.Dict()
            values_dict = pluginProps

            if type_id == "setColorWhite":  # <Action id="setColorWhite" deviceFilter="self.lifxDevice">

                values_dict["option"] = "SELECT_OPTION"
                values_dict["optionPresetList"] = "SELECT_PRESET"

                if "actionType" not in values_dict:
                    values_dict["actionType"] = "SELECT_ACTION_TYPE"
                if "turnOnIfOffStandard" not in values_dict:
                    values_dict["turnOnIfOffStandard"] = True
                if "modeStandard" not in values_dict:
                    values_dict["modeStandard"] = "SELECT_COLOR_OR_WHITE"
                if "hueStandard" not in values_dict:
                    values_dict["hueStandard"] = ""
                if "saturationStandard" not in values_dict:
                    values_dict["saturationStandard"] = ""
                if "kelvinStandard" not in values_dict:
                    values_dict["kelvinStandard"] = "NONE"
                if "brightnessStandard" not in values_dict:
                    values_dict["brightnessStandard"] = ""
                if "durationStandard" not in values_dict:
                    values_dict["durationStandard"] = ""
                if "modeWaveform" not in values_dict:
                    values_dict["modeWaveform"] = "SELECT_COLOR_OR_WHITE"
                if "hueWaveform" not in values_dict:
                    values_dict["hueWaveform"] = ""
                if "saturationWaveform" not in values_dict:
                    values_dict["saturationWaveform"] = ""
                if "kelvinWaveform" not in values_dict:
                    values_dict["kelvinWaveform"] = "NONE"
                if "brightnessWaveform" not in values_dict:
                    values_dict["brightnessWaveform"] = ""
                if "transientWaveform" not in values_dict:
                    values_dict["transientWaveform"] = True
                if "periodWaveform" not in values_dict:
                    values_dict["periodWaveform"] = ""
                if "cyclesWaveform" not in values_dict:
                    values_dict["cyclesWaveform"] = ""
                if "dutyCycleWaveform" not in values_dict:
                    values_dict["dutyCycleWaveform"] = "0"  # Equal Time on Both
                if "typeWaveform" not in values_dict:
                    values_dict["typeWaveform"] = "0"  # Saw

                values_dict["selectedPresetOption"] = "NONE"
                values_dict["resultPreset"] = "result_na"
                values_dict["updatePresetList"] = "SELECT_PRESET"
                values_dict = self.actionConfigOptionSelected(values_dict, type_id, action_id)

                if "actionType" in values_dict:
                    if values_dict["actionType"] == "Standard":
                        if "modeStandard" in values_dict:
                            if values_dict["modeStandard"] == "Color":
                                values_dict, error_dict = \
                                    self.hueSaturationBrightnessStandardUpdated(values_dict, type_id, action_id)
                            elif values_dict["modeStandard"] == "White":
                                values_dict, error_dict = self.kelvinStandardUpdated(values_dict, type_id, action_id)
                    elif values_dict["actionType"] == "Waveform":
                        if "modeWaveform" in values_dict:
                            if values_dict["modeWaveform"] == "Color":
                                values_dict, error_dict = \
                                    self.hueSaturationBrightnessWaveformUpdated(values_dict, type_id, action_id)
                            elif values_dict["modeWaveform"] == "White":
                                values_dict, error_dict = self.kelvinWaveformUpdated(values_dict, type_id, action_id)

            return values_dict, error_dict
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def getDeviceConfigUiValues(self, plugin_props, type_id, dev_id):
        try:
            if type_id == 'lifxDevice':
                if "lifx_device_list" not in plugin_props:
                    plugin_props["lifx_device_list"] = "SELECT_AVAILABLE"

                self.logger.debug(f"PROPS 'lifx_device_list' for '{indigo.devices[dev_id].name}' = '{plugin_props['lifx_device_list']}'")

        except Exception as exception_error:

            self.exception_handler(exception_error, True)  # Log error and display failing statement

        finally:
            return super(Plugin, self).getDeviceConfigUiValues(plugin_props, type_id, dev_id)

    def runConcurrentThread(self):
        # This thread is used to detect plugin close down and check for updates
        try:
            self.sleep(5)  # in seconds - Allow startup to complete
            while True:
                self.sleep(300)  # in seconds

        except self.StopThread:
            self.logger.info("Autolog 'LIFX V6 Controller' Plugin shutdown requested")

            self.logger.debug("runConcurrentThread being ended . . .")

            if "lifxlanHandler" in self.globals[K_THREADS]:
                self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put([QUEUE_PRIORITY_STOP_THREAD, CMD_STOP_THREAD, None, None])

            # Cancel any existing timers
            for lifxDevId in self.globals[K_DEVICE_TIMERS]:
                for timer in self.globals[K_DEVICE_TIMERS][lifxDevId]:
                    self.globals[K_DEVICE_TIMERS][lifxDevId][timer].cancel()

            if self.globals[K_POLLING][K_THREAD_ACTIVE]:
                self.globals[K_POLLING][K_FORCE_THREAD_END] = True
                self.globals[K_THREADS][K_POLLING][K_EVENT].set()  # Stop the Polling Thread
                self.globals[K_THREADS][K_POLLING][K_THREAD].join(7.0)  # wait for thread to end
                self.logger.debug("Polling thread now stopped")

            if "lifxlanHandler" in self.globals[K_THREADS]:
                self.globals[K_THREADS][K_LIFXLAN_HANDLER][K_THREAD].join(7.0)  # wait for thread to end
                self.logger.debug("LifxlanHandler thread now stopped")

        self.logger.debug(". . . runConcurrentThread now ended")

    def shutdown(self):
        if self.globals[K_POLLING][K_THREAD_ACTIVE]:
            self.globals[K_POLLING][K_FORCE_THREAD_END] = True
            self.globals[K_THREADS][K_POLLING][K_EVENT].set()  # Stop the Polling Thread

        self.logger.info("'LIFX Controller' Plugin shutdown complete")

    def startup(self):
        try:
            # Create LIFX folder name in variables (for presets) and devices (for lamps)
            folder_name = "LIFX"
            if folder_name not in indigo.variables.folders:
                folder_name = indigo.variables.folder.create(folder_name)
            self.globals[K_FOLDERS][K_VARIABLES_ID] = indigo.variables.folders.getId(folder_name)

            folder_name = "LIFX"
            if folder_name not in indigo.devices.folders:
                folder_name = indigo.devices.folder.create(folder_name)
            self.globals[K_FOLDERS][K_DEVICES_ID] = indigo.devices.folders.getId(folder_name)

            indigo.devices.subscribeToChanges()

            # Create Discovery process queue
            self.globals[K_QUEUES][K_DISCOVERY][K_QUEUE] = queue.PriorityQueue()  # Used to queue discovery commands
            self.globals[K_QUEUES][K_DISCOVERY][K_INITIALISED] = True

            # Create Discovery processing thread
            self.globals[K_THREADS][K_DISCOVERY][K_EVENT] = threading.Event()
            self.globals[K_THREADS][K_DISCOVERY][K_THREAD] = \
                ThreadDiscovery(self.globals, self.globals[K_THREADS][K_DISCOVERY][K_EVENT])
            self.globals[K_THREADS][K_DISCOVERY][K_THREAD].start()

            # Initiate discovery of LIFX devices
            self.globals[K_QUEUES][K_DISCOVERY][K_QUEUE].put([QUEUE_PRIORITY_INIT_DISCOVERY, CMD_DISCOVERY])

            # Create lifxlanHandler process queue
            self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE] = queue.PriorityQueue()  # Used to queue lifxlanHandler commands
            self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_INITIALISED] = True

            # Create lifxlanHandler processing thread
            self.globals[K_THREADS][K_LIFXLAN_HANDLER][K_EVENT] = threading.Event()
            self.globals[K_THREADS][K_LIFXLAN_HANDLER][K_THREAD] = \
                ThreadLifxlanHandler(self.globals, self.globals[K_THREADS][K_LIFXLAN_HANDLER][K_EVENT])
            self.globals[K_THREADS][K_LIFXLAN_HANDLER][K_THREAD].start()

            # Create polling processing thread
            if self.globals[K_POLLING][K_STATUS] and not self.globals[K_POLLING][K_THREAD_ACTIVE]:
                self.globals[K_THREADS][K_POLLING][K_EVENT] = threading.Event()
                self.globals[K_THREADS][K_POLLING][K_THREAD] = \
                    ThreadPolling(self.globals, self.globals[K_THREADS][K_POLLING][K_EVENT])
                self.globals[K_THREADS][K_POLLING][K_THREAD].start()

            self.logger.info("'LIFX Controller' giving Discovery an opportunity to complete . . .")

            for dev in indigo.devices.iter("self"):
                if dev.deviceTypeId == "lifxDevice":
                    dev.updateStateOnServer(key="connected", value=False)
                    dev.updateStateOnServer(key="discovered", value=False)
                    # dev.updateStateOnServer(key="no_ack_state", value=False)
                    dev.updateStateOnServer(key="onOffState", value=False)
                    if dev.enabled:
                        ui_value = "Waiting on discovery ..."
                        dev.updateStateImageOnServer(indigo.kStateImageSel.TimerOn)
                    else:
                        ui_value = "not enabled"
                        dev.updateStateImageOnServer(indigo.kStateImageSel.PowerOff)
                    dev.updateStateOnServer(key="brightnessLevel", value=0, uiValue=ui_value)

            #  Give discovery up to 10 seconds to complete
            second_counter = 0
            while not self.globals[K_INITIAL_DISCOVERY_COMPLETE] and second_counter < 10:
                self.sleep(1)
                second_counter += 1

            self.logger.info(". . . 'LIFX Controller' initialization now completed.")
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def validateActionConfigUi(self, values_dict, type_id, action_id):
        try:
            if type_id == "setColorWhite":
                validateResult = self.validate_action_config_ui_set_color_white(values_dict, type_id, action_id)
            else:
                self.logger.debug(f"validateActionConfigUi called with unknown type_id: type_id=[{type_id}], action_id=[{action_id}]")
                return True, values_dict

            if validateResult[0]:
                return True, validateResult[1]  # True, values_dict
            else:
                return False, validateResult[1], validateResult[2]  # False, values_dict, error_dict
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def validateDeviceConfigUi(self, values_dict, type_id, dev_id):
        try:
            if "ignore_no_ack" in values_dict and dev_id in self.globals[K_LIFX]:
                self.globals[K_LIFX][dev_id][K_IGNORE_NO_ACK] = bool(values_dict.get("ignore_no_ack", False))

            lifx_mac_address = values_dict["mac_address"]
            new_ip_address = values_dict["ip_address"]
            try:
                socket.inet_aton(new_ip_address)
                pass  # Legal
            except Exception as exception_error:
                check_error_message = "illegal IP address string passed to inet_aton"
                exception_error_message = f"{exception_error}"
                self.logger.warning(f"CEM [{len(check_error_message)}: {check_error_message}")  # TODO: What is CEM and SEM ?
                # self.logger.warning(f"SEM[{len(standard_error_message)}: {exception_error_message}")  # TODO: What is this line for?
                if exception_error_message == check_error_message:
                    error_message = f"Update of IP Address to '{new_ip_address}' rejected as IP address is invalid."
                else:
                    error_message = (
                        f"Update LIFX Lamp [{lifx_mac_address}] IP Address to '{new_ip_address}' failed with an error. Line '{sys.exc_traceback.tb_lineno}' has error='{exception_error_message}'")
                error_dict = indigo.Dict()
                error_dict['ip_address'] = error_message
                error_dict['showAlertText'] = error_message
                return False, values_dict, error_dict

            if "override_default_plugin_durations" in values_dict and values_dict["override_default_plugin_durations"]:

                error_dict = indigo.Dict()  # Initialise Error Dictionary

                # Validate "default_duration_dim_brighten" value
                default_duration_dim_brighten = values_dict.get("default_duration_dim_brighten", "1.0").rstrip().lstrip()
                try:
                    if float(default_duration_dim_brighten) <= 0.0:
                        raise ValueError("default_duration_dim_brighten must be greater than zero")
                    values_dict["default_duration_dim_brighten"] = f"{float(f'{float(default_duration_dim_brighten):06.1f}')}"
                except ValueError:
                    error_dict["default_duration_dim_brighten"] = "Default duration for dimming and brightness must be greater than zero"
                    error_dict["showAlertText"] = ("You must enter a valid Default Duration for dimming and brightness value"
                                                   " for the LIFX lamp. It must be greater than zero")
                    return False, values_dict, error_dict

                # Validate "default_duration_on" value
                default_duration_on = values_dict.get("default_duration_on", "1.0").rstrip().lstrip()
                try:
                    if float(default_duration_on) <= 0.0:
                        raise ValueError("Default Duration On must be greater than zero")
                    values_dict["default_duration_on"] = f"{float(f'{float(defaultDurationOn):06.1f}')}"
                except ValueError:
                    error_dict["defaultDurationOn"] = "Default Turn On duration must be greater than zero"
                    error_dict["showAlertText"] = ("You must enter a valid Default Turn On Duration value for the LIFX lamp."
                                                   " It must be greater than zero")
                    return False, values_dict, error_dict

                # Validate "default_duration_off" value
                default_duration_off = values_dict.get("default_duration_off", "1.0").rstrip().lstrip()
                try:
                    if float(default_duration_off) <= 0.0:
                        raise ValueError("Default Duration Off must be greater than zero")
                    values_dict["default_duration_off"] = f"{float(f'{float(defaultDurationOff):06.1f}')}"
                except ValueError:
                    error_dict["default_duration_off"] = "Default Turn Off duration must be greater than zero"
                    error_dict["showAlertText"] = ("You must enter a valid Default Turn Off Duration value for the LIFX lamp."
                                                   " It must be greater than zero")
                    return False, values_dict, error_dict

                # Validate "default_duration_color_white" value
                default_duration_color_white = values_dict.get("default_duration_color_white", "1.0").rstrip().lstrip()
                try:
                    if float(defaultDurationColorWhite) <= 0.0:
                        raise ValueError("Default Duration Color White must be greater than zero")
                    values_dict["default_duration_color_white"] = f"{float(f'{float(default_duration_color_white):06.1f}')}"
                except ValueError:
                    error_dict["default_duration_color_white"] = "Default Set Color/White duration must be greater than zero"
                    error_dict["showAlertText"] = ("You must enter a valid Default Set Color/White Duration value for the LIFX lamp."
                                                   " It must be greater than zero")
                    return False, values_dict, error_dict

            return True, values_dict
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def validatePrefsConfigUi(self, values_dict):
        try:
            if "discoveryMinutes" in values_dict:
                try:
                    if int(values_dict["discoveryMinutes"]) < 1:
                        raise ValueError
                except ValueError:
                    error_dict = indigo.Dict()
                    error_dict["discoveryMinutes"] = "Invalid number Discovery Minutes"
                    error_dict["showAlertText"] = \
                        "The number of minutes between discoveries must be a positive integer e.g 1, 2, 5 etc."
                    return False, values_dict, error_dict

            if "defaultDurationDimBrighten" in values_dict:
                try:
                    float(values_dict["defaultDurationDimBrighten"])
                except ValueError:
                    error_dict = indigo.Dict()
                    error_dict["defaultDurationDimBrighten"] = "Invalid number for seconds"
                    error_dict["showAlertText"] = \
                        "The number of seconds must be specified as an integer or float e.g. 2, 2.0 or 2.5 etc."
                    return False, values_dict, error_dict

            if "defaultDurationDimBrighten" in values_dict:
                try:
                    float(values_dict["defaultDurationDimBrighten"])
                except ValueError:
                    error_dict = indigo.Dict()
                    error_dict["defaultDurationDimBrighten"] = "Invalid number for seconds"
                    error_dict["showAlertText"] = \
                        "The number of seconds must be specified as an integer or float e.g. 2, 2.0 or 2.5 etc."
                    return False, values_dict, error_dict

            if "defaultDurationOn" in values_dict:
                try:
                    float(values_dict["defaultDurationOn"])
                except ValueError:
                    error_dict = indigo.Dict()
                    error_dict["defaultDurationOn"] = "Invalid number for seconds"
                    error_dict["showAlertText"] = \
                        "The number of seconds must be specified as an integer or float e.g. 2, 2.0 or 2.5 etc."
                    return False, values_dict, error_dict

            if "defaultDurationOff" in values_dict:
                try:
                    float(values_dict["defaultDurationOff"])
                except ValueError:
                    error_dict = indigo.Dict()
                    error_dict["defaultDurationOff"] = "Invalid number for seconds"
                    error_dict["showAlertText"] = \
                        "The number of seconds must be specified as an integer or float e.g. 2, 2.0 or 2.5 etc."
                    return False, values_dict, error_dict

            if "defaultDurationColorWhite" in values_dict:
                try:
                    float(values_dict["defaultDurationColorWhite"])
                except ValueError:
                    error_dict = indigo.Dict()
                    error_dict["defaultDurationColorWhite"] = "Invalid number for seconds"
                    error_dict["showAlertText"] = \
                        "The number of seconds must be specified as an integer or float e.g. 2, 2.0 or 2.5 etc."
                    return False, values_dict, error_dict

            return True

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement
            return True

    #################################
    #
    # Start of bespoke plugin methods
    #
    #################################

    def colorPickerUpdated(self, values_dict, type_id, dev_id):
        try:
            if values_dict["actionType"] == "Standard":
                rgbHexList = values_dict["colorStandardColorpicker"].split()

                # Convert color picker values for RGB (x00-xFF100) to colorSys values (0.0-1.0)
                red = float(int(rgbHexList[0], 16) / 255.0)
                green = float(int(rgbHexList[1], 16) / 255.0)
                blue = float(int(rgbHexList[2], 16) / 255.0)

                hsv_hue, hsv_saturation, hsv_brightness = colorsys.rgb_to_hsv(red, green, blue)

                # Convert colorsys values for HSV (0.0-1.0) to H (0-360), S (0.0-100.0) and V aka B (0.0-100.0)
                values_dict["hueStandard"] = f'{int(hsv_hue * 360.0)}'
                values_dict["saturationStandard"] = f'{int(hsv_saturation * 100.0)}'
                values_dict["brightnessStandard"] = f'{int(hsv_brightness * 100.0)}'
            elif values_dict["actionType"] == "Waveform":
                rgbHexList = values_dict["colorWaveformColorpicker"].split()

                # Convert color picker values for RGB (x00-xFF100) to colorSys values (0.0-1.0)
                red = float(int(rgbHexList[0], 16) / 255.0)
                green = float(int(rgbHexList[1], 16) / 255.0)
                blue = float(int(rgbHexList[2], 16) / 255.0)

                hsv_hue, hsv_saturation, hsv_brightness = colorsys.rgb_to_hsv(red, green, blue)

                # Convert colorsys values for HSV (0.0-1.0) to H (0-360), S (0.0-100.0) and V aka B (0.0-100.0)
                values_dict["hueWaveform"] = f'{int(hsv_hue * 360.0)}'
                values_dict["saturationWaveform"] = f'{int(hsv_saturation * 100.0)}'
                values_dict["brightnessWaveform"] = f'{int(hsv_brightness * 100.0)}'

            return values_dict
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def actionConfigApplyLifxOptionValues(self, values_dict, type_id, action_id):
        try:
            self.logger.debug(f"actionConfigPresetApplyOptionValues: type_id[{type_id}], action_id[{action_id}], values_dict:\n{values_dict}")

            if values_dict["actionType"] == "Standard":
                values_dict["modeStandard"] = values_dict["lifxMode"]
                values_dict["brightnessStandard"] = values_dict["lifxBrightness"]
                if values_dict["lifxMode"] == "Color":
                    values_dict["hueStandard"] = values_dict["lifxHue"]
                    values_dict["saturationStandard"] = values_dict["lifxSaturation"]
                    hue = float(values_dict["lifxHue"]) * 65535.0 / 360.0
                    saturation = float(values_dict["lifxSaturation"]) * 65535.0 / 100.0
                    brightness = float(values_dict["lifxBrightness"]) * 65535.0 / 100.0
                    # Convert Color HSBK into RGBW
                    values_dict["colorStandardColorpicker"] = \
                        self.action_config_set_color_swatch_rgb(hue, saturation, brightness)
                    return values_dict
                else:
                    # lifxKelvinStatic is a Kelvin description field e.g. "3200K Neutral Warm"
                    kelvin = float(values_dict["lifxKelvinStatic"][0:4])
                    # Convert White HSBK into RGBW
                    kelvin, kelvinDescription, kelvinRgb = self.action_config_set_kelvin_color_swatch_rgb(kelvin)
                    values_dict["kelvinStandard"] = kelvin
                    values_dict["kelvinStandardColorpicker"] = kelvinRgb
                    return values_dict
            else:
                values_dict["modeWaveform"] = values_dict["lifxMode"]
                values_dict["brightnessWaveform"] = values_dict["lifxBrightness"]
                if values_dict["lifxMode"] == "Color":
                    values_dict["hueWaveform"] = values_dict["lifxHue"]
                    values_dict["saturationWaveform"] = values_dict["lifxSaturation"]
                    hue = float(values_dict["lifxHue"]) * 65535.0 / 360.0
                    saturation = float(values_dict["lifxSaturation"]) * 65535.0 / 100.0
                    brightness = float(values_dict["lifxBrightness"]) * 65535.0 / 100.0
                    # Convert Color HSBK into RGBW
                    values_dict["colorWaveformColorpicker"] = \
                        self.action_config_set_color_swatch_rgb(hue, saturation, brightness)
                    return values_dict
                else:
                    # lifxKelvinStatic is a Kelvin description field e.g. "3200K Neutral Warm"
                    kelvin = float(values_dict["lifxKelvinStatic"][0:4])
                    # Convert White HSBK into RGBW
                    kelvin, kelvinDescription, kelvinRgb = self.action_config_set_kelvin_color_swatch_rgb(kelvin)
                    values_dict["kelvinWaveform"] = kelvin
                    values_dict["kelvin_waveformColorpicker"] = kelvinRgb
                    return values_dict
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def actionConfigApplyStandardPresetOptionValues(self, values_dict, type_id, action_id):
        try:
            self.logger.debug(f"actionConfigApplyStandardPresetOptionValues: type_id[{type_id}], action_id[{action_id}], values_dict:\n{values_dict}")

            error_dict = indigo.Dict()

            values_dict["actionType"] = "Standard"
            if values_dict["presetBrightnessStandard"] != "":
                values_dict["brightnessStandard"] = values_dict["presetBrightnessStandard"]
            if values_dict["presetModeStandard"] == "White":
                values_dict["modeStandard"] = "White"
                if values_dict["presetKelvinStandardStatic"] != "":
                    values_dict["kelvinStandard"] = values_dict["presetKelvinStandardStatic"][0:4]

                values_dict, error_dict = self.kelvinStandardUpdated(values_dict, type_id, action_id)

            elif values_dict["presetModeStandard"] == "Color":
                values_dict["modeStandard"] = "Color"
                if values_dict["presetHueStandard"] != "":
                    values_dict["hueStandard"] = values_dict["presetHueStandard"]
                if values_dict["presetSaturationStandard"] != "":
                    values_dict["saturationStandard"] = values_dict["presetSaturationStandard"]

                values_dict, error_dict = self.hueSaturationBrightnessStandardUpdated(values_dict, type_id, action_id)

                if values_dict["presetDurationStandard"] != "":
                    values_dict["durationStandard"] = values_dict["presetDurationStandard"]

            self.logger.debug(f"actionConfigApplyStandardPresetOptionValues: Returned values_dict:\n{values_dict}")

            return values_dict, error_dict
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def actionConfigApplyWaveformPresetOptionValues(self, values_dict, type_id, action_id):
        try:
            self.logger.debug(f"actionConfigApplyWaveformPresetOptionValues: type_id[{type_id}], action_id[{action_id}], values_dict:\n{values_dict}")

            values_dict["actionType"] = "Waveform"
            if values_dict["presetBrightnessWaveform"] != "":
                values_dict["brightnessWaveform"] = values_dict["presetBrightnessWaveform"]
            if values_dict["presetmode_waveform"] == "White":
                values_dict["modeWaveform"] = "White"
                if values_dict["presetkelvin_waveformStatic"] != "":
                    values_dict["kelvinWaveform"] = values_dict["presetkelvin_waveformStatic"][0:4]

                values_dict, error_dict = self.kelvinWaveformUpdated(values_dict, type_id, action_id)

            if values_dict["presetmode_waveform"] == "Color":
                values_dict["modeWaveform"] = "Color"
                if values_dict["presetHueWaveform"] != "":
                    values_dict["hueWaveform"] = values_dict["presetHueWaveform"]
                if values_dict["presetSaturationWaveform"] != "":
                    values_dict["saturationWaveform"] = values_dict["presetSaturationWaveform"]

                values_dict, error_dict = self.hueSaturationBrightnessWaveformUpdated(values_dict, type_id, action_id)

            if values_dict["presetTransientWaveform"] != "":
                values_dict["transientWaveform"] = values_dict["presetTransientWaveform"]
            if values_dict["presetperiod_waveform"] != "":
                values_dict["periodWaveform"] = values_dict["presetperiod_waveform"]
            if values_dict["presetcycles_waveform"] != "":
                values_dict["cyclesWaveform"] = values_dict["presetcycles_waveform"]
            if values_dict["presetDutyCycleWaveform"] != "":
                values_dict["dutyCycleWaveform"] = values_dict["presetDutyCycleWaveform"]
            if values_dict["presetTypeWaveform"] != "":
                values_dict["typeWaveform"] = values_dict["presetTypeWaveform"]

            self.logger.debug(f"actionConfigApplyWaveformPresetOptionValues: Returned values_dict:\n{values_dict}")

            return values_dict
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def actionConfigLifxDeviceSelected(self, values_dict, type_id, action_id):
        try:
            self.logger.debug(
                f"actionConfigLifxDeviceSelected [lifxLamp]= {str(values_dict['optionLifxDeviceList'])}")

            lifx_lamp_selected = False  # Start with assuming no lamp selected in dialogue
            lifx_dev_id = 0  # To suppress PyCharm warning
            if "optionLifxDeviceList" in values_dict:
                try:
                    lifx_dev_id = int(values_dict["optionLifxDeviceList"])
                    try:
                        for dev in indigo.devices.iter("self"):  # CHECK FILTER FOR LIFX DEVICE ONLY!!!!
                            if dev.id == lifx_dev_id:
                                lifx_lamp_selected = True
                                break
                    except Exception:
                        pass
                except Exception:
                    pass

            if lifx_lamp_selected:
                values_dict["lifxHue"] = str(self.globals[K_LIFX][lifx_dev_id]["indigoHue"])
                values_dict["lifxSaturation"] = str(self.globals[K_LIFX][lifx_dev_id]["indigoSaturation"])
                values_dict["lifxBrightness"] = str(self.globals[K_LIFX][lifx_dev_id]["indigoBrightness"])
                values_dict["lifxKelvin"] = str(self.globals[K_LIFX][lifx_dev_id]["indigoKelvin"])

                hue = self.globals[K_LIFX][lifx_dev_id]["hsbkHue"]
                saturation = self.globals[K_LIFX][lifx_dev_id]["hsbkSaturation"]
                value = self.globals[K_LIFX][lifx_dev_id]["hsbkBrightness"]
                kelvin = self.globals[K_LIFX][lifx_dev_id]["hsbkKelvin"]

                if saturation != 0:
                    values_dict["lifxMode"] = "Color"
                    # Convert Color HSBK into RGBW
                    values_dict["colorLifxColorpicker"] = self.action_config_set_color_swatch_rgb(hue, saturation, value)
                    return values_dict
                else:
                    values_dict["lifxMode"] = "White"
                    # Convert White HSBK into RGBW
                    kelvin, kelvinDescription, kelvinRgb = self.action_config_set_kelvin_color_swatch_rgb(kelvin)
                    values_dict["lifxKelvinStatic"] = str(kelvinDescription)
                    values_dict["kelvinLifxColorpicker"] = kelvinRgb
                    return values_dict

            else:
                values_dict["lifxHue"] = "n/a"
                values_dict["lifxSaturation"] = "n/a"
                values_dict["lifxBrightness"] = "n/a"
                values_dict["lifxKelvin"] = "n/a"
            return values_dict
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def actionConfigListKelvinValues(self, filter="", values_dict=None, type_id="", targetId=0):
        try:
            kelvinArray = [("NONE", "- Select Kelvin value -"), ("CURRENT", "Use current Kelvin value")]
            for kelvin in LIFX_KELVINS:
                kelvinArray.append((str(kelvin), LIFX_KELVINS[kelvin][1]))  # Kelvin value, kelvin description

            def getKelvin(kelvinItem):
                return kelvinItem[1]

            return sorted(kelvinArray, key=getKelvin)
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def actionConfigListLifxDevices(self, filter="", values_dict=None, type_id="", targetId=0):
        try:
            lifxArray = [("NONE", "- Select LIFX Device -")]
            for device in indigo.devices:
                if device.deviceTypeId == "lifxDevice" and device.id != targetId:  # Exclude own device
                    lifxArray.append((device.id, device.name))

            def getLifxDeviceName(lifxDevItem):
                return lifxDevItem[1]

            return sorted(lifxArray, key=getLifxDeviceName)
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def actionConfigOptionSelected(self, values_dict, type_id, action_id):
        try:
            self.logger.debug("actionConfigOptionSelected")

            # Turn Off Save/Update Preset Dialogue
            values_dict["resultPreset"] = "result_na"
            values_dict["newPresetName"] = ""
            values_dict["selected_preset_Option"] = "NONE"

            values_dict["optionLifxDeviceList"] = "NONE"
            values_dict["lifxMode"] = "NONE"
            values_dict["presetSelected"] = "NO"

            return values_dict

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def actionConfigPresetActionSelected(self, values_dict, type_id, action_id):
        try:

            self.logger.debug(f"actionConfigPresetActionSelected: {values_dict}")

            values_dict["resultPreset"] = "result_na"
            values_dict["newPresetName"] = ""

            return values_dict

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def actionConfigPresetSaveButtonPressed(self, values_dict, type_id, action_id):
        try:
            values_dict["resultPreset"] = "result_na"

            self.logger.debug(f"actionConfigPresetSaveButtonPressed: type_id[{type_id}], action_id[{action_id}]")

            validation = self.validateActionConfigUi(values_dict, "applyPreset", action_id)

            self.logger.debug(f"validation: type_id[{type(validation)}], action_id[{validation}]")

            values_dict = validation[1]  # values_dict

            if validation[0]:
                preset = self.build_preset_variable(values_dict)  # Build Preset Variable
                if len(preset) > 0:
                    try:
                        if not re.match(r"\w+$", values_dict["newPresetName"]):
                            raise ValueError("newPresetName must be a alphanumeric or '_'")
                        indigo.variable.create(values_dict["newPresetName"], value=preset,
                                               folder=self.globals[K_FOLDERS][K_VARIABLES_ID])
                        values_dict["resultPreset"] = "result_save_ok"
                    except ValueError:
                        values_dict["resultPreset"] = "result_save_error"
                        error_dict = indigo.Dict()
                        error_dict["newPresetName"] = "Unable to create preset variable"
                        error_dict["showAlertText"] = ("Unable to create preset variable."
                                                       " Check that the preset name format is valid (alphanumeric and underscore only)"
                                                       " and that the preset variable doesn't already exist")
                        return values_dict, error_dict
            else:
                values_dict["resultPreset"] = "result_invalid_value"
                return values_dict, validation[2]

            return values_dict

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def actionConfigPresetSelected(self, values_dict, type_id, action_id):
        try:
            self.logger.debug(f"actionConfigPresetSelected [Preset]= {values_dict['optionPresetList']}")

            values_dict["actionTypePreset"] = "No Preset Selected"
            preset_selected = False  # Start with assuming no preset selected in dialogue
            selected_preset_value = ""
            if "optionPresetList" in values_dict:
                try:
                    variableId = int(values_dict["optionPresetList"])
                    try:
                        if indigo.variables[variableId].folderId == self.globals[K_FOLDERS][K_VARIABLES_ID]:
                            selected_preset_value = indigo.variables[variableId].value
                            preset_selected = True
                    except Exception:
                        pass
                except Exception:
                    pass

            if not preset_selected:
                values_dict["presetSelected"] = "NO"  # Hidden field for controlling fields displayed
            else:
                values_dict["presetSelected"] = "YES"  # Hidden field for controlling fields displayed

                action_type, mode, turn_on_if_off, hue, saturation, \
                    brightness, kelvin, duration, transient, \
                    period, cycles, dutyCycle, waveform = self.decode_preset(selected_preset_value)

                values_dict["actionTypePreset"] = action_type
                if action_type == "Standard":

                    if turn_on_if_off == "0":
                        values_dict["presetTurnOnIfOffStandardStatic"] = "No"
                    else:
                        values_dict["presetTurnOnIfOffStandardStatic"] = "Yes"
                    if brightness != "":
                        values_dict["presetBrightnessStandard"] = brightness
                    else:
                        brightness = "100.0"  # Default to 100% saturation (for Color Swatch)
                    if mode == "White":
                        if kelvin != "":
                            kelvin, kelvinDescription, kelvinRgb = \
                                self.action_config_set_kelvin_color_swatch_rgb(int(kelvin))
                            values_dict["presetKelvinStandardStatic"] = str(kelvinDescription)
                            values_dict["kelvinPresetColorpicker"] = kelvinRgb
                    elif mode == "Color":
                        values_dict["actionTypePreset"] = action_type
                        values_dict["presetModeStandard"] = mode
                        if hue != "":
                            values_dict["presetHueStandard"] = hue
                        else:
                            hue = "360.0"  # Default to Red (for Color Swatch)
                        if saturation != "":
                            values_dict["presetSaturationStandard"] = saturation
                        else:
                            saturation = "100.0"  # Default to 100% saturation (for Color Swatch)
                        hue = float(float(hue) * 65535.0 / 360.0)
                        saturation = float(float(saturation) * 65535.0 / 100.0)
                        brightness = float(float(brightness) * 65535.0 / 100.0)
                        values_dict["colorPresetColorpicker"] = self.action_config_set_color_swatch_rgb(hue, saturation,
                                                                                                        brightness)
                    else:
                        values_dict["presetModeStandard"] = "Preset has invalid mode"
                        return values_dict  # Error: mode must be "White" or "Color"

                    if duration != "":
                        values_dict["presetDurationStandard"] = duration
                    values_dict["presetModeStandard"] = mode
                elif action_type == "Waveform":
                    if brightness != "":
                        values_dict["presetBrightnessWaveform"] = brightness
                    else:
                        brightness = "100.0"  # Default to 100% saturation (for Color Swatch)
                    if mode == "White":
                        if kelvin != "":
                            kelvin, kelvinDescription, kelvinRgb = \
                                self.action_config_set_kelvin_color_swatch_rgb(int(kelvin))
                            values_dict["presetkelvinWaveformStatic"] = str(kelvinDescription)
                            values_dict["kelvinPresetWaveformColorpicker"] = kelvinRgb
                    elif mode == "Color":
                        if hue != "":
                            values_dict["presetHueWaveform"] = hue
                        else:
                            hue = "360.0"  # Default to Red (for Color Swatch)
                        if saturation != "":
                            values_dict["presetSaturationWaveform"] = saturation
                        else:
                            saturation = "100.0"  # Default to 100% saturation (for Color Swatch)
                        hue = float(float(hue) * 65535.0 / 360.0)
                        saturation = float(float(saturation) * 65535.0 / 100.0)
                        brightness = float(float(brightness) * 65535.0 / 100.0)
                        values_dict["colorPresetWaveformColorpicker"] = \
                            self.action_config_set_color_swatch_rgb(hue, saturation, brightness)
                    else:
                        values_dict["presetModeWaveform"] = "Preset has invalid mode"
                        return values_dict  # Error: mode must be "White" or "Color"

                    if transient != "":
                        values_dict["presetTransientWaveform"] = transient
                    if period != "":
                        values_dict["presetPeriodWaveform"] = period
                    if cycles != "":
                        values_dict["presetCyclesWaveform"] = cycles
                    if dutyCycle != "":
                        values_dict["presetDutyCycleWaveform"] = dutyCycle
                    if waveform != "":
                        values_dict["presetTypeWaveform"] = waveform
                    values_dict["presetModeWaveform"] = mode
                else:
                    values_dict["presetModeStandard"] = "Preset has invalid LIFX Action"
                    values_dict["presetModeWaveform"] = "Preset has invalid LIFX Action"
                    values_dict["actionTypePreset"] = "Preset has invalid LIFX Action"

            return values_dict

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def actionConfigPresetUpdateButtonPressed(self, values_dict, type_id, action_id):
        try:
            self.logger.debug(f"actionConfigPresetUpdateButtonPressed: type_id[{type_id}], action_id[{action_id}]")

            values_dict["resultPreset"] = "result_na"

            validation = self.validateActionConfigUi(values_dict, "setPreset", action_id)

            self.logger.debug(f"validation: type_id[{type(validation)}], action_id[{validation}]")

            values_dict = validation[1]  # values_dict

            if validation[0]:
                preset = self.build_preset_variable(values_dict)  # Build Preset Variable
                if len(preset) > 0:
                    try:
                        presetVariableId = int(values_dict["updatePresetList"])
                        presetVariableToUpdate = indigo.variables[presetVariableId]
                        presetVariableToUpdate.value = preset
                        presetVariableToUpdate.replaceOnServer()
                        values_dict["resultPreset"] = "result_update_ok"
                    except Exception:
                        values_dict["resultPreset"] = "result_update_error"
                        error_dict = indigo.Dict()
                        error_dict["updatePresetList"] = "Unable to update preset variable"
                        error_dict["showAlertText"] = "Unable to update preset variable"
                        return values_dict, error_dict
            else:
                self.logger.debug("validation: FALSE")
                values_dict["resultPreset"] = "result_invalid_value"
                return values_dict, validation[2]

            return values_dict

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def action_config_set_kelvin_color_swatch_rgb(self, argKelvin):
        try:
            kelvin = min(LIFX_KELVINS, key=lambda x: abs(x - argKelvin))
            rgb, kelvinDescription = LIFX_KELVINS[kelvin]
            rgbHexVals = []
            for byteLevel in rgb:
                if byteLevel < 0:
                    byteLevel = 0
                elif byteLevel > 255:
                    byteLevel = 255
                rgbHexVals.append("%02X" % byteLevel)  # TODO: Enhance this!
            return kelvin, kelvinDescription, " ".join(rgbHexVals)
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def action_control_universal(self, action, dev):
        try:
            # ##### STATUS REQUEST ######
            if action.deviceAction == indigo.kUniversalAction.RequestStatus:
                self.process_status(action, dev)
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def action_config_set_color_swatch_rgb(self, hue, saturation, value):
        try:
            # hue, saturation and value are integers in the range 0 - 65535
            hue = float(hue) / 65535.0
            value = float(value) / 65535.0
            saturation = float(saturation) / 65535.0

            red, green, blue = colorsys.hsv_to_rgb(hue, saturation, value)

            red = int(round(float(red * 255.0)))
            green = int(round(float(green * 255.0)))
            blue = int(round(float(blue * 255.0)))

            rgb = [red, green, blue]
            rgbHexVals = []
            for byteLevel in rgb:
                if byteLevel < 0:
                    byteLevel = 0
                elif byteLevel > 255:
                    byteLevel = 255
                rgbHexVals.append("%02X" % byteLevel)  # TODO:  Enhance this!
            return " ".join(rgbHexVals)
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def brightenDimByTimer(self, plugin_action, dev):  # Dev is a LIFX Lamp
        try:
            actionProps = plugin_action.props
            option = int(actionProps["optionBrightenDimByTimer"])

            if option == 0:  # Stop brighten / dim
                self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put(
                    [QUEUE_PRIORITY_COMMAND_HIGH, CMD_STOP_BRIGHTEN_DIM_BY_TIMER, dev.id, [option, None, None]])
                self.logger.info(f"sent \"{dev.name}\" stop brighten / dim")
            else:
                if option == 3:  # Start dim / brighten toggle
                    if "lastDimBrightenToggle" in self.globals[K_LIFX][dev.id]:
                        if self.globals[K_LIFX][dev.id]["lastDimBrightenToggle"] == 1:
                            option = 2
                        else:
                            option = 1
                    else:
                        option = 1
                    if int(dev.states["indigoBrightness"]) == 100:
                        option = 2

                    self.globals[K_LIFX][dev.id]["lastDimBrightenToggle"] = option
                    self.logger.info(f"lastDimBrightenToggle for \"{dev.name}\" = {self.globals[K_LIFX][dev.id]['lastDimBrightenToggle']}")

                if option == 1:  # Start brighten
                    amountToBrightenDimBy = int(actionProps["amountToBrightenBy"])
                    command = CMD_BRIGHTEN_BY_TIMER
                    brightenDimUi = "Brightening"
                    self.globals[K_LIFX][dev.id]["lastDimBrightenToggle"] = option
                    timerInterval = float(actionProps["brightenTimerInterval"])
                else:  # option == 2:  # Start dim
                    amountToBrightenDimBy = int(actionProps["amountToDimBy"])
                    command = CMD_DIM_BY_TIMER
                    brightenDimUi = "Dimming"
                    self.globals[K_LIFX][dev.id]["lastDimBrightenToggle"] = option
                    timerInterval = float(actionProps["dimTimerInterval"])
                self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put(
                    [QUEUE_PRIORITY_COMMAND_HIGH, command, dev.id, [option, amountToBrightenDimBy, timerInterval]])
                self.logger.info(
                    f"sent \"{dev.name}\" {brightenDimUi} by {amountToBrightenDimBy} every {timerInterval} second(s)")
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def build_available_lifx_devices_list(self, filter="", values_dict=None, type_id="", target_id=0):
        try:
            self.logger.debug(f"'build_available_lifx_devices_list': TARGET ID = '{target_id}'")

            available_dict = [("SELECT_AVAILABLE", "- Select LIFX device -")]

            for lifx_mac_address in self.globals[K_DISCOVERY].keys():  # self.globals['discovery']['discoveredDevices']
                if (self.globals[K_DISCOVERY][lifx_mac_address][K_INDIGO_DEVICE_ID] == 0 or
                        self.globals[K_DISCOVERY][lifx_mac_address][K_INDIGO_DEVICE_ID] == target_id):
                    lifx_ui = (f"{self.globals[K_DISCOVERY][lifx_mac_address][K_LABEL]}  [{lifx_mac_address} / {self.globals[K_DISCOVERY][lifx_mac_address][K_IP_ADDRESS]}]")
                    lifx_available = (lifx_mac_address, lifx_ui)
                    available_dict.append(lifx_available)

            if len(available_dict) == 1:
                available_dict = [("SELECT_AVAILABLE", "- No unassigned LIFX devices available -")]

            myArray = available_dict

            return sorted(myArray, key=lambda lifx_name: lifx_name[1].lower())  # sort by LIFX name

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def build_preset_variable(self, values_dict):
        try:
            preset = ""

            if values_dict["actionType"] == "Standard":
                if bool(values_dict["turnOnIfOffStandard"]):
                    turn_on_if_off_standard = "1"
                else:
                    turn_on_if_off_standard = "0"
                preset = preset + ",ON=" + turn_on_if_off_standard
                if values_dict["modeStandard"] == "White":
                    if values_dict["kelvinStandard"].rstrip() != "":
                        preset = preset + ",K=" + values_dict["kelvinStandard"].rstrip()
                elif values_dict["modeStandard"] == "Color":
                    if values_dict["hueStandard"].rstrip() != "":
                        preset = preset + ",H=" + values_dict["hueStandard"].rstrip()
                    if values_dict["saturationStandard"].rstrip() != "":
                        preset = preset + ",S=" + values_dict["saturationStandard"].rstrip()
                if values_dict["brightnessStandard"].rstrip() != "":
                    preset = preset + ",B=" + values_dict["brightnessStandard"].rstrip()
            elif values_dict["actionType"] == "Waveform":
                if values_dict["modeWaveform"] == "White":
                    if values_dict["kelvinWaveform"].rstrip() != "":
                        preset = preset + ",K=" + values_dict["kelvinWaveform"].rstrip()
                elif values_dict["modeWaveform"] == "Color":
                    if values_dict["hueWaveform"].rstrip() != "":
                        preset = preset + ",H=" + values_dict["hueWaveform"].rstrip()
                    if values_dict["saturationWaveform"].rstrip() != "":
                        preset = preset + ",S=" + values_dict["saturationWaveform"].rstrip()
                if values_dict["brightnessWaveform"].rstrip() != "":
                    preset = preset + ",B=" + values_dict["brightnessWaveform"].rstrip()
                transient_waveform = "1" if bool(values_dict["transientWaveform"]) else "0"
                preset = preset + ",T=" + transient_waveform
                if values_dict["periodWaveform"].rstrip() != "":
                    preset = preset + ",P=" + values_dict["periodWaveform"].rstrip()
                if values_dict["cyclesWaveform"].rstrip() != "":
                    preset = preset + ",C=" + values_dict["cyclesWaveform"].rstrip()
                if values_dict["dutyCycleWaveform"].rstrip() != "":
                    preset = preset + ",DC=" + values_dict["dutyCycleWaveform"].rstrip()
                if values_dict["typeWaveform"].rstrip() != "":
                    preset = preset + ",W=" + values_dict["typeWaveform"].rstrip()

            if len(preset) > 0:
                if values_dict["actionType"] == "Waveform":
                    prefix = "AT=W,M=W," if values_dict["modeWaveform"] == "White" else "AT=W,M=C,"
                else:
                    prefix = "AT=S,M=W," if values_dict["modeStandard"] == "White" else "AT=S,M=C,"
                preset = prefix + preset[1:]  # Remove leading "," from preset

            return preset
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def decode_preset(self, preset):
        try:
            action_type = ""
            turn_on_if_off = ""
            mode = ""
            hue = ""
            saturation = ""
            brightness = ""
            kelvin = ""
            duration = ""
            transient = ""
            period = ""
            cycles = ""
            dutyCycle = ""
            waveform = ""

            presetItems = preset.split(",")
            self.logger.debug(f"LIFX validatePreset-A [{presetItems}]")

            for presetItem in presetItems:
                self.logger.debug(f"LIFX validatePreset-B [{presetItem}]")

                presetElement, presetValue = presetItem.split("=")
                if presetElement == "AT":
                    if presetValue == "S":
                        action_type = "Standard"
                    elif presetValue == "W":
                        action_type = "Waveform"
                    else:
                        action_type = "Preset Invalid LIFX Action Type (AT) in PRESET"
                if presetElement == "M":
                    if presetValue == "W":
                        mode = "White"
                    elif presetValue == "C":
                        mode = "Color"
                    else:
                        mode = "Preset Invalid LIFX Color/White Mode (M) in PRESET"
                if presetElement == "ON":
                    turn_on_if_off = str(presetValue)
                elif presetElement == "H":
                    hue = str(presetValue)
                elif presetElement == "S":
                    saturation = str(presetValue)
                elif presetElement == "B":
                    brightness = str(presetValue)
                elif presetElement == "K":
                    kelvin = str(presetValue)
                elif presetElement == "D":
                    duration = str(presetValue)
                elif presetElement == "T":
                    transient = str(presetValue)
                elif presetElement == "P":
                    period = str(presetValue)
                elif presetElement == "C":
                    cycles = str(presetValue)
                elif presetElement == "DC":
                    dutyCycle = str(presetValue)
                elif presetElement == "W":
                    waveform = str(presetValue)

            # handle presets from previous versions

            if (action_type == "") and (mode == ""):  # Might be from previous version of plugin?
                # check for waveform
                if (transient == "False") or (transient == "True"):
                    # Is an old style Waveform preset, so adjust accordingly
                    if transient == "False":
                        transient = "0"
                    else:
                        transient = "1"
                    action_type = "Waveform"
                    if kelvin != "":
                        mode = "White"
                    else:
                        mode = "Color"
                        if saturation == "":
                            saturation = "100"
                else:
                    # Is probably old style Standard preset, so adjust accordingly
                    action_type = "Standard"
                    if kelvin != "":
                        mode = "White"
                    else:
                        mode = "Color"
                        if saturation == "":
                            saturation = "100"
            # Now check that turn_on_if_off, if not default to "1" = True
            if action_type == "Standard":
                if turn_on_if_off == "":
                    turn_on_if_off = "1"

            self.logger.debug(
                f"LIFX Preset: Action Type={action_type}, Mode={mode}, ON={turn_on_if_off}, H={hue}, K={kelvin}, B={brightness}, D={duration}, T={transient}, P={period}, C={cycles}, DC={dutyCycle}, W={waveform}")

            return action_type, mode, turn_on_if_off, hue, saturation, brightness, kelvin, duration, \
                transient, period, cycles, dutyCycle, waveform

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def devices_lifx_devices_list(self, filter, values_dict, type_id, ahbDevId):
        try:
            self.logger.debug(f"devices_lifx_devices_list called with filter: {filter}  type_id: {type_id}  Hue Hub: {str(ahbDevId)}")

            deviceList = list()
            for dev in indigo.devices:
                if dev.deviceTypeId == LIFX_DEVICE_TYPEID:
                    deviceList.append((dev.id, dev.name))
            if len(deviceList) == 0:
                deviceList = list((0, "NO LIFX DEVICES DETECTED"))
            return deviceList
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def device_supports_infrared(self, dev, action_request):
        try:
            # Check device is present
            if dev is None:
                self.logger.info(f"No LIFX device selected in Action - request to {action_request} infrared ignored")
                return False
            # Check whether LIFX device supports infrared: True = Yes, False = No
            props = dev.pluginProps
            if ("supports_infrared" not in props) or (not props["supports_infrared"]):
                self.logger.info(
                    f"LIFX device '{dev.name}' does not support infrared - request to {dev.name} infrared ignored")
                return False
            return True
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def hueSaturationBrightnessStandardUpdated(self, values_dict, type_id, devId):
        try:
            error_dict = indigo.Dict()

            if values_dict["modeStandard"] == "White":  # skip processing all fields if mode is "White"
                return values_dict, error_dict

            # Default color Swatch to black i.e. off / unset
            values_dict["colorStandardColorpicker"] = self.action_config_set_color_swatch_rgb(0.0, 65535.0, 0.0)

            brightness_standard = values_dict["brightnessStandard"].rstrip().lstrip()
            if brightness_standard == "" or brightness_standard == "-":
                brightness = self.globals[K_LIFX][devId]["hsbkBrightness"]
            else:
                try:
                    brightness_standard = float(f"{float(brightness_standard):06.1f}")
                    if float(brightness_standard) < 0.0 or float(brightness_standard) > 100.0:
                        raise ValueError("Brightness must be set between 0.0 and 100.0 (inclusive)")
                    brightness = float(float(brightness_standard) * 65535.0 / 100.0)
                except ValueError:
                    error_dict = indigo.Dict()
                    error_dict["brightnessStandard"] = ("Brightness must be set between 0.0 and 100.0 (inclusive)"
                                                        " or '-' (dash) to not set value")
                    error_dict["showAlertText"] = ("You must enter a valid Brightness value for the LIFX device."
                                                   " It must be a value between 0.0 and 100.0 (inclusive)"
                                                   " or "-" (dash) to leave an existing value unchanged")
                    return values_dict, error_dict

            hue_standard = values_dict["hueStandard"].rstrip().lstrip()
            if hue_standard == "" or hue_standard == "-":
                hue = self.globals[K_LIFX][devId]["hsbkHue"]
            else:
                try:
                    hue_standard = float(f"{float(hue_standard):06.1f}")
                    if float(hue_standard) < 0.0 or float(hue_standard) > 360.0:
                        raise ValueError("Hue must be set between 0.0 and 360.0 (inclusive)")
                    hue = float(float(hue_standard) * 65535.0 / 360.0)
                except ValueError:
                    error_dict = indigo.Dict()
                    error_dict["hueStandard"] = "Hue must be set between 0.0 and 360.0 (inclusive) or "-" (dash) to not set value"
                    error_dict["showAlertText"] = ("You must enter a valid Hue value for the LIFX device."
                                                   " It must be a value between 0.0 and 360.0 (inclusive)"
                                                   " or "-" (dash) to leave an existing value unchanged")
                    return values_dict, error_dict

            saturation_standard = values_dict["saturationStandard"].rstrip().lstrip()
            if saturation_standard == "" or saturation_standard == "-":
                saturation = self.globals[K_LIFX][devId]["hsbkSaturation"]
            else:
                try:
                    saturation_standard = float(f"{float(saturation_standard):06.1f}")
                    if float(saturation_standard) < 0.0 or float(saturation_standard) > 100.0:
                        raise ValueError("Saturation must be set between 0.0 and 100.0 (inclusive)")
                    saturation = float(float(saturation_standard) * 65535.0 / 100.0)
                except ValueError:
                    error_dict = indigo.Dict()
                    error_dict["saturationStandard"] = ("Saturation must be set between 0.0 and 100.0 (inclusive)"
                                                        " or "-" (dash) to not set value")
                    error_dict["showAlertText"] = ("You must enter a valid Saturation value for the LIFX device."
                                                   " It must be a value between 0.0 and 100.0 (inclusive)"
                                                   " or "-" (dash) to leave an existing value unchanged")
                    return values_dict, error_dict

            values_dict["colorStandardColorpicker"] = self.action_config_set_color_swatch_rgb(hue, saturation, brightness)
            return values_dict, error_dict
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def hueSaturationBrightnessWaveformUpdated(self, values_dict, type_id, devId):
        try:
            error_dict = indigo.Dict()

            if values_dict["modeWaveform"] == "White":  # skip processing all fields if mode is "White"
                return values_dict

            # Default color Swatch to black i.e. off / unset
            values_dict["colorWaveformColorpicker"] = self.action_config_set_color_swatch_rgb(0.0, 65535.0, 0.0)

            brightness_waveform = values_dict["brightnessWaveform"].rstrip().lstrip()
            if brightness_waveform == "" or brightness_waveform == "-":
                brightness = self.globals[K_LIFX][devId]["hsbkBrightness"]
            else:
                try:
                    brightness_waveform = float(f"{float(brightness_waveform):06.1f}")
                    if float(brightness_waveform) < 0.0 or float(brightness_waveform) > 100.0:
                        raise ValueError("Brightness must be set between 0.0 and 100.0 (inclusive)")
                    brightness = float(float(brightness_waveform) * 65535.0 / 100.0)
                except ValueError:
                    error_dict = indigo.Dict()
                    error_dict["brightnessWaveform"] = ("Brightness must be set between 0.0 and 100.0 (inclusive)"
                                                        " or "-" (dash) to not set value")
                    error_dict["showAlertText"] = ("You must enter a valid Brightness value for the LIFX device."
                                                   " It must be a value between 0.0 and 100.0 (inclusive)"
                                                   " or "-" (dash) to leave an existing value unchanged")
                    return values_dict, error_dict

            hue_waveform = values_dict["hueWaveform"].rstrip().lstrip()
            if hue_waveform == "" or hue_waveform == "-":
                hue = self.globals[K_LIFX][devId]["hsbkHue"]
            else:
                try:
                    hue_waveform = float(f"{float(hue_waveform):06.1f}")
                    if float(hue_waveform) < 0.0 or float(hue_waveform) > 360.0:
                        raise ValueError("Hue must be set between 0.0 and 360.0 (inclusive)")
                    hue = float(float(hue_waveform) * 65535.0 / 360.0)
                except ValueError:
                    error_dict = indigo.Dict()
                    error_dict["hueWaveform"] = "Hue must be set between 0.0 and 360.0 (inclusive) or "-" (dash) to not set value"
                    error_dict["showAlertText"] = ("You must enter a valid Hue value for the LIFX device."
                                                   " It must be a value between 0.0 and 360.0 (inclusive)"
                                                   " or "-" (dash) to leave an existing value unchanged")
                    return values_dict, error_dict

            saturation_waveform = values_dict["saturationWaveform"].rstrip().lstrip()
            if saturation_waveform == "" or saturation_waveform == "-":
                saturation = self.globals[K_LIFX][devId]["hsbkSaturation"]
            else:
                try:
                    saturation_waveform = float(f"{float(saturation_waveform):06.1f}")
                    if float(saturation_waveform) < 0.0 or float(saturation_waveform) > 100.0:
                        raise ValueError("Saturation must be set between 0.0 and 100.0 (inclusive)")
                    saturation = float(float(saturation_waveform) * 65535.0 / 100.0)
                except ValueError:
                    error_dict = indigo.Dict()
                    error_dict["saturationWaveform"] = ("Saturation must be set between 0.0 and 100.0 (inclusive)"
                                                        " or "-" (dash) to not set value")
                    error_dict["showAlertText"] = ("You must enter a valid Saturation value for the LIFX device."
                                                   " It must be a value between 0.0 and 100.0 (inclusive)"
                                                   " or "-" (dash) to leave an existing value unchanged")
                    return values_dict, error_dict

            values_dict["colorWaveformColorpicker"] = self.action_config_set_color_swatch_rgb(hue, saturation, brightness)
            return values_dict, error_dict
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def kelvinStandardUpdated(self, values_dict, type_id, devId):
        try:
            error_dict = indigo.Dict()

            try:
                if values_dict["kelvinStandard"] == "CURRENT":
                    kelvin = self.globals[K_LIFX][devId]["hsbkKelvin"]
                else:
                    kelvin = int(values_dict["kelvinStandard"])
            except Exception:
                error_dict = indigo.Dict()
                error_dict["kelvinStandard"] = "Kelvin must be set between 2500 and 9000 (inclusive)"
                error_dict["showAlertText"] = "You must enter a valid Kelvin value for the LIFX device." \
                                              " It must be an integer between 2500 and 9000 (inclusive)"
                return values_dict, error_dict

            kelvin, kelvinDescription, kelvinRgb = self.action_config_set_kelvin_color_swatch_rgb(kelvin)
            values_dict["kelvinStandardColorpicker"] = kelvinRgb
            return values_dict, error_dict
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def kelvinWaveformUpdated(self, values_dict, type_id, devId):
        try:
            error_dict = indigo.Dict()

            try:
                if values_dict["kelvinWaveform"] == "CURRENT":
                    kelvin = self.globals[K_LIFX][devId]["hsbkKelvin"]
                else:
                    kelvin = int(values_dict["kelvinWaveform"])
            except Exception:
                error_dict = indigo.Dict()
                error_dict["kelvinWaveform"] = "Kelvin must be set between 2500 and 9000 (inclusive)"
                error_dict["showAlertText"] = "You must enter a valid Kelvin value for the LIFX device." \
                                              " It must be an integer between 2500 and 9000 (inclusive)"
                return values_dict, error_dict

            kelvin, kelvinDescription, kelvinRgb = self.action_config_set_kelvin_color_swatch_rgb(kelvin)
            values_dict["kelvin_waveformColorpicker"] = kelvinRgb
            return values_dict, error_dict
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def lifx_available_device_selected(self, values_dict, type_id, dev_id):
        try:
            self.logger.debug(f"'lifx_available_device_selected': typeId[{type_id}], devId[{dev_id}], valuesDict = {values_dict}")

            if values_dict['lifx_device_list'] != 'SELECT_AVAILABLE':
                lifx_mac_address = values_dict['lifx_device_list']
                values_dict['lifx_label'] = self.globals[K_DISCOVERY][lifx_mac_address][K_LABEL]
                values_dict['mac_address'] = lifx_mac_address
                values_dict['ip_address'] = self.globals[K_DISCOVERY][lifx_mac_address][K_IP_ADDRESS]

            return values_dict

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def modeStandardUpdated(self, values_dict, type_id, action_id):
        try:
            if values_dict["modeStandard"] == "White":
                values_dict, error_dict = self.kelvinStandardUpdated(values_dict, type_id, action_id)
            else:
                values_dict, error_dict = self.hueSaturationBrightnessStandardUpdated(values_dict, type_id, action_id)
            return values_dict, error_dict

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def modeWaveformUpdated(self, values_dict, type_id, action_id):
        try:
            if values_dict["modeWaveform"] == "White":
                values_dict, error_dict = self.kelvinWaveformUpdated(values_dict, type_id, action_id)
            else:
                values_dict, error_dict = self.hueSaturationBrightnessWaveformUpdated(values_dict, type_id, action_id)
            return values_dict

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def opened_action_config_ui(self, values_dict, type_id, action_id):
        try:
            self.logger.debug("opened_action_config_ui intercepted")

            return values_dict
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def process_brightness_set(self, plugin_action, dev, newBrightness):  # Dev is a LIFX Lamp
        try:
            duration = self.globals[K_LIFX][dev.id][K_DURATION_DIM_BRIGHTEN]
            if newBrightness > 0:
                if newBrightness > dev.brightness:
                    actionUi = "brighten"
                else:
                    actionUi = "dim"
                self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put(
                    [QUEUE_PRIORITY_COMMAND_HIGH, CMD_BRIGHTNESS, dev.id, [newBrightness]])
                self.logger.info(
                    f"sent \"{dev.name}\" {actionUi} to {newBrightness} with duration of {duration} seconds")
            else:
                self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put([QUEUE_PRIORITY_COMMAND_HIGH, CMD_OFF, dev.id, None])
                self.logger.info(f"sent \"{dev.name}\" {'dim to off'} with duration of {duration} seconds")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processDiscoverDevices(self, plugin_action):
        try:
            self.globals[K_QUEUES][K_DISCOVERY][K_QUEUE].put([QUEUE_PRIORITY_INIT_DISCOVERY, CMD_DISCOVERY])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processPresetApply(self, plugin_action, dev):  # Dev is a LIFX Device
        try:
            preset = indigo.variables[int(plugin_action.props.get("PresetId"))]

            if not dev.states["connected"] or not self.globals[K_LIFX][dev.id][K_CONNECTED]:
                self.logger.info(
                    f"Unable to apply Preset \"{preset.name}\" to \"{dev.name}\" as device not connected")
                return

            self.logger.debug(f"LIFX PLUGIN - process_preset_apply [{plugin_action.props.get('PresetId')}]: {preset.value}")

            action_type, mode, turn_on_if_off, hue, saturation, brightness, kelvin, duration, \
                transient, period, cycles, dutyCycle, typeWaveform = self.decode_preset(preset.value)

            if action_type == "Standard":
                if mode == "White":
                    if kelvin == "":
                        kelvin = "-"
                    saturation = "0"
                elif mode == "Color":
                    if hue == "":
                        hue = "-"
                    if saturation == "":
                        saturation = "-"
                else:
                    self.logger.error(
                        f"LIFX Preset {preset.name} for {dev.name} hasn't been applied. {mode}")
                    return
                if brightness == "":
                    brightness = "-"
                if saturation == "":
                    saturation = "-"
                if duration == "":
                    duration = "-"
                if plugin_action.props.get("PresetDuration").rstrip() != "":
                    try:
                        duration = str(int(plugin_action.props.get("PresetDuration")))
                    except Exception:
                        self.logger.error(f"LIFX Preset {preset.name} for {dev.name} hasn't been applied. Duration[D] specified in preset is invalid: {duration}")
                        return

                if turn_on_if_off != "0" and turn_on_if_off != "1":
                    self.logger.error(f"LIFX Preset {preset.name} for {dev.name} hasn't been applied. Turn-On-If-Off[ON] specified in preset is invalid: {turn_on_if_off}")
                    return

                turn_on_if_off = False if (turn_on_if_off == "0") else True

                self.logger.debug(
                    f"LIFX PRESET QUEUE_PRIORITY_COMMAND_HIGH [STANDARD]; Target for {dev.name}: T_O_I_F={turn_on_if_off}, Mode={mode}, Hue={hue}, Saturation={saturation}, Brightness={brightness}, Kelvin={kelvin}, Duration={duration}")

                self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put([QUEUE_PRIORITY_COMMAND_HIGH, CMD_STANDARD, dev.id,
                                                                       [turn_on_if_off, mode, hue, saturation, brightness, kelvin,
                                                                        duration]])

                if mode == "White":
                    if kelvin == "-":
                        kelvinUi = "existing"
                    else:
                        kelvinUi = f'{int(float(kelvin))}'
                    if brightness == "-":
                        brightnessUi = "existing"
                    else:
                        brightnessUi = f'{int(float(brightness))}'
                    if duration == "-":
                        durationUi = "default"
                    else:
                        durationUi = str(duration)
                    self.logger.info(f"sent \"{dev.name}\" preset of set White Level to \"{int(brightnessUi)}\" and White Temperature to \"{int(kelvinUi)}\" with duration of {durationUi} seconds")
                else:
                    if hue == "-":
                        hueUi = "existing"
                    else:
                        hueUi = f'{int(float(hue))}'
                    if saturation == "-":
                        saturationUi = "existing"
                    else:
                        saturationUi = f'{int(float(saturation))}'
                    if brightness == "-":
                        brightnessUi = "existing"
                    else:
                        brightnessUi = f'{int(float(brightness))}'
                    if duration == "-":
                        durationUi = "default"
                    else:
                        durationUi = str(duration)

                    self.logger.info(f"sent \"{dev.name}\" set Color Level to hue \"{hueUi}\", saturation \"{saturationUi}\" and brightness \"{brightnessUi}\" with duration of {durationUi} seconds")

            elif action_type == "Waveform":
                if mode == "White":
                    valid = True
                    if kelvin == "":
                        valid = False
                    else:
                        try:
                            int(kelvin)
                        except ValueError:
                            valid = False
                    if not valid:
                        self.logger.error(f"LIFX Preset {preset.name} for {dev.name} hasn't been applied. Kelvin[K] value specified in preset is invalid: {kelvin}")
                        return
                elif mode == "Color":
                    valid = True
                    if hue == "":
                        valid = False
                    else:
                        try:
                            float(hue)
                        except ValueError:
                            valid = False
                    if not valid:
                        self.logger.error(f"LIFX Preset {preset.name} for {dev.name} hasn't been applied. Hue[H] value specified in preset is invalid: {hue}")
                        return
                    if saturation == "":
                        valid = False
                    else:
                        try:
                            float(saturation)
                        except ValueError:
                            valid = False
                    if not valid:
                        self.logger.error(f"LIFX Preset {preset.name} for {dev.name} hasn't been applied. Saturation[S] value specified in preset is invalid: {saturation}")
                        return
                else:
                    self.logger.error(
                        f"LIFX Preset {preset.name} for {dev.name} hasn't been applied. {mode}")
                    return

                valid = True
                if brightness == "":
                    valid = False
                else:
                    try:
                        float(brightness)
                    except ValueError:
                        valid = False
                if not valid:
                    self.logger.error(f"LIFX Preset {preset.name} for {dev.name} hasn't been applied. Brightness[B] value specified is preset is invalid: {brightness}")
                    return

                if transient != "0" and transient != "1":
                    self.logger.error(f"LIFX Preset {preset.name} for {dev.name} hasn't been applied. Transient[T] value specified in preset is invalid: {transient}")
                    return

                valid = True
                if period == "":
                    valid = False
                else:
                    try:
                        float(period)
                    except ValueError:
                        valid = False
                if not valid:
                    self.logger.error(f"LIFX Preset {preset.name} for {dev.name} hasn't been applied. Period[P] value specified in preset is invalid: {period}")
                    return

                valid = True
                if cycles == "":
                    valid = False
                else:
                    try:
                        int(cycles)
                    except ValueError:
                        valid = False
                if not valid:
                    self.logger.error(f"LIFX Preset {preset.name} for {dev.name} hasn't been applied. cycles[H] value specified in preset is invalid: {cycles}")
                    return

                valid = True
                if dutyCycle == "":
                    valid = False
                else:
                    try:
                        int(dutyCycle)
                    except ValueError:
                        valid = False
                if not valid:
                    self.logger.error(f"LIFX Preset {preset.name} for {dev.name} hasn't been applied. Duty Cycle[DC] value specified is preset is invalid: {dutyCycle}")
                    return

                if typeWaveform not in ("0", "1", "2", "3", "4"):
                    self.logger.error(f"LIFX Preset {preset.name} for {dev.name} hasn't been applied. Waveform[W] value specified in preset is invalid: {typeWaveform}")
                    return

                self.logger.debug(
                    f"LIFX PRESET QUEUE_PRIORITY_COMMAND_HIGH [WAVEFORM]; Target for {dev.name}: Mode={mode}, Hue={hue}, Saturation={saturation}, Brightness={brightness}, Kelvin={kelvin}, Transient={transient}, Period={period}, Cycles={cycles}, Duty Cycle={dutyCycle}, Waveform={typeWaveform}")

                self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put([QUEUE_PRIORITY_WAVEFORM, CMD_WAVEFORM, dev.id,
                                                                       [mode, hue, saturation, brightness, kelvin, transient, period,
                                                                        cycles, dutyCycle, typeWaveform]])

                transientUi = " Color will be returned to original." if transient else ""
                periodUi = f'{int(period)}'
                cyclesUi = f'{int(cycles)}'
                if int(dutyCycle) == 0:
                    dutyCycleUi = "an equal amount of time is spent on the original color and the new color"
                elif int(dutyCycle) > 0:
                    dutyCycleUi = "more time is spent on the original color"
                else:
                    dutyCycleUi = "more time is spent on the new color"
                typeWaveformUi = LIFX_WAVEFORMS.get(typeWaveform, "0")

                brightnessUi = f'{int(float(brightness))}'

                if mode == "White":
                    kelvinUi = f'{int(float(kelvin))}'
                    self.logger.info(f"sent \"{dev.name}\" waveform \"{typeWaveformUi}\" with White Level to \"{int(brightnessUi)}\" and White Temperature to \"{int(kelvinUi)}\" ...")
                else:
                    hueUi = f'{int(float(hue))}'
                    saturationUi = f'{int(float(saturation))}'
                    self.logger.info(f"sent \"{dev.name}\" preset of waveform \"{typeWaveformUi}\" with hue \"{hueUi}\", saturation \"{saturationUi}\" and brightness \"{brightnessUi}\" ...")
                self.logger.info(f"  ... period is \"{periodUi}\" milliseconds for \"{cyclesUi}\" cycles and {dutyCycleUi}.{transientUi}")

            else:
                self.logger.error(f"LIFX Preset [{dev.name}] hasn't been applied. Action-Type[AT] specified in preset is invalid")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processPresetApplyDefineGenerator(self, filter="", values_dict=None, type_id="", targetId=0):
        try:
            preset_dict = list()
            preset_dict.append(("SELECT_PRESET", "- Select Preset -"))

            for preset in indigo.variables.iter():
                if preset.folderId == self.globals[K_FOLDERS][K_VARIABLES_ID]:
                    preset_found = (str(preset.id), str(preset.name))
                    preset_dict.append(preset_found)

            myArray = preset_dict
            return myArray

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def process_set_color_levels(self, action, dev):
        try:
            self.logger.debug(f"processSetColorLevels ACTION:\n{action} ")

            duration = str(self.globals[K_LIFX][dev.id][K_DURATION_COLOR_WHITE])

            # Determine Color / White Mode
            colorMode = False

            # First check if color is being set by the action Set RGBW levels
            if "redLevel" in action.actionValue and \
                    "greenLevel" in action.actionValue and \
                    "blueLevel" in action.actionValue:
                if float(action.actionValue["redLevel"]) > 0.0 or \
                        float(action.actionValue["greenLevel"]) > 0.0 or \
                        float(action.actionValue["blueLevel"]) > 0.0:
                    colorMode = True

            if (not colorMode) and (("whiteLevel" in action.actionValue) or ("whiteTemperature" in action.actionValue)):
                # If either of "whiteLevel" or "whiteTemperature" are altered - assume mode is White

                whiteLevel = float(dev.states["whiteLevel"])
                whiteTemperature = int(dev.states["whiteTemperature"])

                if "whiteLevel" in action.actionValue:
                    whiteLevel = float(action.actionValue["whiteLevel"])

                if "whiteTemperature" in action.actionValue:
                    whiteTemperature = int(action.actionValue["whiteTemperature"])
                    if whiteTemperature < 2500:
                        whiteTemperature = 2500
                    elif whiteTemperature > 9000:
                        whiteTemperature = 9000

                kelvin = min(LIFX_KELVINS, key=lambda x: abs(x - whiteTemperature))
                rgb, kelvinDescription = LIFX_KELVINS[kelvin]

                self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put(
                    [QUEUE_PRIORITY_COMMAND_HIGH, CMD_WHITE, dev.id, [whiteLevel, kelvin]])

                self.logger.info(f"sent \"{dev.name}\" set White Level to \"{int(whiteLevel)}\" and White Temperature to \"{kelvinDescription}\" with duration of {duration} seconds")

            else:
                # As neither of "whiteTemperature" or "whiteTemperature" are set - assume mode is Colour

                props = dev.pluginProps
                if ("SupportsRGB" in props) and props["SupportsRGB"]:  # Check device supports color
                    redLevel = float(dev.states["redLevel"])
                    greenLevel = float(dev.states["greenLevel"])
                    blueLevel = float(dev.states["blueLevel"])

                    if "redLevel" in action.actionValue:
                        redLevel = float(action.actionValue["redLevel"])
                    if "greenLevel" in action.actionValue:
                        greenLevel = float(action.actionValue["greenLevel"])
                    if "blueLevel" in action.actionValue:
                        blueLevel = float(action.actionValue["blueLevel"])

                    self.logger.debug(f"sent \"{dev.name}\" Red = {redLevel}[{int(redLevel * 2.56)}], Green = {greenLevel}[{int(greenLevel * 2.56)}], Blue = {blueLevel}[{int(blueLevel * 2.56)}]")

                    # Convert Indigo values for rGB (0-100) to colorSys values (0.0-1.0)
                    red = float(redLevel / 100.0)  # e.g. 100.0/100.0 = 1.0
                    green = float(greenLevel / 100.0)  # e.g. 70.0/100.0 = 0.7
                    blue = float(blueLevel / 100.0)  # e.g. 40.0/100.0 = 0.4

                    hsv_hue, hsv_saturation, hsv_brightness = colorsys.rgb_to_hsv(red, green, blue)

                    # Convert colorsys values for HLS (0.0-1.0) to H (0-360), L aka B (0.0 -100.0) and S (0.0 -100.0)
                    hue = int(hsv_hue * 65535.0)
                    brightness = int(hsv_brightness * 65535.0)
                    saturation = int(hsv_saturation * 65535.0)

                    self.logger.debug(
                        f"ColorSys: \"{dev.name}\" R, G, B: {red}, {green}, {blue} = H: {hue}[{hsv_hue}], S: {saturation}[{hsv_saturation}], B: {brightness}[{hsv_brightness}]")

                    self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put(
                        [QUEUE_PRIORITY_COMMAND_HIGH, CMD_COLOR, dev.id, [hue, saturation, brightness]])

                    hueUi = f'{int(((hue * 360.0) / 65535.0))}'
                    saturationUi = f'{int(((saturation * 100.0) / 65535.0))}'
                    brightnessUi = f'{int(((brightness * 100.0) / 65535.0))}'

                    self.logger.info(f"sent \"{dev.name}\" set Color Level to hue \"{hueUi}\", saturation \"{saturationUi}\" and brightness \"{brightnessUi}\" with duration of {duration} seconds")
                else:
                    self.logger.info(
                        f"Failed to send \"{dev.name}\" set Color Level as device does not support color.")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def process_status(self, plugin_action, dev):
        try:
            self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put([QUEUE_PRIORITY_STATUS_MEDIUM, CMD_STATUS, dev.id, None])
            self.logger.info(f"sent \"{dev.name}\" {'status request'}")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def process_turn_off(self, plugin_action, dev, actionUi="off"):
        try:
            self.logger.debug(f"LIFX \"processTurnOff\" [{dev.name}]")

            self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put([QUEUE_PRIORITY_COMMAND_HIGH, CMD_OFF, dev.id, None])

            duration = self.globals[K_LIFX][dev.id][K_DURATION_OFF]
            self.logger.info(f"sent \"{dev.name}\" {actionUi} with duration of {duration} seconds")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def process_turn_on(self, plugin_action, dev, actionUi="on"):
        try:
            self.logger.debug(f"LIFX \"processTurnOn\" [{dev.name}]")

            self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put([QUEUE_PRIORITY_COMMAND_HIGH, CMD_ON, dev.id, None])

            duration = self.globals[K_LIFX][dev.id][K_DURATION_ON]
            self.logger.info(f"sent \"{dev.name}\" {actionUi} with duration of {duration} seconds")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def process_turn_on_off_toggle(self, plugin_action, dev):
        try:
            self.logger.debug(f"LIFX \"processTurnOnOffToggle\" [{dev.name}]")

            onStateRequested = not dev.onState
            if onStateRequested:
                actionUi = "toggle from \"off\" to \"on\""
                self.process_turn_on(plugin_action, dev, actionUi)
            else:
                actionUi = "toggle from \"on\" to \"off\""
                self.process_turn_off(plugin_action, dev, actionUi)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def setColorWhite(self, plugin_action, dev):  # Dev is a LIFX Lamp
        try:
            self.logger.debug(f"LIFX 'setColorWhite' [{self.globals[K_LIFX][dev.id][K_IP_ADDRESS]}] - plugin_action Props =\n{plugin_action.props}")

            action_type = str(plugin_action.props.get("actionType", "INVALID"))  # "Standard" or "Waveform"

            if not dev.states["connected"] or not self.globals[K_LIFX][dev.id][K_CONNECTED]:
                self.logger.info(
                    f"Unable to apply action \"Set Color/White - {action_type}\" to \"{dev.name}\" as device not connected")
                return

            if (action_type != "Standard") and (action_type != "Waveform"):
                self.logger.error(f"LIFX 'setColorWhite' for {dev.name} - Invalid message type '{action_type}'")
                return

            if action_type == "Standard":
                hue = "-"  # Denotes value not set
                saturation = "-"
                kelvin = "-"
                mode = str(plugin_action.props.get("modeStandard", "White"))  # "Color" or "White" (Default)
                if mode == "White":
                    try:
                        kelvin = str(plugin_action.props.get("kelvinStandard", "-"))  # Denotes value not set
                    except Exception:
                        kelvin = "-"
                elif mode == "Color":
                    try:
                        hue = str(plugin_action.props.get("hueStandard", "-"))
                        saturation = plugin_action.props.get("saturationStandard", "-")  # Denotes value not set
                    except Exception:
                        hue = "-"
                        saturation = "-"
                else:
                    self.logger.error(f"LIFX 'setColorWhite' for {dev.name} - Invalid mode '{mode}'")
                    return

                try:
                    brightness = str(plugin_action.props.get("brightnessStandard", "-"))  # Denotes value not set
                except Exception:
                    brightness = "-"
                try:
                    duration = float(plugin_action.props.get("durationStandard", "-"))
                    duration = str(duration)
                except Exception:
                    duration = "-"
                try:
                    turn_on_if_off = bool(
                        plugin_action.props.get("turn_on_if_off", True))  # Default "Turn On if Off" to True if missing
                except Exception:
                    turn_on_if_off = True  # Default "Turn On if Off" to True if error

                self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put([QUEUE_PRIORITY_COMMAND_HIGH, CMD_STANDARD, dev.id,
                                                                       [turn_on_if_off, mode, hue, saturation, brightness, kelvin,
                                                                        duration]])

                if mode == "White":
                    if kelvin == "-":
                        kelvinUi = "existing"
                    else:
                        kelvinUi = f'{int(kelvin)}'
                    if brightness == "-":
                        brightnessUi = "existing"
                    else:
                        brightnessUi = f'{int(float(brightness))}'
                    if duration == "-":
                        durationUi = "default"
                    else:
                        durationUi = str(duration)
                    self.logger.info(f"sent \"{dev.name}\" set White Level to \"{int(brightnessUi)}\" and White Temperature to \"{int(kelvinUi)}\" with duration of {durationUi} seconds")
                else:
                    if hue == "-":
                        hueUi = "existing"
                    else:
                        hueUi = f'{int(float(hue))}'
                    if saturation == "-":
                        saturationUi = "existing"
                    else:
                        saturationUi = f'{int(float(saturation))}'
                    if brightness == "-":
                        brightnessUi = "existing"
                    else:
                        brightnessUi = f'{int(float(brightness))}'
                    if duration == "-":
                        durationUi = "default"
                    else:
                        durationUi = str(duration)

                    self.logger.info(f"sent \"{dev.name}\" set Color Level to hue \"{hueUi}\", saturation \"{saturationUi}\" and brightness \"{brightnessUi}\" with duration of {durationUi} seconds")
                return

            # Waveform

            hue = 0  # Defaulted to avoid error (although not needed)
            saturation = 100  # Defaulted to avoid error (although not needed)
            kelvin = 0  # Defaulted to avoid error (although not needed)

            mode = str(plugin_action.props.get("modeWaveform", "White"))  # "Color" or "White" (Default)
            if mode == "White":
                try:
                    kelvin = str(plugin_action.props.get("kelvinWaveform", "3500"))  # Default Kelvin to 3500 if missing
                except Exception:
                    kelvin = "3500"  # Default Kelvin to 3500 if error
            elif mode == "Color":
                try:
                    hue = str(plugin_action.props.get("hueWaveform", "0"))  # Default Hue to 0 (Red) if missing
                    saturation = plugin_action.props.get("saturationWaveform", "100")  # Default Saturation to 100 if missing
                except Exception:
                    hue = "0"  # Default Hue to 0 (Red) if error
                    saturation = "100"  # Default Saturation to 100 if error
            try:
                brightness = str(
                    plugin_action.props.get("brightnessWaveform", "100"))  # Default Brightness to 100 if missing
            except Exception:
                brightness = "100"  # Default Brightness to 100 if error
            try:
                transient = plugin_action.props.get("transientWaveform",
                                                    True)  # Default Transient to "1" (Return color to original) if missing
            except Exception:
                transient = True  # Default Transient to "1" (Return color to original) if error
            try:
                period = str(
                    int(plugin_action.props.get("periodWaveform", 600)))  # Default Period to "500" (milliseconds) if missing
            except Exception:
                period = str("700")  # Default Period to "500" (milliseconds) if error
            try:
                cycles = str(plugin_action.props.get("cyclesWaveform", "10"))  # Default Cycles to "10" if missing
            except Exception:
                cycles = "10"  # Default Cycles to "10" if error
            try:
                dutyCycle = str(plugin_action.props.get("dutyCycleWaveform",
                                                        "0"))  # Default Duty Cycle to "0" (Equal amount of time) if missing
            except Exception:
                dutyCycle = "0"  # Default Duty Cycle to "0" (Equal amount of time) if error
            try:
                typeWaveform = str(
                    plugin_action.props.get("typeWaveform", "0"))  # Default TYpe of Waveform to "0" (Saw) if missing
            except Exception:
                typeWaveform = "0"  # Default TYpe of Waveform to "0" (Saw) if missing

            self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put([QUEUE_PRIORITY_WAVEFORM, CMD_WAVEFORM, dev.id,
                                                                   [mode, hue, saturation, brightness, kelvin, transient, period,
                                                                    cycles, dutyCycle, typeWaveform]])

            transientUi = " Color will be returned to original." if transient else ""
            periodUi = f'{int(period)}'
            cyclesUi = f'{int(cycles)}'
            if int(dutyCycle) == 0:
                dutyCycleUi = "an equal amount of time is spent on the original color and the new color"
            elif int(dutyCycle) > 0:
                dutyCycleUi = "more time is spent on the original color"
            else:
                dutyCycleUi = "more time is spent on the new color"
            typeWaveformUi = LIFX_WAVEFORMS.get(typeWaveform, "0")

            brightnessUi = f'{int(float(brightness))}'

            if mode == "White":
                kelvinUi = f'{int(float(kelvin))}'
                self.logger.info(f"sent \"{dev.name}\" waveform \"{typeWaveformUi}\" with White Level to \"{int(brightnessUi)}\" and White Temperature to \"{int(kelvinUi)}\" ...")
            else:
                hueUi = f'{int(float(hue))}'
                saturationUi = f'{int(float(saturation))}'
                self.logger.info(f"sent \"{dev.name}\" waveform \"{typeWaveformUi}\" with hue \"{hueUi}\", saturation \"{saturationUi}\" and brightness \"{brightnessUi}\" ...")
            self.logger.info(f"  ... period is \"{periodUi}\" milliseconds for \"{cyclesUi}\" cycles and {dutyCycleUi}.{transientUi}")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def setInfraredBrightness(self, plugin_action, dev):  # Dev is a LIFX Lamp
        try:
            if self.device_supports_infrared(dev, "Set Infrared Brightness"):
                try:
                    infrared_brightness = float(plugin_action.props.get("infraredBrightness", 100.0))
                except ValueError:
                    error_infrared_brightness = plugin_action.props.get("infraredBrightness", "NOT SPECIFIED")
                    self.logger.error(
                        f"Failed to set infrared maximum brightness for \"{dev.name}\" value '{error_infrared_brightness}' is invalid.")
                    return

                self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put(
                    [QUEUE_PRIORITY_COMMAND_HIGH, CMD_INFRARED_SET, dev.id, [infrared_brightness]])
                infrared_brightness_ui = f'{int(float(infrared_brightness))}'
                self.logger.info(f"sent '{dev.name}' set infrared maximum brightness to {infrared_brightness_ui}")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def turnOnInfrared(self, plugin_action, dev):  # Dev is a LIFX Lamp
        try:
            if self.device_supports_infrared(dev, "Turn On"):
                self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put([QUEUE_PRIORITY_COMMAND_HIGH, CMD_INFRARED_ON, dev.id, None])
                self.logger.info(f"sent '{dev.name}' turn on infrared")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def turnOffInfrared(self, plugin_action, dev):  # Dev is a LIFX Lamp
        try:
            if self.device_supports_infrared(dev, "Turn Off"):
                self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put([QUEUE_PRIORITY_COMMAND_HIGH, CMD_INFRARED_OFF, dev.id, None])
                self.logger.info(f"sent '{dev.name}' turn off infrared")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def resetRecoveryTotals(self, plugin_action, dev):  # Dev is a LIFX Lamp
        try:
            dev.updateStateOnServer(key="total_no_ack_events", value=0)
            dev.updateStateOnServer(key="total_recovery_attempts", value=0)
            dev.updateStateOnServer(key="total_successful_recoveries", value=0)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def resetRecoveryTotalsAll(self, plugin_action):
        try:
            for dev in indigo.devices.iter("self"):
                if dev.deviceTypeId == "lifxDevice":
                    dev.updateStateOnServer(key="total_no_ack_events", value=0)
                    dev.updateStateOnServer(key="total_recovery_attempts", value=0)
                    dev.updateStateOnServer(key="total_successful_recoveries", value=0)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def printRecoveryTotalsAll(self, plugin_action):
        try:
            header = "\nRECOVERY TOTALS\n===============\n\n"

            detail = ""
            detail_list = []
            max_len_dev_name = 0
            for dev in indigo.devices.iter("self"):
                if dev.deviceTypeId == "lifxDevice":
                    name = dev.name
                    if len(name) > max_len_dev_name:
                        max_len_dev_name = len(name)
                    try:
                        total_no_ack_events = dev.states["total_no_ack_events"]
                    except KeyError:
                        total_no_ack_events = 0
                    try:
                        total_recovery_attempts = dev.states["total_recovery_attempts"]
                    except KeyError:
                        total_recovery_attempts = 0
                    try:
                        total_successful_recoveries = dev.states["total_successful_recoveries"]
                    except KeyError:
                        total_successful_recoveries = 0
                    detail_list.append([name, total_no_ack_events, total_recovery_attempts, total_successful_recoveries])

            detail_list.sort()
            detail_lines = ""
            for detail in detail_list:
                name = detail[0].ljust(max_len_dev_name)
                total_no_ack_events = detail[1]
                total_recovery_attempts = detail[2]
                total_successful_recoveries = detail[3]
                detail_lines = (f"{detail_lines}{name}: 'No Ack' = {total_no_ack_events}, Attempts = {total_recovery_attempts}, Recoveries = {total_successful_recoveries}\n")

            footer = "\n===============\n"

            self.logger.info(f"{header}{detail_lines}{footer}")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def validate_action_config_ui_set_color_white(self, values_dict, type_id, action_id):
        try:
            self.logger.debug(f"validate_action_config_ui_set_color_white: type_id=[{type_id}], action_id=[{action_id}]")

            error_dict = indigo.Dict()  # Initialise Error Dictionary

            # validate LIFX actionType
            action_type = values_dict["actionType"]
            if action_type != "Standard" and action_type != "Waveform":
                error_dict["actionType"] = "LIFX Action must be set to one of 'Standard' or 'Waveform'"
                error_dict["showAlertText"] = "You must select a valid LIFX Action; either 'Standard' or 'Waveform'"
                return False, values_dict, error_dict

            if action_type == "Standard":
                # Validation for LIFX actionType "Waveform"

                valueCount = 0  # To count number of fields entered for consistency check

                # validate modeStandard
                mode_standard = values_dict["modeStandard"]
                if mode_standard != "Color" and mode_standard != "White":
                    error_dict["modeStandard"] = "Color / White selection must be set to one of 'Color' or 'White'"
                    error_dict["showAlertText"] = "Color / White selection must be set to one of 'Color' or 'White'"
                    return False, values_dict, error_dict

                if mode_standard == "Color":
                    # Validate "hueStandard" value
                    hue_standard = values_dict["hueStandard"].rstrip().lstrip()  # Remove leading/trailing spaces
                    if hue_standard == "" or hue_standard == "-":
                        values_dict["hueStandard"] = "-"
                    else:
                        try:
                            hue_standard = float(f"{float(hue_standard):06.1f}")
                            if float(hue_standard) < 0.0 or float(hue_standard) > 360.0:
                                raise ValueError("Hue must be set between 0.0 and 360.0 (inclusive)")
                            values_dict["hueStandard"] = f"{hue_standard}"
                            valueCount += 1  # At least one of the required fields now entered
                        except ValueError:
                            error_dict["hueStandard"] = "Hue must be set between 0.0 and 360.0 (inclusive) or "-" (dash) to not set value"
                            error_dict["showAlertText"] = ("You must enter a valid Hue value for the LIFX device."
                                                           " It must be a value between 0.0 and 360.0 (inclusive)"
                                                           " or "-" (dash) to leave an existing value unchanged")
                            return False, values_dict, error_dict

                if mode_standard == "Color":
                    # Validate "saturationStandard" value
                    saturation_standard = values_dict["saturationStandard"].rstrip().lstrip()
                    if saturation_standard == "" or saturation_standard == "-":
                        values_dict["saturation_standard"] = "-"
                    else:
                        try:
                            saturation_standard = float(f"{float(saturation_standard):06.1f}")
                            if float(saturation_standard) < 0.0 or float(saturation_standard) > 100.0:
                                raise ValueError("Saturation must be set between 0.0 and 100.0 (inclusive)")
                            values_dict["saturationStandard"] = f"{saturation_standard}"
                            valueCount += 1  # At least one of the required fields now entered
                        except ValueError:
                            error_dict["saturationStandard"] = ("Saturation must be set between 0.0 and 100.0 (inclusive)"
                                                                " or "-" (dash) to not set value")
                            error_dict["showAlertText"] = ("You must enter a valid Saturation value for the LIFX device."
                                                           " It must be a value between 0.0 and 100.0 (inclusive)"
                                                           " or "-" (dash) to leave an existing value unchanged")
                            return False, values_dict, error_dict

                if mode_standard == "White":
                    # Validate "kelvinStandard" value
                    kelvin_standard = values_dict["kelvinStandard"]
                    if kelvin_standard == "-":
                        pass
                    else:
                        try:
                            kelvin_standard = int(kelvin_standard)  # Extract Kelvin value from description
                            if kelvin_standard < 2500 or kelvin_standard > 9000:
                                raise ValueError("Kelvin must be set between 2500 and 9000 (inclusive)")
                            valueCount += 1  # At least one of the required fields now entered
                        except ValueError:
                            error_dict["kelvinStandard"] = ("Kelvin must be set to one of the presets between 2500 and 9000 (inclusive)"
                                                            " or to 'Use current Kelvin value' to leave the existing value unchanged")
                            error_dict["showAlertText"] = ("You must select a valid Kelvin value for the LIFX device"
                                                           " or to 'Use current Kelvin value' to leave the existing value unchanged")
                            return False, values_dict, error_dict

                # Validate "brightnessStandard" value
                brightness_standard = values_dict["brightnessStandard"].rstrip().lstrip()
                if brightness_standard == "" or brightness_standard == "-":
                    values_dict["brightnessStandard"] = "-"
                else:
                    try:
                        brightness_standard = float(f"{float(brightness_standard):06.1f}")
                        if float(brightness_standard) < 0.0 or float(brightness_standard) > 100.0:
                            raise ValueError("Brightness must be set between 0.0 and 100.0 (inclusive)")
                        values_dict["brightnessStandard"] = f"{brightness_standard}"
                        valueCount += 1  # At least one of the required fields now entered
                    except ValueError:
                        error_dict["brightnessStandard"] = ("Brightness must be set between 0.0 and 100.0 (inclusive) or"
                                                            " '-' (dash) to not set value")
                        error_dict["showAlertText"] = ("You must enter a valid Brightness value for the LIFX device."
                                                       " It must be a value between 0.0 and 100.0 (inclusive) or '-' (dash)"
                                                       " to leave an existing value unchanged")
                        return False, values_dict, error_dict

                # Validate "durationStandard" value
                duration_standard = values_dict["durationStandard"].rstrip().lstrip()
                if not (duration_standard == "" or duration_standard == "-"):
                    try:
                        duration_standard = float(f"{float(duration_standard):06.1f}")
                        values_dict["durationStandard"] = f"{duration_standard}"
                        valueCount += 1  # At least one of the required fields now entered
                    except Exception:
                        error_dict["durationStandard"] = "Duration must be numeric or "-" (dash) to not set value"
                        error_dict["showAlertText"] = ("You must enter a valid Duration value for the LIFX device."
                                                       " It must be a numeric e.g. 2.5 (representing seconds)"
                                                       " or '-' (dash) to leave an existing value unchanged")
                        return False, values_dict, error_dict

                if valueCount == 0:  # All values missing / not specified
                    if mode_standard == "Color":
                        errorMsg = "One of Hue, Saturation, Brightness or Duration must be present"
                        error_dict["hueStandard"] = errorMsg
                        error_dict["saturationStandard"] = errorMsg
                    else:
                        # "White"
                        errorMsg = "One of Kelvin, Brightness or Duration must be present"
                        error_dict["kelvinStandard"] = "One of Hue, Kelvin, Brightness or Duration must be present"
                    error_dict["brightnessStandard"] = errorMsg
                    error_dict["durationStandard"] = errorMsg
                    error_dict["showAlertText"] = errorMsg
                    return False, values_dict, error_dict

                if type_id == "set_color_white":
                    if values_dict["selected_preset_Option"] != "NONE":
                        error_dict["selected_preset_Option"] = "Preset Options must be set to 'No Action'"
                        error_dict["showAlertText"] = ("Preset Options must be set to 'No Action' before you can Save. This is a safety"
                                                       " check in case you meant to save/update a Preset and forgot to do so ;-)")
                        return False, values_dict, error_dict

                return True, values_dict

            else:
                # Validation for LIFX actionType "Waveform"

                # validate modeWaveform
                mode_waveform = values_dict["modeWaveform"]
                if mode_waveform != "Color" and mode_waveform != "White":
                    error_dict["modeWaveform"] = "Color / White selection must be set to one of 'Color' or 'White'"
                    error_dict["showAlertText"] = "YColor / White selection must be set to one of 'Color' or 'White'"
                    return False, values_dict, error_dict

                if mode_waveform == "Color":
                    # Validate "hueWaveform" value
                    hue_waveform = values_dict["hueWaveform"].rstrip().lstrip()  # Remove leading/trailing spaces
                    try:
                        hue_waveform = float(f"{float(hue_waveform):06.1f}")
                        if float(hue_waveform) < 0.0:
                            raise ValueError("Hue must be a positive number")
                        if float(hue_waveform) < 0.0 or float(hue_waveform) > 360.0:
                            raise ValueError("Hue must be set between 0.0 and 360.0 (inclusive)")
                        values_dict["hueWaveform"] = f"{hue_waveform}"
                    except ValueError:
                        error_dict["hueWaveform"] = "Hue must be set between 0.0 and 360.0 (inclusive)"
                        error_dict["showAlertText"] = ("You must enter a valid Hue value for the LIFX device."
                                                       " It must be a value between 0.0 and 360.0 (inclusive)")
                        return False, values_dict, error_dict

                if mode_waveform == "Color":
                    # Validate "saturationWaveform" value
                    saturation_waveform = values_dict["saturationWaveform"].rstrip().lstrip()
                    try:
                        saturation_waveform = float(f"{float(saturation_waveform):06.1f}")
                        if float(saturation_waveform) < 0.0 or float(saturation_waveform) > 100.0:
                            raise ValueError("Saturation must be set between 0.0 and 100.0 (inclusive)")
                        values_dict["saturation_waveform"] = f"{saturation_waveform}"
                    except ValueError:
                        error_dict["saturationWaveform"] = "Saturation must be set between 0.0 and 100.0 (inclusive)"
                        error_dict["showAlertText"] = ("You must enter a valid Saturation value for the LIFX device."
                                                       " It must be a value between 0.0 and 100.0 (inclusive)")
                        return False, values_dict, error_dict

                if mode_waveform == "White":
                    # Validate "kelvinWaveform" value
                    kelvin_waveform = values_dict["kelvinWaveform"].rstrip().lstrip()
                    try:
                        kelvin_waveform = int(kelvin_waveform)
                        if kelvin_waveform < 2500 or kelvin_waveform > 9000:
                            raise ValueError("Kelvin must be set between 2500 and 9000 (inclusive)")
                        values_dict["kelvinWaveform"] = kelvin_waveform
                    except ValueError:
                        error_dict["kelvinWaveform"] = "Kelvin must be set between 2500 and 9000 (inclusive)"
                        error_dict["showAlertText"] = ("You must enter a valid Kelvin value for the LIFX device."
                                                       " It must be an integer between 2500 and 9000 (inclusive)")
                        return False, values_dict, error_dict

                # Validate "brightnessWaveform" value
                brightness_waveform = values_dict["brightnessWaveform"].rstrip().lstrip()
                try:
                    brightness_waveform = float(f"{float(brightness_waveform):06.1f}")
                    if float(brightness_waveform) < 0.0 or float(brightness_waveform) > 100.0:
                        raise ValueError("Brightness must be set between 0.0 and 100.0 (inclusive)")
                    values_dict["brightnessWaveform"] = f"{brightness_waveform}"
                except ValueError:
                    error_dict["brightnessWaveform"] = "Brightness must be set between 0.0 and 100.0 (inclusive)"
                    error_dict["showAlertText"] = ("You must enter a valid Brightness value for the LIFX device."
                                                   " It must be a value between 0.0 and 100.0 (inclusive)")
                    return False, values_dict, error_dict

                # Validate "periodWaveform" value
                period_waveform = values_dict["periodWaveform"].rstrip().lstrip()
                try:
                    period_waveform = f'{int(period_waveform)}'
                    values_dict["periodWaveform"] = period_waveform
                except Exception:
                    error_dict["periodWaveform"] = "Period must be numeric"
                    error_dict["showAlertText"] = ("You must enter a valid Period value for the LIFX device."
                                                   " It must be a numeric e.g. 750 (representing milliseconds)")
                    return False, values_dict, error_dict

                # Validate "cyclesWaveform" value
                cycles_waveform = values_dict["cyclesWaveform"].rstrip().lstrip()
                try:
                    cycles_waveform = str(int(cycles_waveform))
                    values_dict["cyclesWaveform"] = cycles_waveform
                except ValueError:
                    error_dict["cyclesWaveform"] = "Cycles must be numeric"
                    error_dict["showAlertText"] = ("You must enter a valid Cycles value for the LIFX device."
                                                   " It must be a numeric e.g. 10 (representing whole seconds)")
                    return False, values_dict, error_dict

            if values_dict["selectedPresetOption"] != "NONE":
                error_dict["selectedPresetOption"] = "Preset Options must be set to 'No Action'"
                error_dict["showAlertText"] = ("Preset Options must be set to 'No Action' before you can Save."
                                               " A safety check to check if you were trying to save/update a Preset and forgot to do so ;-)")
                return False, values_dict, error_dict

            return True, values_dict

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement
