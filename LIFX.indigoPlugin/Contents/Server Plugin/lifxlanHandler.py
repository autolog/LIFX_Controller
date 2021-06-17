#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# LIFX V6 Controller - Send & Receive Messages © Autolog 2020
#

# noinspection PyUnresolvedReferences
# ============================== Native Imports ===============================
import colorsys
import locale
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


# noinspection PyUnresolvedReferences,PyPep8Naming
class ThreadLifxlanHandler(threading.Thread):

    # This class manages the interface to the lifxlan library
    #   and controls the sending of commands to lifx devices and handles their responses.

    def __init__(self, pluginGlobals, event):

        threading.Thread.__init__(self)

        self.globals = pluginGlobals

        self.lh_logger = logging.getLogger("Plugin.LIFX_HANDLER")
        self.lh_logger.debug(u"Debugging LIFX Handler Thread")

        self.lifx_discovered_devices_mapping = dict()

        self.thread_stop = event

        self.lifxlan = None

    def run(self):
        try:
            # Initialise the LIFX Lamps on startup
            # self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put([QUEUE_PRIORITY_INIT_DISCOVERY, CMD_DISCOVERY, None, None])

            self.lh_logger.debug(u"LIFXLAN Handler Thread initialised")

            while not self.thread_stop.is_set():
                try:
                    lifx_queued_entry = self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].get(True, 5)

                    # lifx_queued_entry format:
                    #   - Priority
                    #   - Command
                    #   - Device
                    #   - Data

                    lifx_queue_priority, lifx_command, dev_id, lifx_command_arguments = lifx_queued_entry

                    # Debug info to log
                    if dev_id is not None:
                        debug_dev_info = u"for device '{0}' ".format(indigo.devices[dev_id].name)
                    else:
                        debug_dev_info = ""
                    self.lh_logger.debug(u"Dequeued lifxlanHandler Command '{0}' {1} to process with priority: {2}"
                                         .format(CMD_TRANSLATION[lifx_command], debug_dev_info, lifx_queue_priority))

                    if lifx_command == CMD_STOP_THREAD:
                        break  # Exit While loop and quit thread

                    if dev_id is None:
                        # Ignore command
                        pass
                        continue  # Loop back to process next entry off the queue

                    dev = indigo.devices[dev_id]

                    if not dev.enabled:
                        indigo.devices[dev_id].updateStateOnServer(key="brightnessLevel",
                                                                   value=0,
                                                                   uiValue=u'not enabled',
                                                                   clearErrorState=True)
                        continue  # Loop back to process next entry off the queue

                    if K_LIFX_COMMAND_CURRENT not in self.globals[K_LIFX][dev_id]:
                        self.globals[K_LIFX][dev_id][K_LIFX_COMMAND_CURRENT] = ""
                    self.globals[K_LIFX][dev_id][K_LIFX_COMMAND_PREVIOUS] = self.globals[K_LIFX][dev_id][K_LIFX_COMMAND_CURRENT]
                    self.globals[K_LIFX][dev_id][K_LIFX_COMMAND_CURRENT] = lifx_command

                    if K_LIFX_DEVICE not in self.globals[K_LIFX][dev_id]:
                        self.lh_logger.debug(u"Indigo LIFX device '{0}' not yet set-up".format(dev.name))
                        return

                    if self.globals[K_LIFX][dev_id][K_LIFX_DEVICE] is None:
                        # self.globals[K_LIFX][dev_id][K_NO_ACK_STATE] = True
                        # dev.updateStateOnServer(key="no_ack_state",
                        #                         value=self.globals[K_LIFX][dev_id][K_NO_ACK_STATE],
                        #                         clearErrorState=True)
                        self.globals[K_LIFX][dev_id][K_CONNECTED] = False
                        dev.updateStateOnServer(key="connected",
                                                value=False,
                                                clearErrorState=True)
                        self.handle_no_ack_status(dev)

                    dev = indigo.devices[dev_id]

                    if lifx_command == CMD_STATUS or lifx_command == CMD_POLLING_STATUS or lifx_command == CMD_RECOVERY_STATUS:
                        self.process_status(lifx_command, dev)
                        continue

                    if not self.globals[K_LIFX][dev_id][K_CONNECTED]:  # Ignore following commands if lamp not connected
                        continue

                    # At this point the device is confirmed to be connected - so now process commands

                    if (lifx_command == CMD_ON) or \
                            (lifx_command == CMD_OFF) or \
                            (lifx_command == CMD_WAVEFORM_OFF) or \
                            (lifx_command == CMD_IMMEDIATE_ON):
                        self.process_on_off(lifx_command, dev)

                    elif (lifx_command == CMD_INFRARED_ON) or \
                            (lifx_command == CMD_INFRARED_OFF) or \
                            (lifx_command == CMD_INFRARED_SET):
                        self.process_infrared(lifx_command, dev, lifx_command_arguments)

                    elif lifx_command == CMD_STOP_BRIGHTEN_DIM_BY_TIMER:
                        self.globals[K_LIFX][dev_id][K_STOP_REPEAT_BRIGHTEN] = True
                        self.globals[K_LIFX][dev_id][K_STOP_REPEAT_DIM] = True
                        self.clear_brighten_by_timer_timer(dev)
                        self.clear_dim_by_timer_timer(dev)

                    elif lifx_command == CMD_BRIGHTEN_BY_TIMER or lifx_command == CMD_REPEAT_BRIGHTEN_BY_TIMER:
                        self.process_brighten_by_timer(lifx_command, dev, lifx_command_arguments)

                    elif lifx_command == CMD_DIM_BY_TIMER or lifx_command == CMD_REPEAT_DIM_BY_TIMER:
                        self.process_dim_by_timer(lifx_command, dev, lifx_command_arguments)

                    elif lifx_command == CMD_DIM or lifx_command == CMD_BRIGHTEN or lifx_command == CMD_BRIGHTNESS:
                        self.process_dim_brighten_brightness(lifx_command, dev, lifx_command_arguments)

                    elif lifx_command == CMD_WHITE:
                        self.process_white(lifx_command, dev, lifx_command_arguments)

                    elif lifx_command == CMD_COLOR:
                        self.process_color(lifx_command, dev, lifx_command_arguments)

                    elif lifx_command == CMD_STANDARD:
                        self.process_standard(lifx_command, dev, lifx_command_arguments)

                    elif lifx_command == CMD_WAVEFORM:
                        self.process_waveform(lifx_command, dev, lifx_command_arguments)

                    elif lifx_command == CMD_SET_LABEL:
                        self.process_set_label(lifx_command, dev)

                    elif lifx_command == CMD_GET_VERSION:
                        self.process_get_version(lifx_command, dev)

                    elif lifx_command == CMD_GET_HOST_FIRMWARE:
                        self.process_get_host_firmware(lifx_command, dev)

                    elif lifx_command == CMD_GET_PORT:
                        self.process_get_port(lifx_command, dev)

                    elif lifx_command == CMD_GET_WIFI_FIRMWARE:
                        self.process_get_wifi_firmware(lifx_command, dev, lifx_command_arguments)

                    elif lifx_command == CMD_GET_WIFI_INFO:
                        self.process_get_wifi_info(lifx_command, dev)

                    elif lifx_command == CMD_GET_HOST_INFO:
                        self.process_get_host_info(lifx_command, dev, lifx_command_arguments)

                    elif lifx_command == CMD_GET_LOCATION:
                        self.process_get_location(lifx_command, dev, lifx_command_arguments)

                    elif lifx_command == CMD_GET_GROUP:
                        self.process_get_group(lifx_command, dev, lifx_command_arguments)

                    elif lifx_command == CMD_GET_INFO:
                        self.process_get_info(lifx_command, dev, lifx_command_arguments)

                except Queue.Empty:
                    pass
                except StandardError as standard_error_message:
                    self.lh_logger.error(u"StandardError detected communicating with LIFX lamp."
                                         u" Line {0} has error: {1}"
                                         .format(sys.exc_traceback.tb_lineno, standard_error_message))

        except StandardError as standard_error_message:
            self.lh_logger.error(u"StandardError detected in LIFX Send Receive Message Thread. Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))

        self.lh_logger.debug(u"LIFX Send Receive Message Thread ended.")

    def clear_brighten_by_timer_timer(self, dev):
        if dev.id in self.globals[K_DEVICE_TIMERS] and 'BRIGHTEN_BY_TIMER' in self.globals[K_DEVICE_TIMERS][dev.id]:
            self.globals[K_DEVICE_TIMERS][dev.id]["BRIGHTEN_BY_TIMER"].cancel()

    def clear_dim_by_timer_timer(self, dev):
        if dev.id in self.globals[K_DEVICE_TIMERS] and "DIM_BY_TIMER" in self.globals[K_DEVICE_TIMERS][dev.id]:
            self.globals[K_DEVICE_TIMERS][dev.id]["DIM_BY_TIMER"].cancel()

    def clear_status_timer(self, dev):
        if dev.id in self.globals[K_DEVICE_TIMERS] and 'STATUS' in self.globals[K_DEVICE_TIMERS][dev.id]:
            self.globals[K_DEVICE_TIMERS][dev.id][K_STATUS].cancel()

    def clear_waveform_off_timer(self, dev):
        if 'WAVEFORM_OFF' in self.globals[K_DEVICE_TIMERS][dev.id]:
            self.globals[K_DEVICE_TIMERS][dev.id]["WAVEFORM_OFF"].cancel()

    def communication_lost(self, dev_id, lifx_command):
        try:
            dev = indigo.devices[dev_id]
            if self.globals[K_LIFX][dev_id][K_CONNECTED]:
                self.globals[K_LIFX][dev_id][K_CONNECTED] = False
                dev.updateStateOnServer(key="connected", value=self.globals[K_LIFX][dev_id][K_CONNECTED])
                dev.updateStateOnServer(key="onOffState", value=False)
                dev.updateStateOnServer(key="brightnessLevel", value=0)
                self.lh_logger.error(u"No acknowledgement received from '{0}' when attempting a '{1}' command."
                                     .format(dev.name, lifx_command))

            if dev_id not in self.globals[K_RECOVERY]:
                self.globals[K_RECOVERY][dev_id] = dict()
                self.globals[K_RECOVERY][dev_id][K_ATTEMPTS] = 0
            self.globals[K_RECOVERY][dev_id][K_ATTEMPTS] += 1

            if self.globals[K_RECOVERY][dev_id][K_ATTEMPTS] >= self.globals[K_PLUGIN_CONFIG_DEFAULT][K_RECOVERY_ATTEMPTS_LIMIT]:
                if self.globals[K_RECOVERY][dev_id][K_ATTEMPTS] == self.globals[K_PLUGIN_CONFIG_DEFAULT][K_RECOVERY_ATTEMPTS_LIMIT]:
                    self.lh_logger.error(u"Unable to communicate with LIFX device '{0}' - Retry limit reached."
                                         .format(indigo.devices[dev_id].name))
                self.handle_no_ack_status(dev)
            else:
                total_recovery_attempts = int(dev.states["total_recovery_attempts"])
                total_recovery_attempts += 1
                dev.updateStateOnServer(key="total_recovery_attempts", value=total_recovery_attempts)
                if not self.globals[K_PLUGIN_CONFIG_DEFAULT][K_HIDE_RECOVERY_MESSAGES]:
                    self.lh_logger.warning(u"Unable to communicate with LIFX device '{0}'. Retrying: Attempt {1}"
                                           .format(indigo.devices[dev_id].name, self.globals[K_RECOVERY][dev_id][K_ATTEMPTS]))

                try:
                    if dev_id in self.globals[K_RECOVERY_TIMERS]:
                        self.globals[K_RECOVERY_TIMERS][dev_id].cancel()
                        del self.globals[K_RECOVERY_TIMERS][dev_id]
                except StandardError:
                    pass

                self.globals[K_RECOVERY_TIMERS][dev_id] = threading.Timer(self.globals[K_PLUGIN_CONFIG_DEFAULT][K_RECOVERY_FREQUENCY],
                                                                          self.handle_timer_recovery_delay, [dev_id])
                self.globals[K_RECOVERY_TIMERS][dev_id].start()
                dev.setErrorStateOnServer(u"recovery active [{0}]".format(self.globals[K_RECOVERY][dev_id][K_ATTEMPTS]))

        except StandardError as standard_error_message:
            self.lh_logger.error(u"'communication_lost' error detected. Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))

    def communication_ok(self, dev_id, lifx_command):
        try:
            dev = indigo.devices[dev_id]
            if dev_id in self.globals[K_RECOVERY]:
                if self.globals[K_RECOVERY][dev_id][K_ATTEMPTS] >= self.globals[K_PLUGIN_CONFIG_DEFAULT][K_RECOVERY_ATTEMPTS_LIMIT]:
                    self.lh_logger.info(u"Re-established contact with LIFX device '{0}'".format(indigo.devices[dev_id].name))
                elif self.globals[K_RECOVERY][dev_id][K_ATTEMPTS] > 0:
                    self.lh_logger.info(u"Re-established contact with LIFX device '{0}' after {1} recovery attempt(s)"
                                        .format(indigo.devices[dev_id].name, self.globals[K_RECOVERY][dev_id][K_ATTEMPTS]))
                del self.globals[K_RECOVERY][dev_id]
                # dev.updateStateOnServer(key="no_ack_state", value=False)
                self.globals[K_LIFX][dev_id][K_CONNECTED] = True
                dev.updateStateOnServer(key="connected", value=True)
                total_successful_recoveries = int(dev.states["total_successful_recoveries"])
                total_successful_recoveries += 1
                dev.updateStateOnServer(key="total_successful_recoveries", value=total_successful_recoveries)

        except StandardError as standard_error_message:
            self.lh_logger.error(u"'communication_ok' error detected. Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))

    def get_color(self, dev_id, argLifxLanLightObject):

        status = False
        hsbk = (0, 0, 0, 3500)
        power = 0

        try:
            lifx_command = 'get_color'

            try:
                hsbk = argLifxLanLightObject.get_color()
                power = argLifxLanLightObject.power_level
                status = True
                self.communication_ok(dev_id, lifx_command)
            except (StandardError, WorkflowException):
                self.communication_lost(dev_id, lifx_command)

        except StandardError as standard_error_message:
            dev = indigo.devices[dev_id]
            self.lh_logger.error(u"Error detected in 'get_color' for LIFX device '{0}'. Line {1} has error: {2}"
                                 .format(dev.name, sys.exc_traceback.tb_lineno, standard_error_message))

        finally:
            return status, power, hsbk

    def get_infrared(self, dev_id, argLifxLanLightObject):
        lifx_command = 'get_infrared'
        try:
            infraredBrightness = argLifxLanLightObject.get_infrared()
            status = True
            self.communication_ok(dev_id, lifx_command)
        except (StandardError, WorkflowException, IOError) as error:
            self.lh_logger.debug(u"'get_infrared' error detected for '{0}' = {1}".format(indigo.devices[dev_id].name, error))
            status = False
            infraredBrightness = 0
            self.communication_lost(dev_id, lifx_command)
        return status, infraredBrightness

    def handle_no_ack_status(self, dev):
        try:
            dev_id = dev.id
            if self.globals[K_LIFX][dev_id][K_IGNORE_NO_ACK]:
                dev.updateStateImageOnServer(indigo.kStateImageSel.PowerOff)
                dev.updateStateOnServer(key="onOffState", value=False, clearErrorState=True)
                dev.updateStateOnServer(key="brightnessLevel", value=0, uiValue=u"0")
            else:
                dev.setErrorStateOnServer(u"no ack")  # Default to 'no ack' status

            total_no_ack_events = int(dev.states["total_no_ack_events"])
            total_no_ack_events += 1
            dev.updateStateOnServer(key="total_no_ack_events", value=total_no_ack_events)

        except StandardError as standard_error_message:
            self.lh_logger.error(u"StandardError detected in 'update_status_from_message'. Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))


    def handle_timer_recovery_delay(self, parameter):
        try:
            dev_id = parameter
            dev = indigo.devices[dev_id]

            self.lh_logger.debug(u"Timer for {0} [{1}] invoked for recovery queued Status command"
                                 .format(dev.name, dev.address))
            try:
                if dev_id in self.globals[K_RECOVERY_TIMERS]:
                    self.globals[K_RECOVERY_TIMERS][dev_id].cancel()
                del self.globals[K_RECOVERY_TIMERS][dev_id]
            except StandardError:
                pass

            self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put([QUEUE_PRIORITY_STATUS_HIGH, CMD_STATUS, dev_id, None])

        except StandardError as standard_error_message:
            self.lh_logger.error(u"'handle_timer_recovery_delay' error detected."
                                 u" Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))

    def handle_timer_repeating_queued_brighten_by_timer_command(self, parameters):
        try:
            dev_id = parameters[0]
            dev = indigo.devices[dev_id]
            option = parameters[1]
            amountToBrightenDimBy = parameters[2]
            timerInterval = parameters[3]

            self.lh_logger.debug(
                u"Timer for {0} [{1}] invoked for repeating queued message BRIGHTEN_BY_TIMER. Stop = {2}".format(
                    dev.name, dev.address, self.globals[K_LIFX][dev_id][K_STOP_REPEAT_BRIGHTEN]))

            try:
                del self.globals[K_DEVICE_TIMERS][dev_id]["BRIGHTEN_BY_TIMER"]
            except (KeyError, IndexError):
                pass

            if not self.globals[K_LIFX][dev_id][K_STOP_REPEAT_BRIGHTEN]:
                self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put(
                    [QUEUE_PRIORITY_COMMAND_MEDIUM, CMD_REPEAT_BRIGHTEN_BY_TIMER, dev.id,
                     [option, amountToBrightenDimBy, timerInterval]])

        except StandardError as standard_error_message:
            self.lh_logger.error(
                u"'handle_timer_repeating_queued_brighten_by_timer_command' error detected. Line {0} has error: {1}".format(
                    sys.exc_traceback.tb_lineno, standard_error_message))

    def handle_timer_repeating_queued_dim_by_timer_command(self, parameters):
        try:
            dev_id = parameters[0]
            dev = indigo.devices[dev_id]
            option = parameters[1]
            amountToBrightenDimBy = parameters[2]
            timerInterval = parameters[3]

            self.lh_logger.debug(u"Timer for {0} [{1}] invoked for repeating queued message DIM_BY_TIMER. Stop = {2}"
                                 .format(dev.name, dev.address, self.globals[K_LIFX][dev_id][K_STOP_REPEAT_DIM]))

            try:
                del self.globals[K_DEVICE_TIMERS][dev_id]["DIM_BY_TIMER"]
            except (KeyError, IndexError):
                pass

            if not self.globals[K_LIFX][dev_id][K_STOP_REPEAT_DIM]:
                self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put(
                    [QUEUE_PRIORITY_COMMAND_MEDIUM,
                     CMD_REPEAT_DIM_BY_TIMER,
                     dev_id,
                     [option, amountToBrightenDimBy, timerInterval]])

        except StandardError as standard_error_message:
            self.lh_logger.error(u"handle_timer_repeating_queued_dim_by_timer_command error detected."
                                 u" Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))

    def handle_timer_repeating_queued_status_command(self, dev, seconds):
        try:
            self.lh_logger.debug(u"Timer for {0} [{1}] invoked for repeating queued message STATUS - {2} seconds left"
                                 .format(dev.name, dev.address, seconds))

            try:
                del self.globals[K_DEVICE_TIMERS][dev.id][K_STATUS]
            except (KeyError, IndexError):
                pass

            self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put([QUEUE_PRIORITY_STATUS_HIGH, CMD_STATUS, dev.id, None])

            if seconds > 0:
                seconds -= 1
                self.globals[K_DEVICE_TIMERS][dev.id][K_STATUS] = \
                    threading.Timer(1.0, self.handle_timer_repeating_queued_status_command, [dev, seconds])
                self.globals[K_DEVICE_TIMERS][dev.id][K_STATUS].start()

        except StandardError as standard_error_message:
            self.lh_logger.error(u"handle_timer_repeating_queued_status_command error detected."
                                 u" Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))

    def handle_timer_waveform_off_command(self, dev):
        try:
            self.lh_logger.debug(u"Timer for {0} [{1}] invoked to turn off LIFX device (Used by Waveform)"
                                 .format(dev.name, dev.address))

            try:
                del self.globals[K_DEVICE_TIMERS][dev.id]["WAVEFORM_OFF"]
            except (KeyError, IndexError):
                pass

            self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put([QUEUE_PRIORITY_STATUS_HIGH, CMD_WAVEFORM_OFF, dev.id, None])

        except StandardError as standard_error_message:
            self.lh_logger.error(u"'handle_timer_waveform_off_command' error detected. Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))

    def process_brighten_by_timer(self, lifx_command, dev, lifx_command_arguments):
        try:
            dev_id = dev.id

            if lifx_command == CMD_BRIGHTEN_BY_TIMER:
                # Clear any outstanding timers
                self.clear_brighten_by_timer_timer(dev)
                self.globals[K_LIFX][dev_id][K_STOP_REPEAT_BRIGHTEN] = False
                self.globals[K_LIFX][dev_id][K_STOP_REPEAT_DIM] = True

            if not self.globals[K_LIFX][dev_id][K_STOP_REPEAT_BRIGHTEN]:
                option = lifx_command_arguments[0]
                amountToBrightenBy = lifx_command_arguments[1]
                timerInterval = lifx_command_arguments[2]

                newBrightness = dev.brightness + amountToBrightenBy
                if int(dev.states["power_level"]) == 0 or int(dev.states["indigo_brightness"]) < 100:
                    self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put(
                        [QUEUE_PRIORITY_COMMAND_HIGH, CMD_BRIGHTEN, dev_id, [newBrightness]])
                    dev.updateStateOnServer("brightnessLevel", newBrightness)
                    self.globals[K_DEVICE_TIMERS][dev_id]["BRIGHTEN_BY_TIMER"] = \
                        threading.Timer(timerInterval,
                                        self.handle_timer_repeating_queued_brighten_by_timer_command,
                                        [[dev_id, option, amountToBrightenBy, timerInterval]])
                    self.globals[K_DEVICE_TIMERS][dev_id]["BRIGHTEN_BY_TIMER"].start()
                else:
                    self.globals[K_LIFX][dev_id][K_STOP_REPEAT_BRIGHTEN] = True
                    self.lh_logger.info(u"\"{0}\" {1}".format(dev.name, "brightened to 100%"))

        except StandardError as standard_error_message:
            self.lh_logger.error(u"StandardError detected in 'process_brighten_by_timer'. Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))

    def process_color(self, lifx_command, dev, lifx_command_arguments):
        try:
            dev_id = dev.id

            # Stop any background timer brighten or dim operation
            self.globals[K_LIFX][dev_id][K_STOP_REPEAT_DIM] = True
            self.globals[K_LIFX][dev_id][K_STOP_REPEAT_BRIGHTEN] = True

            targetHue, targetSaturation, targetBrightness = lifx_command_arguments

            # Clear any outstanding timers
            self.clear_status_timer(dev)

            lifx_io_ok, power, hsbk = self.get_color(dev_id, self.globals[K_LIFX][dev_id][K_LIFX_DEVICE])
            self.lh_logger.debug(u"LIFX COMMAND [COLOR] lifx_io_ok for {0} =  {1}, HSBK = {2}"
                                 .format(indigo.devices[dev_id].name, lifx_io_ok, hsbk))
            if lifx_io_ok:
                hue = hsbk[0]
                saturation = hsbk[1]
                brightness = hsbk[2]
                kelvin = hsbk[3]

                self.lh_logger.debug(u"LIFX COMMAND [COLOR]; GET-COLOR for {0}:"
                                     u" Hue={1}, Saturation={2}, Brightness={3}, Kelvin={4}"
                                     .format(indigo.devices[dev_id].name, hue, saturation, brightness, kelvin))

                if power == 0 and self.globals[K_LIFX][dev_id]["turn_on_if_off"]:
                    # Need to reset existing brightness to 0 before turning on
                    try:
                        hsbkWithBrightnessZero = set_hsbk(hue, saturation, 0, kelvin)
                        self.globals[K_LIFX][dev_id][K_LIFX_DEVICE].set_color(
                            hsbkWithBrightnessZero, 0)
                        self.communication_ok(dev_id, lifx_command)
                    except (StandardError, WorkflowException, IOError) as error:
                        self.communication_lost(dev_id, 'set_color')
                        return
                    # Need to turn on LIFX device as currently off
                    power = 65535
                    try:
                        self.globals[K_LIFX][dev_id][K_LIFX_DEVICE].set_power(power, 0)
                        self.communication_ok(dev_id, lifx_command)
                    except (StandardError, WorkflowException, IOError) as error:
                        self.communication_lost(dev_id, 'set_power')
                        return

                hue = targetHue
                saturation = targetSaturation
                brightness = targetBrightness
                duration = int(self.globals[K_LIFX][dev_id][K_DURATION_COLOR_WHITE] * 1000)

                self.lh_logger.debug(u"LIFX COMMAND [COLOR]; SET-COLOR for {0}:"
                                     u" Hue={1}, Saturation={2}, Brightness={3}, Kelvin={4}, Duration={5}"
                                     .format(indigo.devices[dev_id].name, hue, saturation,
                                             brightness, kelvin, duration))

                try:
                    hsbk = set_hsbk(hue, saturation, brightness, kelvin)
                    self.globals[K_LIFX][dev_id][K_LIFX_DEVICE].set_color(hsbk, duration)
                    self.communication_ok(dev_id, lifx_command)
                except (StandardError, WorkflowException, IOError) as error:
                    self.communication_lost(dev_id, 'set_color')
                    return

                timer_duration = int(self.globals[K_LIFX][dev_id][K_DURATION_COLOR_WHITE])
                self.globals[K_DEVICE_TIMERS][dev_id][K_STATUS] = \
                    threading.Timer(1.0,
                                    self.handle_timer_repeating_queued_status_command,
                                    [dev, timer_duration])

                self.globals[K_DEVICE_TIMERS][dev_id][K_STATUS].start()

            self.globals[K_LIFX][dev_id][K_LIFX_COMMAND_PREVIOUS] = lifx_command

        except StandardError as standard_error_message:
            self.lh_logger.error(u"StandardError detected in 'process_color'. Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))

    def process_dim_brighten_brightness(self, lifx_command, dev, lifx_command_arguments):
        try:
            dev_id = dev.id

            newBrightness = lifx_command_arguments[0]
            newBrightness = int((newBrightness * 65535.0) / 100.0)

            # Clear any outstanding timers
            self.clear_status_timer(dev)

            hue = self.globals[K_LIFX][dev_id]["hsbkHue"]  # Value between 0 and 65535
            saturation = self.globals[K_LIFX][dev_id][
                "hsbkSaturation"]  # Value between 0 and 65535 (e.g. 20% = 13107)
            kelvin = self.globals[K_LIFX][dev_id]["hsbkKelvin"]  # Value between 2500 and 9000
            powerLevel = self.globals[K_LIFX][dev_id]["powerLevel"]  # Value between 0 and 65535

            if (lifx_command == CMD_BRIGHTEN or lifx_command == CMD_DIM) and powerLevel == 0:
                # Need to turn on LIFX device as currently off
                powerLevel = 65535
                try:
                    self.globals[K_LIFX][dev_id][K_LIFX_DEVICE].set_power(powerLevel, 0)
                    self.communication_ok(dev_id, lifx_command)
                except (StandardError, WorkflowException, IOError) as error:
                    self.communication_lost(dev_id, "set_power")
                    return
            elif lifx_command == CMD_BRIGHTNESS and newBrightness > 0 and powerLevel == 0:
                # Need to reset existing brightness to 0 before turning on
                try:
                    hsbkWithBrightnessZero = set_hsbk(hue, saturation, 0, kelvin)
                    self.globals[K_LIFX][dev_id][K_LIFX_DEVICE].set_color(
                        hsbkWithBrightnessZero, 0)
                    self.communication_ok(dev_id, lifx_command)
                except (StandardError, WorkflowException, IOError) as error:
                    self.communication_lost(dev_id, "set_color")
                    return
                # Need to turn on LIFX device as currently off
                powerLevel = 65535
                try:
                    self.globals[K_LIFX][dev_id][K_LIFX_DEVICE].set_power(powerLevel, 0)
                    self.communication_ok(dev_id, lifx_command)
                except (StandardError, WorkflowException, IOError) as error:
                    self.communication_lost(dev_id, "set_power")
                    return

            if lifx_command == CMD_BRIGHTNESS:
                self.globals[K_LIFX][dev_id][K_STOP_REPEAT_BRIGHTEN] = True
                self.globals[K_LIFX][dev_id][K_STOP_REPEAT_DIM] = True
                duration = int(self.globals[K_LIFX][dev_id][K_DURATION_DIM_BRIGHTEN] * 1000)
            else:
                duration = 0

            if saturation > 0:  # check if white or colour (colour if saturation > 0)
                # colour
                if newBrightness > 32768:
                    saturation = int(65535 - ((newBrightness - 32768) * 1.98))
                    brightness = 65535
                else:
                    saturation = 65535
                    brightness = int(newBrightness * 2.0)
            else:
                # White
                brightness = int(newBrightness)

            self.lh_logger.debug(u"LIFX COMMAND [BRIGHTNESS]; SET-COLOR for {0}:"
                                 u" Hue={1}, Saturation={2}, Brightness={3}, Kelvin={4}"
                                 .format(indigo.devices[dev_id].name, hue, saturation,
                                         brightness, kelvin))

            try:
                hsbk = set_hsbk(hue, saturation, brightness, kelvin)
                self.globals[K_LIFX][dev_id][K_LIFX_DEVICE].set_color(hsbk, duration, True)
                self.update_status_from_message(lifx_command, dev_id, powerLevel, hsbk)
                self.communication_ok(dev_id, lifx_command)
            except (StandardError, WorkflowException, IOError) as error:
                self.communication_lost(dev_id, "set_color")
                return

            self.globals[K_LIFX][dev_id][K_LIFX_COMMAND_PREVIOUS] = lifx_command

        except StandardError as standard_error_message:
            self.lh_logger.error(u"StandardError detected in 'process_dim_brighten_brightness'. Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))

    def process_dim_by_timer(self, lifx_command, dev, lifx_command_arguments):
        try:
            dev_id = dev.id

            if lifx_command == CMD_DIM_BY_TIMER:
                # Clear any outstanding timers
                self.clear_dim_by_timer_timer(dev)
                self.globals[K_LIFX][dev_id][K_STOP_REPEAT_DIM] = False
                self.globals[K_LIFX][dev_id][K_STOP_REPEAT_BRIGHTEN] = True

            if not self.globals[K_LIFX][dev_id][K_STOP_REPEAT_DIM]:
                option = lifx_command_arguments[0]
                amountToDimBy = lifx_command_arguments[1]
                timerInterval = lifx_command_arguments[2]

                if int(dev.states["power_level"]) > 0:
                    if dev.brightness == 0:
                        newBrightness = 0
                    else:
                        newBrightness = dev.brightness - amountToDimBy
                else:
                    if int(dev.states["indigo_brightness"]) > 0:
                        newBrightness = int(dev.states["indigo_brightness"])
                    else:
                        newBrightness = 0

                if newBrightness <= 0:
                    newBrightness = 0
                    dev.updateStateOnServer("brightnessLevel", newBrightness)
                    self.globals[K_LIFX][dev_id][K_STOP_REPEAT_DIM] = True
                    self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put(
                        [QUEUE_PRIORITY_COMMAND_HIGH, CMD_DIM, dev_id, [newBrightness]])
                    self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put(
                        [QUEUE_PRIORITY_COMMAND_HIGH, CMD_OFF, dev_id, None])
                    self.lh_logger.info(u"'{0}' {1}".format(dev.name, "dimmed to off"))
                else:
                    self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put(
                        [QUEUE_PRIORITY_COMMAND_HIGH, CMD_DIM, dev_id, [newBrightness]])
                    dev.updateStateOnServer("brightnessLevel", newBrightness)
                    self.globals[K_DEVICE_TIMERS][dev_id]["BRIGHTEN_DIM_BY_TIMER"] = \
                        threading.Timer(timerInterval,
                                        self.handle_timer_repeating_queued_dim_by_timer_command,
                                        [[dev_id, option, amountToDimBy, timerInterval]])
                    self.globals[K_DEVICE_TIMERS][dev_id]["BRIGHTEN_DIM_BY_TIMER"].start()

        except StandardError as standard_error_message:
            self.lh_logger.error(u"StandardError detected in 'process_dim_by_timer'. Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))

    def process_get_host_firmware(self, lifx_command, dev):
        try:
            dev_id = dev.id

            self.lh_logger.debug(u"Processing {0} for '{1}' ".format(lifx_command, indigo.devices[dev_id].name))

            dev = indigo.devices[dev_id]

            # Clear any outstanding timers
            self.clear_status_timer(dev)

            try:
                firmware_version = str(self.globals[K_LIFX][dev_id][K_LIFX_DEVICE].get_host_firmware_version())
                self.communication_ok(dev_id, lifx_command)
            except (StandardError, WorkflowException, IOError) as error:
                self.communication_lost(dev_id, 'get_host_firmware_version')
                return

            self.lh_logger.debug(
                u"HOST FIRMWARE VERSION for '{0}': '{1}'".format(indigo.devices[dev_id].name, firmware_version))

            props = dev.pluginProps

            if 'version' in props:
                version = str(props["version"]).split('|')
            else:
                props["version"] = ''
                version = ["_"]

            if len(version) > 1:
                if firmware_version == version[1]:
                    newVersion = firmware_version
                else:
                    newVersion = firmware_version + '|' + version[1]
            else:
                newVersion = firmware_version

            if props["version"] != newVersion:
                props["version"] = newVersion
                dev.replacePluginPropsOnServer(props)

            self.globals[K_LIFX][dev_id][K_LIFX_COMMAND_PREVIOUS] = lifx_command

        except StandardError as standard_error_message:
            self.lh_logger.error(u"StandardError detected in 'process_get_host_firmware'. Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))

    def process_get_host_info(self, lifx_command, dev, lifx_command_arguments):
        try:
            self.lh_logger.debug(u"Processing {0}".format(lifx_command))

        except StandardError as standard_error_message:
            self.lh_logger.error(u"StandardError detected in 'process_get_host_info'. Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))

    def process_get_group(self, lifx_command, dev, lifx_command_arguments):
        try:
            self.lh_logger.debug(u"Processing {0}".format(lifx_command))

        except StandardError as standard_error_message:
            self.lh_logger.error(u"StandardError detected in 'process_get_group'. Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))

    def process_get_info(self, lifx_command, dev, lifx_command_arguments):
        try:
            self.lh_logger.debug(u"Processing {0}".format(lifx_command))

        except StandardError as standard_error_message:
            self.lh_logger.error(u"StandardError detected in 'process_get_info'. Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))

    def process_get_location(self, lifx_command, dev, lifx_command_arguments):
        try:
            self.lh_logger.debug(u"Processing {0}".format(lifx_command))

        except StandardError as standard_error_message:
            self.lh_logger.error(u"StandardError detected in 'process_get_location'. Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))

    def process_get_port(self, lifx_command, dev):
        try:
            dev_id = dev.id

            self.lh_logger.debug(u"Processing {0} for '{1}' ".format(lifx_command, indigo.devices[dev_id].name))

            # Clear any outstanding timers
            self.clear_status_timer(dev)

            try:
                port = str(self.globals[K_LIFX][dev_id][K_LIFX_DEVICE].get_port())
                self.communication_ok(dev_id, lifx_command)
            except (StandardError, WorkflowException, IOError) as error:
                self.communication_lost(dev_id, 'get_port')
                return

            self.lh_logger.info(u"Port for '{0}': '{1}'".format(indigo.devices[dev_id].name, port))

            # props = dev.pluginProps

            # if 'version' in props:
            #     version = str(props["version"]).split('|')
            # else:
            #     props["version"] = ''
            #     version = [wifi_firmware_version]

            # if len(version) > 0:
            #     if wifi_firmware_version == version[0]:  # i.e. Firmware and wifi versions are the same
            #         newVersion = wifi_firmware_version
            #     else:
            #         newVersion = str(version[0]) + '|' + wifi_firmware_version
            # else:
            #     newVersion = '_|' + wifi_firmware_version

            # if props["version"] != newVersion:
            #     props["version"] = newVersion
            #     dev.replacePluginPropsOnServer(props)

            self.globals[K_LIFX][dev_id][K_LIFX_COMMAND_PREVIOUS] = lifx_command

        except StandardError as standard_error_message:
            self.lh_logger.error(u"StandardError detected in 'process_get_port'. Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))

    def process_get_version(self, lifx_command, dev):
        try:
            dev_id = dev.id

            self.lh_logger.debug(u"Processing {0} for '{1}' ".format(lifx_command, indigo.devices[dev_id].name))

            # Clear any outstanding timers
            self.clear_status_timer(dev)

            try:
                product = self.globals[K_LIFX][dev_id][K_LIFX_DEVICE].get_product()
                self.communication_ok(dev_id, lifx_command)
            except (StandardError, WorkflowException, IOError) as error:
                self.communication_lost(dev_id, 'get_product')
                return

            self.lh_logger.debug(u"PRODUCT for '{0}' = '{1}'".format(indigo.devices[dev_id].name, product))

            productFound = False
            try:
                model = u"{0}".format(LIFX_PRODUCTS[product][LIFX_PRODUCT_NAME])  # Defined in constants.py
                productFound = True
            except KeyError:
                model = u"LIFX Product - {0}".format(product)

            if dev.model != model:
                dev.model = model
                dev.replaceOnServer()

            if productFound:
                props = dev.pluginProps
                propsChanged = False
                if ("SupportsColor" not in props) or (
                        props["SupportsColor"] != bool(LIFX_PRODUCTS[product][LIFX_PRODUCT_SUPPORTS_COLOR])):
                    props["SupportsColor"] = True  # Applies even if just able to change White Levels / Temperature
                    props["SupportsRGB"] = bool(LIFX_PRODUCTS[product][LIFX_PRODUCT_SUPPORTS_COLOR])
                    propsChanged = True
                if ("SupportsRGB" not in props) or (
                        props["SupportsRGB"] != bool(LIFX_PRODUCTS[product][LIFX_PRODUCT_SUPPORTS_COLOR])):
                    props["SupportsRGB"] = bool(LIFX_PRODUCTS[product][LIFX_PRODUCT_SUPPORTS_COLOR])
                    propsChanged = True
                if ("supports_infrared" not in props) or (
                        props["supports_infrared"] != bool(LIFX_PRODUCTS[product][LIFX_PRODUCT_SUPPORTS_INFRARED])):
                    props["supports_infrared"] = bool(LIFX_PRODUCTS[product][LIFX_PRODUCT_SUPPORTS_INFRARED])
                    propsChanged = True
                if ("SupportsMultizone" not in props) or (props["SupportsMultizone"] != bool(
                        LIFX_PRODUCTS[product][LIFX_PRODUCT_SUPPORTS_MULTIZONE])):
                    props["SupportsMultizone"] = bool(LIFX_PRODUCTS[product][LIFX_PRODUCT_SUPPORTS_MULTIZONE])
                    propsChanged = True
                if propsChanged:
                    dev.replacePluginPropsOnServer(props)

            self.globals[K_LIFX][dev_id][K_LIFX_COMMAND_PREVIOUS] = lifx_command

        except StandardError as standard_error_message:
            self.lh_logger.error(u"StandardError detected in 'process_get_version'. Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))

    def process_get_wifi_firmware(self, lifx_command, dev, lifx_command_arguments):
        try:
            dev_id = dev.id

            self.lh_logger.debug(u"Processing {0} for '{1}' ".format(lifx_command, indigo.devices[dev_id].name))

            dev = indigo.devices[dev_id]

            # Clear any outstanding timers
            self.clear_status_timer(dev)

            try:
                wifi_firmware_version = str(self.globals[K_LIFX][dev_id][K_LIFX_DEVICE].get_wifi_firmware_version())
                self.communication_ok(dev_id, lifx_command)
            except (StandardError, WorkflowException, IOError) as error:
                self.communication_lost(dev_id, 'get_wifi_firmware_version')
                return

            self.lh_logger.debug(u"WI-FI FIRMWARE VERSION for '{0}': '{1}'".format(indigo.devices[dev_id].name,
                                                                                   wifi_firmware_version))

            props = dev.pluginProps

            if 'version' in props:
                version = str(props["version"]).split('|')
            else:
                props["version"] = ''
                version = [wifi_firmware_version]

            if len(version) > 0:
                if wifi_firmware_version == version[0]:  # i.e. Firmware and wifi versions are the same
                    newVersion = wifi_firmware_version
                else:
                    newVersion = str(version[0]) + '|' + wifi_firmware_version
            else:
                newVersion = '_|' + wifi_firmware_version

            if props["version"] != newVersion:
                props["version"] = newVersion
                dev.replacePluginPropsOnServer(props)

            self.globals[K_LIFX][dev_id][K_LIFX_COMMAND_PREVIOUS] = lifx_command

        except StandardError as standard_error_message:
            self.lh_logger.error(u"StandardError detected in 'process_get_wifi_firmware'. Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))

    def process_get_wifi_info(self, lifx_command, dev):
        try:
            dev_id = dev.id

            self.lh_logger.debug(u"Processing {0} for '{1}' ".format(lifx_command, indigo.devices[dev_id].name))

            # Clear any outstanding timers
            self.clear_status_timer(dev)

            try:
                signal, tx, rx = self.globals[K_LIFX][dev_id][K_LIFX_DEVICE].get_wifi_info_tuple()
                self.communication_ok(dev_id, lifx_command)
            except (StandardError, WorkflowException, IOError) as error:
                self.communication_lost(dev_id, 'get_wifi_info_tuple')
                return

            self.lh_logger.debug(
                u"WI-FI INFO [1] for '{0}': Signal={1}, Tx={2}, Rx={3}".format(indigo.devices[dev_id].name, signal,
                                                                               tx, rx))
            if signal is not None:
                signal = str('{:.16f}'.format(signal))[0:12]
            locale.setlocale(locale.LC_ALL, 'en_US')
            if tx is not None:
                tx = locale.format("%d", tx, grouping=True)
            if rx is not None:
                rx = locale.format("%d", rx, grouping=True)

            self.lh_logger.debug(
                u"WI-FI INFO [2] for '{0}': Signal={1}, Tx={2}, Rx={3}".format(indigo.devices[dev_id].name, signal,
                                                                               tx, rx))

            keyValueList = [
                {"key": "wifi_signal", "value": signal},
                {"key": "wifi_tx", "value": tx},
                {"key": "wifi_rx", "value": rx}
            ]
            dev.updateStatesOnServer(keyValueList)

            self.globals[K_LIFX][dev_id][K_LIFX_COMMAND_PREVIOUS] = lifx_command

        except StandardError as standard_error_message:
            self.lh_logger.error(u"StandardError detected in 'process_get_wifi_info'. Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))

    def process_infrared(self, lifx_command, dev, lifx_command_arguments):
        try:
            dev_id = dev.id

            self.lh_logger.debug(u"Processing {0} for '{1}' "
                                 .format(lifx_command, indigo.devices[dev_id].name))

            dev = indigo.devices[dev_id]

            # Clear any outstanding timers
            self.clear_status_timer(dev)

            infraredBrightness = 0
            if lifx_command == CMD_INFRARED_OFF:
                infraredBrightness = 0
            elif lifx_command == CMD_INFRARED_ON:
                infraredBrightness = 65535
            elif lifx_command == CMD_INFRARED_SET:
                infraredBrightness = lifx_command_arguments[0]
                infraredBrightness = int((infraredBrightness * 65535.0) / 100.0)
                if infraredBrightness > 65535:
                    infraredBrightness = 65535  # Just in case ;)

            try:
                self.globals[K_LIFX][dev_id][K_LIFX_DEVICE].set_infrared(infraredBrightness)
                self.lh_logger.debug(u"Processing {0} for '{1}'; Infrared Brightness = {2}"
                                     .format(lifx_command, indigo.devices[dev_id].name, infraredBrightness))
                self.communication_ok(dev_id, lifx_command)
            except (StandardError, WorkflowException, IOError):
                self.communication_lost(dev_id, "set_infrared")
                return

            self.globals[K_DEVICE_TIMERS][dev_id][K_STATUS] = \
                threading.Timer(1.0, self.handle_timer_repeating_queued_status_command, [dev, 2])
            self.globals[K_DEVICE_TIMERS][dev_id][K_STATUS].start()

            self.globals[K_LIFX][dev_id][K_LIFX_COMMAND_PREVIOUS] = lifx_command

        except StandardError as standard_error_message:
            self.lh_logger.error(u"StandardError detected in 'process_infrared'. Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))

    def process_on_off(self, lifx_command, dev):
        try:
            dev_id = dev.id

            # Stop any background timer brighten or dim operation
            self.globals[K_LIFX][dev_id][K_STOP_REPEAT_DIM] = True
            self.globals[K_LIFX][dev_id][K_STOP_REPEAT_BRIGHTEN] = True

            self.lh_logger.debug(u"Processing {0} for '{1}' ".format(lifx_command, indigo.devices[dev_id].name))

            dev = indigo.devices[dev_id]

            # Clear any outstanding timers
            self.clear_status_timer(dev)

            if lifx_command == CMD_ON:
                duration = float(self.globals[K_LIFX][dev_id][K_DURATION_ON])
                power = 65535
            elif lifx_command == CMD_IMMEDIATE_ON:
                duration = 0
                power = 65535
            elif lifx_command == CMD_OFF:
                duration = float(self.globals[K_LIFX][dev_id][K_DURATION_OFF])
                power = 0
            else:
                duration = 0
                power = 0
            timer_duration = duration
            duration = int(duration * 1000)
            try:
                self.globals[K_LIFX][dev_id][K_LIFX_DEVICE].set_power(power, duration)
                self.communication_ok(dev_id, lifx_command)
            except WorkflowException:
                self.communication_lost(dev_id, "set_power")
                return

            self.globals[K_DEVICE_TIMERS][dev_id][K_STATUS] = \
                threading.Timer(1.0,
                                self.handle_timer_repeating_queued_status_command,
                                [dev, timer_duration])
            self.globals[K_DEVICE_TIMERS][dev_id][K_STATUS].start()

            self.globals[K_LIFX][dev_id][K_LIFX_COMMAND_PREVIOUS] = lifx_command

        except StandardError as standard_error_message:
            self.lh_logger.error(u"StandardError detected in 'process_on_off'. Line {0} has error: {1}".format(
                sys.exc_traceback.tb_lineno, standard_error_message))

    def process_set_label(self, lifx_command, dev):
        try:
            dev_id = dev.id

            self.lh_logger.debug(u"Processing {0} for '{1}' ".format(lifx_command, indigo.devices[dev_id].name))

            dev = indigo.devices[dev_id]

            # Clear any outstanding timers
            self.clear_status_timer(dev)

            try:
                self.globals[K_LIFX][dev_id][K_LIFX_DEVICE].set_label(dev.name)
                self.communication_ok(dev_id, lifx_command)
            except (StandardError, WorkflowException, IOError) as error:
                self.communication_lost(dev_id, 'set_label')

            self.globals[K_LIFX][dev_id][K_LIFX_COMMAND_PREVIOUS] = lifx_command

        except StandardError as standard_error_message:
            self.lh_logger.error(u"StandardError detected in 'process_set_label'. Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))

    def process_standard(self, lifx_command, dev, lifx_command_arguments):
        try:
            dev_id = dev.id

            # Stop any background timer brighten or dim operation
            self.globals[K_LIFX][dev_id][K_STOP_REPEAT_DIM] = True
            self.globals[K_LIFX][dev_id][K_STOP_REPEAT_BRIGHTEN] = True

            turnOnIfOff, targetMode, targetHue, targetSaturation, \
                targetBrightness, targetKelvin, targetDuration = lifx_command_arguments

            self.lh_logger.debug(u"LIFX COMMAND [STANDARD]; Target for {0}: TOIF={1}, Mode={2}, Hue={3},"
                                 u" Saturation={4}, Brightness={5}, Kelvin={6}, Duration={7}"
                                 .format(indigo.devices[dev_id].name, turnOnIfOff, targetMode, targetHue,
                                         targetSaturation, targetBrightness, targetKelvin, targetDuration))

            # Clear any outstanding timers
            self.clear_status_timer(dev)

            lifx_io_ok, power, hsbk = self.get_color(dev_id, self.globals[K_LIFX][dev_id][K_LIFX_DEVICE])
            self.lh_logger.debug(u"LIFX COMMAND [COLOR] lifx_io_ok for {0} =  {1}, HSBK = {2}".format(
                indigo.devices[dev_id].name, lifx_io_ok, hsbk))
            if lifx_io_ok:
                hue = hsbk[0]
                saturation = hsbk[1]
                brightness = hsbk[2]
                kelvin = hsbk[3]

                self.lh_logger.debug(u"LIFX COMMAND [COLOR]; GET-COLOR for {0}:"
                                     u" Hue={1}, Saturation={2}, Brightness={3}, Kelvin={4}"
                                     .format(indigo.devices[dev_id].name, hue, saturation, brightness, kelvin))

                if targetMode == 'White':
                    saturation = 0  # Force WHITE mode
                    if targetKelvin != '-':
                        kelvin = int(targetKelvin)
                else:
                    # Assume 'Color'
                    if targetHue != '-':
                        hue = int((float(targetHue) * 65535.0) / 360.0)
                    if targetSaturation != '-':
                        saturation = int((float(targetSaturation) * 65535.0) / 100.0)
                if targetBrightness != '-':
                    brightness = int((float(targetBrightness) * 65535.0) / 100.0)

                if targetDuration != '-':
                    duration = int(float(targetDuration) * 1000)
                else:
                    duration = int(self.globals[K_LIFX][dev_id][K_DURATION_COLOR_WHITE] * 1000)

                self.lh_logger.debug(u"LIFX COMMAND [STANDARD][{0}]; SET-COLOR for {1}:"
                                     u" Hue={2}, Saturation={3}, Brightness={4}, Kelvin={5}, duration={6}"
                                     .format(targetMode, indigo.devices[dev_id].name, hue, saturation,
                                             brightness, kelvin, duration))

                if power == 0 and turnOnIfOff:
                    try:
                        hsbk = set_hsbk(hue, saturation, brightness, kelvin)
                        self.globals[K_LIFX][dev_id][K_LIFX_DEVICE].set_color(hsbk, 0)
                        self.communication_ok(dev_id, lifx_command)
                    except (StandardError, WorkflowException, IOError) as error:
                        self.communication_lost(dev_id, 'set_color')
                        return
                    power = 65535
                    try:
                        self.globals[K_LIFX][dev_id][K_LIFX_DEVICE].set_power(power, duration)
                        self.communication_ok(dev_id, lifx_command)
                    except (StandardError, WorkflowException, IOError) as error:
                        self.communication_lost(dev_id, 'set_power')
                        return
                else:
                    if power == 0:
                        duration = 0  # As power is off. might as well do apply command straight away
                    try:
                        hsbk = set_hsbk(hue, saturation, brightness, kelvin)
                        self.globals[K_LIFX][dev_id][K_LIFX_DEVICE].set_color(hsbk, duration)
                        self.communication_ok(dev_id, lifx_command)
                    except (StandardError, WorkflowException, IOError) as error:
                        self.communication_lost(dev_id, 'set_color')
                        return

                timer_duration = int(duration / 1000)  # Convert back from milliseconds
                self.globals[K_DEVICE_TIMERS][dev_id][K_STATUS] = \
                    threading.Timer(1.0, self.handle_timer_repeating_queued_status_command, [dev, timer_duration])

                self.globals[K_DEVICE_TIMERS][dev_id][K_STATUS].start()

            self.globals[K_LIFX][dev_id][K_LIFX_COMMAND_PREVIOUS] = lifx_command

        except StandardError as standard_error_message:
            self.lh_logger.error(u"StandardError detected in 'process_standard'. Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))

    def process_status(self, lifx_command, dev):
        try:
            dev_id = dev.id

            if not dev.states["discovered"]:
                # if not dev.states["no_ack_state"]:
                # if not dev.states["connected"]:
                self.globals[K_LIFX][dev_id][K_CONNECTED] = False
                dev.updateStateOnServer(key="connected", value=False)
                self.handle_no_ack_status(dev)

            if self.globals[K_LIFX][dev_id][K_LIFX_DEVICE] is None:
                self.lh_logger.debug(u"PROCESS STATUS: K_LIFX_DEVICE is None for device '{0}'".format(dev.name))
                lifx_ip_address = dev.pluginProps["ip_address"]
                self.globals[K_LIFX][dev_id][K_LIFX_DEVICE] = Light(dev.address, lifx_ip_address)
                try:
                    self.globals[K_LIFX][dev_id][K_LIFX_DEVICE].refresh()
                    refreshed = True
                except (StandardError, WorkflowException):
                    refreshed = False
                if refreshed:
                    indigo.device.enable(dev_id, value=False)
                    indigo.device.enable(dev_id, value=True)
                else:
                    self.globals[K_LIFX][dev_id][K_LIFX_DEVICE] = None
                    if lifx_command == CMD_RECOVERY_STATUS:
                        self.lh_logger.debug(u"Unable to reconnect to LIFX device '{0}'".format(dev.name))
                return

            lifx_io_ok, power, hsbk = \
                self.get_color(dev_id, self.globals[K_LIFX][dev_id][K_LIFX_DEVICE])
            if lifx_io_ok:
                self.update_status_from_message(lifx_command, dev_id, power, hsbk)

                props = dev.pluginProps
                if ("supports_infrared" in props) and props["supports_infrared"]:
                    lifx_io_ok, infrared_brightness = \
                        self.get_infrared(dev_id,
                                          self.globals[K_LIFX][dev_id][K_LIFX_DEVICE])
                    if lifx_io_ok:
                        try:
                            indigo_infrared_brightness = float((infrared_brightness * 100) / 65535)
                            keyValueList = [
                                {"key": "infrared_brightness", "value": infrared_brightness},
                                {"key": "indigo_infrared_brightness", "value": indigo_infrared_brightness}]
                            dev.updateStatesOnServer(keyValueList)

                            self.lh_logger.debug(u"LifxlanHandler Infrared Level for '{0}' is: {1}"
                                                 .format(dev.name, indigo_infrared_brightness))

                        except (StandardError, WorkflowException, IOError) as standard_error_message:

                            self.lh_logger.error(u"StandardError detected communicating with LIFX lamp '{0}'."
                                                 u" Line {1} has error: {2}"
                                                 .format(dev.name, sys.exc_traceback.tb_lineno, standard_error_message))

            self.globals[K_LIFX][dev_id][K_LIFX_COMMAND_PREVIOUS] = lifx_command

        except StandardError as standard_error_message:
            self.lh_logger.error(u"StandardError detected in 'process_status' for LIFX device '{0}. Line {1} has error: {2}"
                                 .format(dev.name, sys.exc_traceback.tb_lineno, standard_error_message))

    def process_waveform(self, lifx_command, dev, lifx_command_arguments):
        try:
            dev_id = dev.id

            # Stop any background timer brighten or dim operation
            self.globals[K_LIFX][dev_id][K_STOP_REPEAT_DIM] = True
            self.globals[K_LIFX][dev_id][K_STOP_REPEAT_BRIGHTEN] = True

            targetMode, targetHue, targetSaturation, targetBrightness, targetKelvin, \
                targetTransient, targetPeriod, targetCycles, targetDuty_cycle, targetWaveform = lifx_command_arguments

            # Clear any outstanding timers
            self.clear_status_timer(dev)
            self.clear_waveform_off_timer(dev)

            lifx_io_ok, power, hsbk = self.get_color(dev_id, self.globals[K_LIFX][dev_id][K_LIFX_DEVICE])
            self.lh_logger.debug(u"LIFX COMMAND [COLOR] lifx_io_ok for {0} =  {1}, HSBK = {2}".format(
                indigo.devices[dev_id].name, lifx_io_ok, hsbk))
            if lifx_io_ok:
                hue = hsbk[0]
                saturation = hsbk[1]
                brightness = hsbk[2]
                kelvin = hsbk[3]

                self.lh_logger.debug(u"LIFX COMMAND [COLOR]; GET-COLOR for {0}:"
                                     u" Hue={1}, Saturation={2}, Brightness={3}, Kelvin={4}"
                                     .format(indigo.devices[dev_id].name, hue, saturation, brightness, kelvin))

                deviceAlreadyOn = True
                if power == 0:
                    deviceAlreadyOn = False
                    duration = 0
                    power = 65535
                    duration = int(duration * 1000)
                    try:
                        self.globals[K_LIFX][dev_id][K_LIFX_DEVICE].set_power(power, duration)
                        self.communication_ok(dev_id, lifx_command)
                    except (StandardError, WorkflowException, IOError) as error:
                        self.communication_lost(dev_id, 'set_power')
                        return

                if targetMode == 'White':
                    saturation = 0  # Force WHITE mode
                    if targetKelvin != '-':
                        kelvin = int(kelvin)
                else:
                    # Assume 'COLOR'
                    if targetHue != '-':
                        hue = int((float(targetHue) * 65535.0) / 360.0)
                    if targetSaturation != '-':
                        saturation = int((float(targetSaturation) * 65535.0) / 100.0)
                if targetBrightness != '-':
                    brightness = int((float(targetBrightness) * 65535.0) / 100.0)
                hsbk = set_hsbk(hue, saturation, brightness, kelvin)

                if targetTransient:
                    transient = int(1)
                else:
                    transient = int(0)
                period = int(targetPeriod)
                cycles = float(targetCycles)
                duty_cycle = int(targetDuty_cycle)
                waveform = int(targetWaveform)

                self.lh_logger.debug(u"LIFX COMMAND [WAVEFORM]; SET-WAVEFORM for {0}:"
                                     u" Hue={1}, Saturation={2}, Brightness={3}, Kelvin={4}"
                                     .format(indigo.devices[dev_id].name, hue, saturation, brightness, kelvin))
                self.lh_logger.debug(u"LIFX COMMAND [WAVEFORM]; SET-WAVEFORM for {0}:"
                                     u" Transient={1}, Period={2}, Cycles={3}, Duty_cycle={4}, Waveform={5}"
                                     .format(indigo.devices[dev_id].name,
                                             transient, period, cycles, duty_cycle, waveform))

                try:
                    self.globals[K_LIFX][dev_id][K_LIFX_DEVICE].set_waveform(
                        transient, hsbk, period, cycles, duty_cycle, waveform)
                    self.communication_ok(dev_id, lifx_command)
                except (StandardError, WorkflowException, IOError) as error:
                    self.communication_lost(dev_id, 'set_waveform')
                    return

                if not deviceAlreadyOn:
                    timerSetFor = float((float(period) / 1000.0) * cycles)
                    self.globals[K_DEVICE_TIMERS][dev_id]["WAVEFORM_OFF"] = \
                        threading.Timer(timerSetFor, self.handle_timer_waveform_off_command, [dev])
                    self.globals[K_DEVICE_TIMERS][dev_id]["WAVEFORM_OFF"].start()

            self.globals[K_LIFX][dev_id][K_LIFX_COMMAND_PREVIOUS] = lifx_command

        except StandardError as standard_error_message:
            self.lh_logger.error(u"StandardError detected in 'process_waveform'. Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))

    def process_white(self, lifx_command, dev, lifx_command_arguments):
        try:
            dev_id = dev.id

            # Stop any background timer brighten or dim operation
            self.globals[K_LIFX][dev_id][K_STOP_REPEAT_DIM] = True
            self.globals[K_LIFX][dev_id][K_STOP_REPEAT_BRIGHTEN] = True

            targetWhiteLevel, targetWhiteTemperature = lifx_command_arguments

            # Clear any outstanding timers
            self.clear_status_timer(dev)

            lifx_io_ok, power, hsbk = \
                self.get_color(dev_id,
                               self.globals[K_LIFX][dev_id][K_LIFX_DEVICE])

            self.lh_logger.debug(u"LIFX COMMAND [WHITE] lifx_io_ok for {0} =  {1}, HSBK = {2}"
                                 .format(indigo.devices[dev_id].name, lifx_io_ok, hsbk))
            if lifx_io_ok:
                hue = hsbk[0]
                saturation = hsbk[1]
                brightness = hsbk[2]
                kelvin = hsbk[3]

                self.lh_logger.debug(u"LIFX COMMAND [WHITE]; GET-COLOR for {0}: Hue={1},"
                                     u" Saturation={2}, Brightness={3}, Kelvin={4}"
                                     .format(indigo.devices[dev_id].name, hue, saturation,
                                             brightness, kelvin))

                if power == 0 and self.globals[K_LIFX][dev_id]["turn_on_if_off"]:
                    # Need to reset existing brightness to 0 before turning on
                    try:
                        hsbkWithBrightnessZero = set_hsbk(hue, saturation, 0, kelvin)
                        self.globals[K_LIFX][dev_id][K_LIFX_DEVICE].set_color(
                            hsbkWithBrightnessZero, 0)
                    except (StandardError, WorkflowException, IOError) as error:
                        self.communication_lost(dev_id, "set_color")
                        return
                    # Need to turn on LIFX device as currently off
                    power = 65535
                    try:
                        self.globals[K_LIFX][dev_id][K_LIFX_DEVICE].set_power(power, 0)
                        self.communication_ok(dev_id, lifx_command)
                    except (StandardError, WorkflowException, IOError) as error:
                        self.communication_lost(dev_id, "set_power")
                        return

                saturation = 0
                brightness = int((targetWhiteLevel * 65535.0) / 100.0)
                kelvin = int(targetWhiteTemperature)
                duration = int(self.globals[K_LIFX][dev_id][K_DURATION_COLOR_WHITE] * 1000)

                self.lh_logger.debug(u"LIFX COMMAND [WHITE]; SET-COLOR for {0}:"
                                     u" Hue={1}, Saturation={2}, Brightness={3}, Kelvin={4}"
                                     .format(indigo.devices[dev_id].name, hue, saturation,
                                             brightness, kelvin))

                try:
                    hsbk = set_hsbk(hue, saturation, brightness, kelvin)
                    self.globals[K_LIFX][dev_id][K_LIFX_DEVICE].set_color(hsbk, duration)
                    self.communication_ok(dev_id, lifx_command)
                except (StandardError, WorkflowException, IOError) as error:
                    self.communication_lost(dev_id, "set_color")
                    return

                timer_duration = int(self.globals[K_LIFX][dev_id][K_DURATION_COLOR_WHITE])
                self.globals[K_DEVICE_TIMERS][dev_id][K_STATUS] = \
                    threading.Timer(1.0,
                                    self.handle_timer_repeating_queued_status_command,
                                    [dev, timer_duration])

                self.globals[K_DEVICE_TIMERS][dev_id][K_STATUS].start()

            self.globals[K_LIFX][dev_id][K_LIFX_COMMAND_PREVIOUS] = lifx_command

        except StandardError as standard_error_message:
            self.lh_logger.error(u"StandardError detected in 'process_white'. Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))

    def update_status_from_message(self, lifxCommand, dev_id, power, hsbk):
        try:
            dev = indigo.devices[dev_id]

            hue, saturation, brightness, kelvin = hsbk
            self.lh_logger.debug(u"HANDLE '{0}' MESSAGE for {1}:"
                                 u" Power={2}, Hue={3}, Saturation={4}, Brightness={5}, Kelvin={6}"
                                 .format(lifxCommand, indigo.devices[dev_id].name, power, hue, saturation,
                                         brightness, kelvin))

            if power > 0:
                self.globals[K_LIFX][dev_id]["onState"] = True
                self.globals[K_LIFX][dev_id]["onOffState"] = "on"
            else:
                self.globals[K_LIFX][dev_id]["onState"] = False
                self.globals[K_LIFX][dev_id]["onOffState"] = "off"
            self.globals[K_LIFX][dev_id]["powerLevel"] = power

            # Color [0-7]: HSBK
            # Reserved [8-9]: signed 16-bit integer
            # Power [10-11]: unsigned 16-bit integer
            # Label [12-43]: string, size=32 bytes
            # Reserved [44-51]: unsigned 64-bit integer
            self.globals[K_LIFX][dev_id]["hsbkHue"] = hue
            self.globals[K_LIFX][dev_id]["hsbkSaturation"] = saturation
            self.globals[K_LIFX][dev_id]["hsbkBrightness"] = brightness
            self.globals[K_LIFX][dev_id]["hsbkKelvin"] = kelvin

            self.lh_logger.debug(u"  LIGHT_STATE = Power: {0}".format(self.globals[K_LIFX][dev_id]["powerLevel"]))
            self.lh_logger.debug(u"  LIGHT_STATE = onState: {0}".format(self.globals[K_LIFX][dev_id]["onState"]))
            self.lh_logger.debug(u"  LIGHT_STATE = onOffState: {0}".format(self.globals[K_LIFX][dev_id]["onOffState"]))

            # At this point we have an Indigo device id for the lamp
            #   and can confirm that the indigo device has been started

            # Set the current poll count (for 'no ack' check)
            # self.globals[K_LIFX][dev_id]["lastResponseToPollCount"] = self.globals[K_POLLING][K_COUNT]
            # self.lh_logger.debug(u"LAST RESPONSE TO POLL COUNT for {0} = {1}"
            #                      .format(dev.name, self.globals[K_POLLING][K_COUNT]))

            self.globals[K_LIFX][dev_id]["initialisedFromlamp"] = True

            if self.globals[K_LIFX][dev_id]["onState"]:
                self.globals[K_LIFX][dev_id]["whenLastOnHsbkHue"] = \
                    self.globals[K_LIFX][dev_id]["hsbkHue"]  # Value between 0 and 65535
                self.globals[K_LIFX][dev_id]["whenLastOnHsbkSaturation"] = \
                    self.globals[K_LIFX][dev_id]["hsbkSaturation"]  # Value between 0 and 65535 (e.g. 20% = 13107)
                self.globals[K_LIFX][dev_id]["whenLastOnHsbkBrightness"] = \
                    self.globals[K_LIFX][dev_id]["hsbkBrightness"]  # Value between 0 and 65535
                self.globals[K_LIFX][dev_id]["whenLastOnHsbkKelvin"] = \
                    self.globals[K_LIFX][dev_id]["hsbkKelvin"]  # Value between 2500 and 9000
                self.globals[K_LIFX][dev_id]["whenLastOnPowerLevel"] = \
                    self.globals[K_LIFX][dev_id]["powerLevel"]  # Value between 0 and 65535

            try:
                self.globals[K_LIFX][dev_id]["indigoHue"] = \
                    float((self.globals[K_LIFX][dev_id]["hsbkHue"] * 360) / 65535)  # Bug Fix 2016-07-09
            except ValueError:
                self.globals[K_LIFX][dev_id]["indigoHue"] = float(0)
            try:
                self.globals[K_LIFX][dev_id]["indigoSaturation"] = \
                    float((self.globals[K_LIFX][dev_id]["hsbkSaturation"] * 100) / 65535)
            except ValueError:
                self.globals[K_LIFX][dev_id]["indigoSaturation"] = float(0)
            try:
                self.globals[K_LIFX][dev_id]["indigoBrightness"] = \
                    float((self.globals[K_LIFX][dev_id]["hsbkBrightness"] * 100) / 65535)
            except ValueError:
                self.globals[K_LIFX][dev_id]["indigoBrightness"] = float(0)
            try:
                self.globals[K_LIFX][dev_id]["indigoKelvin"] = float(self.globals[K_LIFX][dev_id]["hsbkKelvin"])
            except ValueError:
                self.globals[K_LIFX][dev_id]["indigoKelvin"] = float(3500)
            try:
                self.globals[K_LIFX][dev_id]["indigoPowerLevel"] = \
                    float((self.globals[K_LIFX][dev_id]["powerLevel"] * 100) / 65535)
            except ValueError:
                self.globals[K_LIFX][dev_id]["indigoPowerLevel"] = float(0)

            hsv_hue = float(self.globals[K_LIFX][dev_id]["hsbkHue"]) / 65535.0
            hsv_value = float(self.globals[K_LIFX][dev_id]["hsbkBrightness"]) / 65535.0
            hsv_saturation = float(self.globals[K_LIFX][dev_id]["hsbkSaturation"]) / 65535.0
            red, green, blue = colorsys.hsv_to_rgb(hsv_hue, hsv_saturation, hsv_value)

            self.globals[K_LIFX][dev_id]["indigoRed"] = float(red * 100.0)
            self.globals[K_LIFX][dev_id]["indigoGreen"] = float(green * 100.0)
            self.globals[K_LIFX][dev_id]["indigoBlue"] = float(blue * 100.0)

            # Set brightness according to LIFX Lamp on/off state - if 'on' use the LIFX Lamp state else set to zero
            if self.globals[K_LIFX][dev_id]["onState"]:
                # check if white or colour (colour if saturation > 0.0)
                if self.globals[K_LIFX][dev_id]["indigoSaturation"] > 0.0:
                    # Colour
                    saturation = hsv_saturation * 100.0
                    brightness = hsv_value * 100.0
                    calculatedBrightnessLevel = float(calculate_brightness_level_from_sv(saturation, brightness))
                    self.globals[K_LIFX][dev_id]["brightnessLevel"] = \
                        int(calculatedBrightnessLevel * (self.globals[K_LIFX][dev_id]["powerLevel"] / 65535.0))
                else:
                    # White
                    self.globals[K_LIFX][dev_id]["brightnessLevel"] = \
                        int(self.globals[K_LIFX][dev_id]["indigoBrightness"] *
                            (self.globals[K_LIFX][dev_id]["powerLevel"] / 65535.0))
                    self.globals[K_LIFX][dev_id]["indigoWhiteLevel"] = \
                        float(self.globals[K_LIFX][dev_id]["indigoBrightness"])
            else:
                self.globals[K_LIFX][dev_id]["brightnessLevel"] = 0

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
                {"key": "when_last_on_hsbk_saturation",
                 "value": self.globals[K_LIFX][dev_id]["whenLastOnHsbkSaturation"]},
                {"key": "when_last_on_hsbk_brightness",
                 "value": self.globals[K_LIFX][dev_id]["whenLastOnHsbkBrightness"]},
                {"key": "when_last_on_hsbk_kelvin", "value": self.globals[K_LIFX][dev_id]["whenLastOnHsbkKelvin"]},
                {"key": "when_last_on_power_level", "value": self.globals[K_LIFX][dev_id]["whenLastOnPowerLevel"]},

                {"key": "indigo_hue", "value": self.globals[K_LIFX][dev_id]["indigoHue"]},
                {"key": "indigo_saturation", "value": self.globals[K_LIFX][dev_id]["indigoSaturation"]},
                {"key": "indigo_brightness", "value": self.globals[K_LIFX][dev_id]["indigoBrightness"]},
                {"key": "indigo_kelvin", "value": self.globals[K_LIFX][dev_id]["indigoKelvin"]},
                {"key": "indigo_power_level", "value": self.globals[K_LIFX][dev_id]["indigoPowerLevel"]},

                {"key": "brightnessLevel",
                 "value": int(self.globals[K_LIFX][dev_id]["brightnessLevel"]),
                 "uiValue": str(self.globals[K_LIFX][dev_id]["brightnessLevel"])},

                {"key": "whiteLevel",
                 "value": int(self.globals[K_LIFX][dev_id]["brightnessLevel"]),
                 "uiValue": str(self.globals[K_LIFX][dev_id]["brightnessLevel"])},

                {"key": "duration", "value": self.globals[K_LIFX][dev_id]["duration"]},
                {"key": "duration_dim_brighten", "value": self.globals[K_LIFX][dev_id][K_DURATION_DIM_BRIGHTEN]},
                {"key": "duration_on", "value": self.globals[K_LIFX][dev_id][K_DURATION_ON]},
                {"key": "duration_off", "value": self.globals[K_LIFX][dev_id][K_DURATION_OFF]},
                {"key": "duration_color_white", "value": self.globals[K_LIFX][dev_id][K_DURATION_COLOR_WHITE]}
                # {"key": "no_ack_state", "value": self.globals[K_LIFX][dev_id][K_NO_ACK_STATE]}
            ]

            props = dev.pluginProps
            if ("SupportsRGB" in props) and props["SupportsRGB"]:
                keyValueList.append({"key": "redLevel", "value": self.globals[K_LIFX][dev_id]["indigoRed"]})
                keyValueList.append({"key": "greenLevel", "value": self.globals[K_LIFX][dev_id]["indigoGreen"]})
                keyValueList.append({"key": "blueLevel", "value": self.globals[K_LIFX][dev_id]["indigoBlue"]})
            if ("SupportsWhiteTemperature" in props) and props["SupportsWhiteTemperature"]:
                keyValueList.append({"key": "whiteTemperature", "value": self.globals[K_LIFX][dev_id]["indigoKelvin"]})
                keyValueList.append({"key": "whiteLevel", "value": self.globals[K_LIFX][dev_id]["indigoWhiteLevel"]})

            dev.updateStatesOnServer(keyValueList)

            dev.updateStateImageOnServer(indigo.kStateImageSel.Auto)

        except StandardError as standard_error_message:
            self.lh_logger.error(u"StandardError detected in 'update_status_from_message'. Line {0} has error: {1}"
                                 .format(sys.exc_traceback.tb_lineno, standard_error_message))
