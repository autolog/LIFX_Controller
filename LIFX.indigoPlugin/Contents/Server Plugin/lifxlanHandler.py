#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# LIFX V4 Controller - Send & Receive Messages © Autolog 2016
#

import colorsys
try:
    import indigo
except:
    pass
import locale
import logging
import Queue
import struct
import sys
import threading
import traceback

from constants import *
from lifxlan.lifxlan import *


# noinspection PyUnresolvedReferences,PyPep8Naming
class ThreadLifxlanHandler(threading.Thread):

    # This class manages the interface to the lifxlan library and controls the sending of commands to lifx devices and handles their responses.

    def __init__(self, pluginGlobals, event):

        threading.Thread.__init__(self)

        self.globals = pluginGlobals

        self.lifxlanHandlerMonitorLogger = logging.getLogger("Plugin.MonitorLifxlanHandler")
        self.lifxlanHandlerMonitorLogger.setLevel(self.globals['debug']['monitorLifxlanHandler'])

        self.lifxlanHandlerDebugLogger = logging.getLogger("Plugin.DebugLifxlanHandler")
        self.lifxlanHandlerDebugLogger.setLevel(self.globals['debug']['debugLifxlanHandler'])

        self.methodTracer = logging.getLogger("Plugin.method")  
        self.methodTracer.setLevel(self.globals['debug']['debugMethodTrace'])

        self.lifxlanHandlerMonitorLogger.info(u"Initialising LIFXLAN Handler Thread")
        self.lifxlanHandlerDebugLogger.debug(u"Debugging LIFXLAN Handler Thread")

        self.threadStop = event

        self.lifxlan = None

    def run(self):
        self.methodTracer.threaddebug(u"ThreadLifxlanHandlerMessages")
 
        try:
            # Initialise the LIFX Lamps on startup
            self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_INIT_DISCOVERY, CMD_DISCOVERY, None, None])

            self.lifxlanHandlerDebugLogger.debug(u"LIFXLAN Handler Thread initialised")

            while not self.threadStop.is_set():
                try:
                    lifxQueuedEntry = self.globals['queues']['lifxlanHandler'].get(True, 5)

                    # lifxQueuedEntry format:
                    #   - Priority
                    #   - Command
                    #   - Device
                    #   - Data

                    lifxQueuePriority, lifxCommand, lifxCommandDevId, lifxCommandParameters = lifxQueuedEntry

                    if lifxCommand == CMD_STOPTHREAD:
                        break  # Exit While loop and quit thread

                    # Check if monitoring / debug options have changed and if so set accordingly
                    if self.globals['debug']['previousMonitorLifxlanHandler'] != self.globals['debug']['monitorLifxlanHandler']:
                        self.globals['debug']['previousMonitorLifxlanHandler'] = self.globals['debug']['monitorLifxlanHandler']
                        self.lifxlanHandlerMonitorLogger.setLevel(self.globals['debug']['monitorLifxlanHandler'])
                    if self.globals['debug']['previousDebugLifxlanHandler'] != self.globals['debug']['debugLifxlanHandler']:
                        self.globals['debug']['previousDebugLifxlanHandler'] = self.globals['debug']['debugLifxlanHandler']
                        self.lifxlanHandlerDebugLogger.setLevel(self.globals['debug']['debugLifxlanHandler'])
                    if self.globals['debug']['previousDebugMethodTrace'] != self.globals['debug']['debugMethodTrace']:
                        self.globals['debug']['previousDebugMethodTrace'] = self.globals['debug']['debugMethodTrace']
                        self.methodTracer.setLevel(self.globals['debug']['debugMethodTrace'])

                    if lifxCommandDevId is not None:
                        if not indigo.devices[lifxCommandDevId].enabled:
                            indigo.devices[lifxCommandDevId].updateStateOnServer(key='brightnessLevel', value=0, uiValue=u'not enabled', clearErrorState=True)
                            # indigo.server.log(u'NOT ENABLED = %s' % indigo.devices[lifxCommandDevId].name)
                            continue
                        else:
                            self.globals['lifx'][lifxCommandDevId]['previousLifxComand'] = self.globals['lifx'][lifxCommandDevId]['currentLifxComand']
                            self.globals['lifx'][lifxCommandDevId]['currentLifxComand'] = lifxCommand
                            if self.globals['lifx'][lifxCommandDevId]['mac_addr'] not in self.lifxDiscoveredDevicesMapping:
                                # self.lifxlanHandlerMonitorLogger.info(u"LIFX Device: '%s' [%s] awaiting discovery" % (indigo.devices[lifxCommandDevId].name, self.globals['lifx'][lifxCommandDevId]['mac_addr']))
                                self.globals['lifx'][lifxCommandDevId]['noAckState'] = True
                                indigo.devices[lifxCommandDevId].updateStateOnServer(key='noAckState', value=self.globals['lifx'][lifxCommandDevId]['noAckState'], clearErrorState=True)
                                if self.globals['lifx'][lifxCommandDevId]['ignoreNoAck']:
                                    indigo.devices[lifxCommandDevId].updateStateImageOnServer(indigo.kStateImageSel.DimmerOff)
                                    indigo.devices[lifxCommandDevId].updateStateOnServer(key='onOffState', value=False, clearErrorState=True)
                                    indigo.devices[lifxCommandDevId].updateStateOnServer(key='brightnessLevel', value=0, uiValue=u'0')
                                else:
                                    indigo.devices[lifxCommandDevId].setErrorStateOnServer(u"no ack")  # Default to 'no ack' status
                                continue
                            elif self.lifxDiscoveredDevicesMapping[self.globals['lifx'][lifxCommandDevId]['mac_addr']]['lifxDevId'] == 0:  # Indigo Device Id (not yet known)
                                self.lifxDiscoveredDevicesMapping[self.globals['lifx'][lifxCommandDevId]['mac_addr']]['lifxDevId'] = lifxCommandDevId

                        self.globals['lifx'][lifxCommandDevId]['ipAddress'] = self.lifxDiscoveredDevicesMapping[self.globals['lifx'][lifxCommandDevId]['mac_addr']]['ipAddress']
                        self.globals['lifx'][lifxCommandDevId]['port'] = self.lifxDiscoveredDevicesMapping[self.globals['lifx'][lifxCommandDevId]['mac_addr']]['port']
                        self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex'] = self.lifxDiscoveredDevicesMapping[self.globals['lifx'][lifxCommandDevId]['mac_addr']]['lifxlanDeviceIndex']

                        lifxDev = indigo.devices[lifxCommandDevId]

                    self.lifxlanHandlerDebugLogger.debug(u"Dequeued lifxlanHandler Command '%s' to process with priority: %s" % (CMD_TRANSLATION[lifxCommand], lifxQueuePriority))

                    if lifxCommand == CMD_DISCOVERY:
                        # Discover LIFX Lamps on demand
                        self.lifxlanHandlerMonitorLogger.info(u"LIFX device discovery starting (this can take up to 60 seconds) . . .")
                        self.lifxlan = LifxLAN(None)  # Force discovery of LIFX Devices
                        self.lifxDevices = self.lifxlan.get_lights()

                        self.numberOfLifxDevices = len(self.lifxDevices)

                        try:
                            testExists = self.lifxDiscoveredDevicesMapping
                        except AttributeError:
                            self.lifxDiscoveredDevicesMapping = dict()

                        indexUi = 0  # In case no devices discovered!
                        discoveryUi = '\n'  # Start with a line break
                        discoveredCount = 0
                        undiscoveredCount = 0
                        discoveryFailedCount = 0
                        for lifxDevice in self.lifxDevices:

                            if lifxDevice.mac_addr not in self.lifxDiscoveredDevicesMapping:
                                self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr] = dict()

                            self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['lifxlanDeviceIndex'] = self.lifxDevices.index(lifxDevice)
                            self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['discovered'] = True
                            self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['ipAddress'] = lifxDevice.ip_addr
                            self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['port'] = lifxDevice.port

                            if 'lifxDevId' in self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr] and self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['lifxDevId'] != 0:
                                self.globals['lifx'][self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['lifxDevId']]['lifxlanDeviceIndex'] = self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['lifxlanDeviceIndex']
                            else:
                                self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['lifxDevId'] = 0  # Indigo Device Id (not yet known)

                            try:
                                lifxDeviceRefreshed = False
                                lifxDevId = self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['lifxDevId']
                                if lifxDevId == 0 or lifxDevId not in self.globals['lifx'] or not self.globals['lifx'][lifxDevId]['discovered']: 
                                    # indigo.server.log(u"REFRESHING '%s'" % lifxDevice.ip_addr)
                                    lifxDevice.req_with_resp(GetService, StateService)
                                    lifxDevice.refresh()
                                    lifxDeviceRefreshed = True
                                # else:
                                    # indigo.server.log(u"SKIPPING REFRESH FOR '%s'" % lifxDevice.ip_addr)
                            except:
                                self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['discovered'] = False

                            indexUi = self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['lifxlanDeviceIndex'] + 1
                            if self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['discovered'] and lifxDeviceRefreshed:
                                discoveredCount += 1
                                discoveryUi += u"LIFX Device {}: '{}' [{}] discovered at address {} on port {}.\n".format(indexUi, lifxDevice.label, lifxDevice.mac_addr, lifxDevice.ip_addr, lifxDevice.port)

                                lifxDeviceMatchedtoIndigoDevice = False
                                for dev in indigo.devices.iter("self"):
                                    if lifxDevice.mac_addr == dev.address:
                                        lifxDeviceMatchedtoIndigoDevice = True
                                        if dev.enabled:
                                            self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['lifxDevId'] = dev.id  # Indigo Device Id
                                        break
                                                
                                if not lifxDeviceMatchedtoIndigoDevice:
                                    lifxDeviceLabel = str(lifxDevice.label).rstrip()
                                    dev = (indigo.device.create(protocol=indigo.kProtocol.Plugin,
                                           address=lifxDevice.mac_addr,
                                           name=lifxDeviceLabel,
                                           description='LIFX Device',
                                           pluginId="com.autologplugin.indigoplugin.lifxcontroller",
                                           deviceTypeId="lifxDevice",
                                           props={"onBrightensToLast": True,
                                                  "SupportsColor": True,
                                                  "SupportsRGB": True,
                                                  "SupportsWhite": True,
                                                  "SupportsTwoWhiteLevels": False,
                                                  "SupportsWhiteTemperature": True,
                                                  "WhiteTemperatureMin": 2500,
                                                  "WhiteTemperatureMax": 9000},
                                           folder=self.globals['folders']['DevicesId']))
                                    
                                    self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['lifxDevId'] = dev.id  # Indigo Device Id

                                    # Start of code block copied from deviceStartComm method in plugin.py
                                    self.globals['lifx'][dev.id] = {}
                                    self.globals['lifx'][dev.id]['discovered'] = True
                                    self.globals['lifx'][dev.id]['connected'] = False
                                    self.globals['lifx'][dev.id]['mac_addr'] = dev.address  # eg. 'd0:73:d5:0a:bc:de'
                                    self.globals['lifx'][dev.id]['ipAddress'] = dev.states['ipAddress']
                                    self.globals['lifx'][dev.id]['port'] = dev.states['port']
                                    self.globals['lifx'][dev.id]['lifxlanDeviceIndex'] = self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['lifxlanDeviceIndex']
                                    self.globals['lifx'][dev.id]['ignoreNoAck'] = bool(dev.pluginProps.get('ignoreNoAck', False))
                                    self.globals['lifx'][dev.id]['noAckState'] = False
                                    # End of code block copied from deviceStartComm method in plugin.py

                            elif not self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['discovered']:
                                if 'lifxDevId' in self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr] and self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['lifxDevId'] != 0:
                                    lifxDev = indigo.devices[self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['lifxDevId']]
                                    if lifxDev.enabled:
                                        discoveryFailedCount += 1
                                        self.lifxlanHandlerMonitorLogger.error(u"Discovery failed to complete for known LIFX Device '{}' [{}]".format(lifxDev.name, lifxDevice.mac_addr))
                                        discoveryUi += u"LIFX Device {}: '{}' [{}] at address {} on port {} - DISCOVERY DID NOT COMPLETE.\n".format(indexUi, lifxDevice.label, lifxDevice.mac_addr, lifxDevice.ip_addr, lifxDevice.port)
                                else:
                                    lifxName = 'Unknown Name' if lifxDevice.label is None else lifxDevice.label
                                    self.lifxlanHandlerMonitorLogger.error(u"Discovery failed to complete for LIFX Device '{}' [{}]".format(lifxName, lifxDevice.mac_addr))
                                    
                            else:
                                discoveredCount += 1
                                lifxDev = indigo.devices[lifxDevId] 
                                discoveryUi += u"LIFX Device {}: '{}' [{}] already discovered at address {} on port {}.\n".format(indexUi, lifxDev.name, lifxDev.address, lifxDev.states['ipAddress'], lifxDev.states['port'])

                            if self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['lifxDevId'] != 0:
                                indigo.devices[self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['lifxDevId']].updateStateOnServer("discovered", self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['discovered'])

                        # Now check if any known and enabled devices still to be discovered and therefore further discovery required
                        furtherDiscoveryRequired = False
                        for dev in indigo.devices.iter("self"):
                            if dev.enabled:
                                lifxDeviceDiscovered = False
                                for lifxDevice in self.lifxDevices:
                                    if lifxDevice.mac_addr == dev.address:
                                        lifxDeviceDiscovered = True
                                if not lifxDeviceDiscovered:
                                    indexUi += 1
                                    discoveryUi += u"LIFX Device {}: '{}' [{}] is not yet visible on the network and therefore a further discovery is required.\n".format(indexUi, dev.name, dev.address)
                                    undiscoveredCount += 1
                                    furtherDiscoveryRequired = True

                        if furtherDiscoveryRequired or discoveryFailedCount > 0:
                            self.globals['discovery']['timer'] = threading.Timer(float(self.globals['discovery']['minutes'] * 60), self.handleTimerDiscovery)
                            self.globals['discovery']['timer'].start()
                            discoveryUi += u"\nAs one or more LIFX devices are still awaiting discovery, another discovery has been scheduled for {} minutes time.\nDisable undiscovered device(s) if further discoveries are not required.".format(self.globals['discovery']['minutes'])
                        else:
                            discoveryUi += u"\nAll known and enabled LIFX devices have been discovered. No further discoveries will be scheduled.\nIf a further discovery is required, reload the plugin or run the LIFX Control Action: 'Discover LIFX Devices'."

                        if discoveredCount == 0:
                            discoveredCount = 'zero'
                        discoveryMessage = u"\n\nLIFX device discovery has completed and {} LIFX device(s) have been successfully discovered.\n".format(discoveredCount)
                        if discoveryFailedCount > 0:
                            discoveryMessage += u"The number of LIFX devices that failed to complete discovery is {}.\n".format(discoveryFailedCount)
                        if undiscoveredCount > 0:
                            discoveryMessage += u"The number of previously known LIFX devices awaiting discovery is {}.\n".format(undiscoveredCount)
                        discoveryMessage += u"{}\n".format(discoveryUi)
                        
                        self.lifxlanHandlerMonitorLogger.info(discoveryMessage)

                        continue

                    if lifxCommand == CMD_STATUS:
                        if not lifxDev.states['discovered']:
                            if not lifxDev.states['noAckState']:
                                self.globals['lifx'][lifxCommandDevId]['connected'] = False
                                lifxDev.updateStateOnServer(key='connected', value=self.globals['lifx'][lifxCommandDevId]['connected'])
                                lifxDev.setErrorStateOnServer(u"no ack")
                            continue
                        ioStatus, power, hsbk = self.getColor(lifxCommandDevId, self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']])
                        if ioStatus:
                            wasConnected = self.globals['lifx'][lifxCommandDevId]['connected']  
                            self.updateStatusFromMsg(lifxCommand, lifxCommandDevId, power, hsbk)

                            if not wasConnected:
                                self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_LOW, CMD_GET_VERSION, lifxCommandDevId, None])
                                self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_LOW, CMD_GET_HOST_FIRMWARE, lifxCommandDevId, None])
                                self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_LOW, CMD_GET_WIFI_FIRMWARE, lifxCommandDevId, None])
                                self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_LOW, CMD_GET_WIFI_INFO, lifxCommandDevId, None])

                            props = lifxDev.pluginProps
                            if ("SupportsInfrared" in props) and props["SupportsInfrared"]:
                                ioStatus, infraredBrightness = self.getInfrared(lifxCommandDevId, self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']])
                                if ioStatus:
                                    IndigoInfraredBrightness = float((infraredBrightness * 100) / 65535)
                                    keyValueList = [
                                        {'key': 'infraredBrightness', 'value': infraredBrightness},
                                        {'key': 'indigoInfraredBrightness', 'value': IndigoInfraredBrightness}]
                                    lifxDev.updateStatesOnServer(keyValueList)

                                    self.lifxlanHandlerDebugLogger.debug(u"LifxlanHandler Infrared Level for '%s' is: %s" % (lifxDev.name, IndigoInfraredBrightness))

                        self.globals['lifx'][lifxCommandDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if (lifxCommand == CMD_ON) or (lifxCommand == CMD_OFF) or (lifxCommand == CMD_WAVEFORM_OFF) or (lifxCommand == CMD_IMMEDIATE_ON):

                        # Stop any background timer brighten or dim operation
                        self.globals['lifx'][lifxCommandDevId]['stopRepeatDim'] = True
                        self.globals['lifx'][lifxCommandDevId]['stopRepeatBrighten'] = True

                        if self.globals['lifx'][lifxCommandDevId]['connected']:

                            self.lifxlanHandlerDebugLogger.debug(u"Processing %s for '%s' " % (lifxCommand, indigo.devices[lifxCommandDevId].name))

                            lifxDev = indigo.devices[lifxCommandDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            if lifxCommand == CMD_ON:
                                duration = float(self.globals['lifx'][lifxCommandDevId]['durationOn'])
                                power = 65535
                            elif lifxCommand == CMD_IMMEDIATE_ON:
                                duration = 0
                                power = 65535
                            elif lifxCommand == CMD_OFF:
                                duration = float(self.globals['lifx'][lifxCommandDevId]['durationOff'])
                                power = 0
                            else:
                                duration = 0
                                power = 0
                            timerDuration = duration
                            duration = int(duration * 1000)
                            try:    
                                self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_power(power, duration)
                            except:
                                self.communicationLost(lifxCommandDevId, 'set_power')
                                continue

                            self.globals['deviceTimers'][lifxCommandDevId]['STATUS'] = threading.Timer(1.0, self.handleTimerRepeatingQueuedStatusCommand, [lifxDev, timerDuration])
                            self.globals['deviceTimers'][lifxCommandDevId]['STATUS'].start()
                        
                        self.globals['lifx'][lifxCommandDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if (lifxCommand == CMD_INFRARED_ON) or (lifxCommand == CMD_INFRARED_OFF) or (lifxCommand == CMD_INFRARED_SET):
                        if self.globals['lifx'][lifxCommandDevId]['connected']:

                            self.lifxlanHandlerDebugLogger.debug(u"Processing %s for '%s' " % (lifxCommand, indigo.devices[lifxCommandDevId].name))

                            lifxDev = indigo.devices[lifxCommandDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            if lifxCommand == CMD_INFRARED_OFF:
                                infraredBrightness = 0
                            elif lifxCommand == CMD_INFRARED_ON:
                                infraredBrightness = 65535
                            elif lifxCommand == CMD_INFRARED_SET:
                                infraredBrightness = lifxCommandParameters[0]
                                infraredBrightness = int((infraredBrightness * 65535.0) / 100.0)
                                if infraredBrightness > 65535:
                                    infraredBrightness = 65535  # Just in case ;)

                            try:
                                self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_infrared(infraredBrightness)
                                self.lifxlanHandlerDebugLogger.debug(u"Processing %s for '%s'; Infrared Brightness = %s" % (lifxCommand, indigo.devices[lifxCommandDevId].name, infraredBrightness))
                            except:
                                self.communicationLost(lifxCommandDevId, 'set_infrared')
                                continue

                            self.globals['deviceTimers'][lifxCommandDevId]['STATUS'] = threading.Timer(1.0, self.handleTimerRepeatingQueuedStatusCommand, [lifxDev, 2])
                            self.globals['deviceTimers'][lifxCommandDevId]['STATUS'].start()
                        
                        self.globals['lifx'][lifxCommandDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if lifxCommand == CMD_STOP_BRIGHTEN_DIM_BY_TIMER:
                        self.globals['lifx'][lifxCommandDevId]['stopRepeatBrighten'] = True
                        self.globals['lifx'][lifxCommandDevId]['stopRepeatDim'] = True
                        self.clearBrightenByTimerTimer(lifxDev)
                        self.clearDimByTimerTimer(lifxDev)
                        continue

                    if lifxCommand == CMD_BRIGHTEN_BY_TIMER or lifxCommand == CMD_REPEAT_BRIGHTEN_BY_TIMER:
                        if self.globals['lifx'][lifxCommandDevId]['connected']:
                            if lifxCommand == CMD_BRIGHTEN_BY_TIMER:
                                # Clear any outstanding timers
                                self.clearBrightenByTimerTimer(lifxDev)
                                self.globals['lifx'][lifxCommandDevId]['stopRepeatBrighten'] = False
                                self.globals['lifx'][lifxCommandDevId]['stopRepeatDim'] = True

                            if not self.globals['lifx'][lifxCommandDevId]['stopRepeatBrighten']:
                                option = lifxCommandParameters[0]
                                amountToBrightenBy = lifxCommandParameters[1]
                                timerInterval = lifxCommandParameters[2]

                                newBrightness = lifxDev.brightness + amountToBrightenBy
                                if int(lifxDev.states['powerLevel']) == 0 or int(lifxDev.states['indigoBrightness']) < 100:
                                    self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_COMMAND_HIGH, CMD_BRIGHTEN, lifxCommandDevId, [newBrightness]])
                                    lifxDev.updateStateOnServer("brightnessLevel", newBrightness)
                                    self.globals['deviceTimers'][lifxCommandDevId]['BRIGHTEN_BY_TIMER'] = threading.Timer(timerInterval, self.handleTimerRepeatingQueuedBrightenByTimerCommand, [[lifxCommandDevId, option, amountToBrightenBy, timerInterval]])
                                    self.globals['deviceTimers'][lifxCommandDevId]['BRIGHTEN_BY_TIMER'].start()
                                else:
                                    self.globals['lifx'][lifxCommandDevId]['stopRepeatBrighten'] = True
                                    self.lifxlanHandlerMonitorLogger.info(u"\"%s\" %s" % (lifxDev.name, 'brightened to 100%'))

                            continue

                    if lifxCommand == CMD_DIM_BY_TIMER or lifxCommand == CMD_REPEAT_DIM_BY_TIMER:
                        if self.globals['lifx'][lifxCommandDevId]['connected']:
                            if lifxCommand == CMD_DIM_BY_TIMER:
                                # Clear any outstanding timers
                                self.clearDimByTimerTimer(lifxDev)
                                self.globals['lifx'][lifxCommandDevId]['stopRepeatDim'] = False
                                self.globals['lifx'][lifxCommandDevId]['stopRepeatBrighten'] = True

                            if not self.globals['lifx'][lifxCommandDevId]['stopRepeatDim']:
                                option = lifxCommandParameters[0]
                                amountToDimBy = lifxCommandParameters[1]
                                timerInterval = lifxCommandParameters[2]

                                if int(lifxDev.states['powerLevel']) > 0:
                                    if lifxDev.brightness == 0:
                                        newBrightness = 0
                                    else: 
                                        newBrightness = lifxDev.brightness - amountToDimBy
                                else:
                                    if int(lifxDev.states['indigoBrightness']) > 0:
                                        newBrightness = int(lifxDev.states['indigoBrightness'])
                                    else:
                                        newBrightness = 0

                                if newBrightness <= 0:
                                    newBrightness = 0
                                    lifxDev.updateStateOnServer("brightnessLevel", newBrightness)
                                    self.globals['lifx'][lifxCommandDevId]['stopRepeatDim'] = True
                                    self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_COMMAND_HIGH, CMD_DIM, lifxCommandDevId, [newBrightness]])
                                    self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_COMMAND_HIGH, CMD_OFF, lifxCommandDevId, None])
                                    self.lifxlanHandlerMonitorLogger.info(u"\"%s\" %s" % (lifxDev.name, 'dimmed to off'))
                                else:
                                    self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_COMMAND_HIGH, CMD_DIM, lifxCommandDevId, [newBrightness]])
                                    lifxDev.updateStateOnServer("brightnessLevel", newBrightness)
                                    self.globals['deviceTimers'][lifxCommandDevId]['BRIGHTEN_DIM_BY_TIMER'] = threading.Timer(timerInterval, self.handleTimerRepeatingQueuedDimByTimerCommand, [[lifxCommandDevId, option, amountToDimBy, timerInterval]])
                                    self.globals['deviceTimers'][lifxCommandDevId]['BRIGHTEN_DIM_BY_TIMER'].start()

                            continue

                    if lifxCommand == CMD_DIM or lifxCommand == CMD_BRIGHTEN or lifxCommand == CMD_BRIGHTNESS:
                        if self.globals['lifx'][lifxCommandDevId]['connected']:
                            newBrightness = lifxCommandParameters[0]
                            newBrightness = int((newBrightness * 65535.0) / 100.0)

                            lifxDev = indigo.devices[lifxCommandDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            hue = self.globals['lifx'][lifxCommandDevId]['hsbkHue']         # Value between 0 and 65535
                            saturation = self.globals['lifx'][lifxCommandDevId]['hsbkSaturation']  # Value between 0 and 65535 (e.g. 20% = 13107)
                            kelvin = self.globals['lifx'][lifxCommandDevId]['hsbkKelvin']      # Value between 2500 and 9000
                            powerLevel = self.globals['lifx'][lifxCommandDevId]['powerLevel']      # Value between 0 and 65535 

                            if (lifxCommand == CMD_BRIGHTEN or lifxCommand == CMD_DIM) and powerLevel == 0:
                                # Need to turn on LIFX device as currently off
                                powerLevel = 65535
                                try:
                                    self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_power(powerLevel, 0)
                                except:
                                    self.communicationLost(lifxCommandDevId, 'set_power')
                                    continue
                            elif lifxCommand == CMD_BRIGHTNESS and newBrightness > 0 and powerLevel == 0:
                                # Need to reset existing brightness to 0 before turning on
                                try:
                                    hsbkWithBrightnessZero = self.setHSBK(hue, saturation, 0, kelvin)
                                    self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_color(hsbkWithBrightnessZero, 0)
                                except:
                                    self.communicationLost(lifxCommandDevId, 'set_color')
                                    continue
                                # Need to turn on LIFX device as currently off
                                powerLevel = 65535
                                try:
                                    self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_power(powerLevel, 0)
                                except:
                                    self.communicationLost(lifxCommandDevId, 'set_power')
                                    continue

                            if lifxCommand == CMD_BRIGHTNESS:
                                self.globals['lifx'][lifxCommandDevId]['stopRepeatBrighten'] = True
                                self.globals['lifx'][lifxCommandDevId]['stopRepeatDim'] = True
                                duration = int(self.globals['lifx'][lifxCommandDevId]['durationDimBrighten'] * 1000)
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

                            self.lifxlanHandlerDebugLogger.debug(u'LIFX COMMAND [BRIGHTNESS]; SET-COLOR for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s' % (indigo.devices[lifxCommandDevId].name,  hue, saturation, brightness, kelvin))   

                            try:
                                hsbk = self.setHSBK(hue, saturation, brightness, kelvin)
                                self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_color(hsbk, duration, True)
                                self.updateStatusFromMsg(lifxCommand, lifxCommandDevId, powerLevel, hsbk)

                            except:
                                self.communicationLost(lifxCommandDevId, 'set_color')
                                continue

                        self.globals['lifx'][lifxCommandDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if lifxCommand == CMD_WHITE:
                        # Stop any background timer brighten or dim operation
                        self.globals['lifx'][lifxCommandDevId]['stopRepeatDim'] = True
                        self.globals['lifx'][lifxCommandDevId]['stopRepeatBrighten'] = True

                        targetWhiteLevel, targetWhiteTemperature = lifxCommandParameters

                        if self.globals['lifx'][lifxCommandDevId]['connected']:
                            lifxDev = indigo.devices[lifxCommandDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            ioStatus, power, hsbk = self.getColor(lifxCommandDevId, self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']])

                            self.lifxlanHandlerDebugLogger.debug(u"LIFX COMMAND [WHITE] IOSTATUS for %s =  %s, HSBK = %s" % (indigo.devices[lifxCommandDevId].name, ioStatus, hsbk))
                            if ioStatus:
                                hue = hsbk[0]
                                saturation = hsbk[1]
                                brightness = hsbk[2]
                                kelvin = hsbk[3]

                                self.lifxlanHandlerDebugLogger.debug(u'LIFX COMMAND [WHITE]; GET-COLOR for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s' % (indigo.devices[lifxCommandDevId].name,  hue, saturation, brightness, kelvin))   

                                if power == 0 and self.globals['lifx'][lifxCommandDevId]['turnOnIfOff']:
                                    # Need to reset existing brightness to 0 before turning on
                                    try:
                                        hsbkWithBrightnessZero = self.setHSBK(hue, saturation, 0, kelvin)
                                        self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_color(hsbkWithBrightnessZero, 0)
                                    except:
                                        self.communicationLost(lifxCommandDevId, 'set_color')
                                        continue
                                    # Need to turn on LIFX device as currently off
                                    power = 65535
                                    try:
                                        self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_power(power, 0)
                                    except:
                                        self.communicationLost(lifxCommandDevId, 'set_power')
                                        continue
                                        
                                saturation = 0
                                brightness = int((targetWhiteLevel * 65535.0) / 100.0)
                                kelvin = int(targetWhiteTemperature)
                                duration = int(self.globals['lifx'][lifxCommandDevId]['durationColorWhite'] * 1000)

                                self.lifxlanHandlerDebugLogger.debug(u'LIFX COMMAND [WHITE]; SET-COLOR for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s' % (indigo.devices[lifxCommandDevId].name,  hue, saturation, brightness, kelvin))   

                                try:
                                    hsbk = self.setHSBK(hue, saturation, brightness, kelvin)
                                    self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_color(hsbk, duration)
                                except:
                                    self.communicationLost(lifxCommandDevId, 'set_color')
                                    continue

                                timerDuration = int(self.globals['lifx'][lifxCommandDevId]['durationColorWhite'])
                                self.globals['deviceTimers'][lifxCommandDevId]['STATUS'] = threading.Timer(1.0, self.handleTimerRepeatingQueuedStatusCommand, [lifxDev, timerDuration])

                                self.globals['deviceTimers'][lifxCommandDevId]['STATUS'].start()

                        self.globals['lifx'][lifxCommandDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if lifxCommand == CMD_COLOR:
                        # Stop any background timer brighten or dim operation
                        self.globals['lifx'][lifxCommandDevId]['stopRepeatDim'] = True
                        self.globals['lifx'][lifxCommandDevId]['stopRepeatBrighten'] = True

                        targetHue, targetSaturation, targetBrightness = lifxCommandParameters

                        if self.globals['lifx'][lifxCommandDevId]['connected']:
                            lifxDev = indigo.devices[lifxCommandDevId]
 
                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            ioStatus, power, hsbk = self.getColor(lifxCommandDevId, self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']])
                            self.lifxlanHandlerDebugLogger.debug(u"LIFX COMMAND [COLOR] IOSTATUS for %s =  %s, HSBK = %s" % (indigo.devices[lifxCommandDevId].name, ioStatus, hsbk))
                            if ioStatus:
                                hue = hsbk[0]
                                saturation = hsbk[1]
                                brightness = hsbk[2]
                                kelvin = hsbk[3]

                                self.lifxlanHandlerDebugLogger.debug(u'LIFX COMMAND [COLOR]; GET-COLOR for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s' % (indigo.devices[lifxCommandDevId].name,  hue, saturation, brightness, kelvin))   

                                if power == 0 and self.globals['lifx'][lifxCommandDevId]['turnOnIfOff']:
                                    # Need to reset existing brightness to 0 before turning on
                                    try:
                                        hsbkWithBrightnessZero = self.setHSBK(hue, saturation, 0, kelvin)
                                        self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_color(hsbkWithBrightnessZero, 0)
                                    except:
                                        self.communicationLost(lifxCommandDevId, 'set_color')
                                        continue
                                    # Need to turn on LIFX device as currently off
                                    power = 65535
                                    try:
                                        self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_power(power, 0)
                                    except:
                                        self.communicationLost(lifxCommandDevId, 'set_power')
                                        continue

                                hue = targetHue
                                saturation = targetSaturation
                                brightness = targetBrightness
                                duration = int(self.globals['lifx'][lifxCommandDevId]['durationColorWhite'] * 1000)

                                self.lifxlanHandlerDebugLogger.debug(u'LIFX COMMAND [COLOR]; SET-COLOR for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s, Duration=%s' % (indigo.devices[lifxCommandDevId].name,  hue, saturation, brightness, kelvin, duration))   

                                try:
                                    hsbk = self.setHSBK(hue, saturation, brightness, kelvin)
                                    self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_color(hsbk, duration)
                                except:
                                    self.communicationLost(lifxCommandDevId, 'set_color')
                                    continue

                                timerDuration = int(self.globals['lifx'][lifxCommandDevId]['durationColorWhite'])
                                self.globals['deviceTimers'][lifxCommandDevId]['STATUS'] = threading.Timer(1.0, self.handleTimerRepeatingQueuedStatusCommand, [lifxDev, timerDuration])

                                self.globals['deviceTimers'][lifxCommandDevId]['STATUS'].start()

                        self.globals['lifx'][lifxCommandDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if lifxCommand == CMD_STANDARD:
                        # Stop any background timer brighten or dim operation
                        self.globals['lifx'][lifxCommandDevId]['stopRepeatDim'] = True
                        self.globals['lifx'][lifxCommandDevId]['stopRepeatBrighten'] = True

                        turnOnIfOff, targetMode, targetHue, targetSaturation, targetBrightness, targetKelvin, targetDuration = lifxCommandParameters

                        if self.globals['lifx'][lifxCommandDevId]['connected']:
                            lifxDev = indigo.devices[lifxCommandDevId]

                            self.lifxlanHandlerDebugLogger.debug(u'LIFX COMMAND [STANDARD]; Target for %s: TOIF=%s, Mode=%s, Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s, Duration=%s' % (indigo.devices[lifxCommandDevId].name,  turnOnIfOff, targetMode, targetHue, targetSaturation, targetBrightness, targetKelvin, targetDuration))   
 
                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            ioStatus, power, hsbk = self.getColor(lifxCommandDevId, self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']])
                            self.lifxlanHandlerDebugLogger.debug(u"LIFX COMMAND [COLOR] IOSTATUS for %s =  %s, HSBK = %s" % (indigo.devices[lifxCommandDevId].name, ioStatus, hsbk))
                            if ioStatus:
                                hue = hsbk[0]
                                saturation = hsbk[1]
                                brightness = hsbk[2]
                                kelvin = hsbk[3]

                                self.lifxlanHandlerDebugLogger.debug(u'LIFX COMMAND [COLOR]; GET-COLOR for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s' % (indigo.devices[lifxCommandDevId].name,  hue, saturation, brightness, kelvin))   

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
                                    duration = int(self.globals['lifx'][lifxCommandDevId]['durationColorWhite'] * 1000)

                                self.lifxlanHandlerDebugLogger.debug(u'LIFX COMMAND [STANDARD][%s]; SET-COLOR for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s, duration=%s' % (targetMode, indigo.devices[lifxCommandDevId].name,  hue, saturation, brightness, kelvin, duration))   

                                if power == 0 and turnOnIfOff:
                                    try:
                                        hsbk = self.setHSBK(hue, saturation, brightness, kelvin)
                                        self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_color(hsbk, 0)
                                    except:
                                        self.communicationLost(lifxCommandDevId, 'set_color')
                                        continue
                                    power = 65535
                                    try:
                                        self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_power(power, duration)
                                    except:
                                        self.communicationLost(lifxCommandDevId, 'set_power')
                                        continue
                                else:
                                    if power == 0:
                                        duration = 0  # As power is off. might as well do apply command straight away
                                    try:
                                        hsbk = self.setHSBK(hue, saturation, brightness, kelvin)
                                        self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_color(hsbk, duration)
                                    except:
                                        self.communicationLost(lifxCommandDevId, 'set_color')
                                        continue

                                timerDuration = int(duration/1000)  # Convert back from milliseconds
                                self.globals['deviceTimers'][lifxCommandDevId]['STATUS'] = threading.Timer(1.0, self.handleTimerRepeatingQueuedStatusCommand, [lifxDev, timerDuration])

                                self.globals['deviceTimers'][lifxCommandDevId]['STATUS'].start()

                        self.globals['lifx'][lifxCommandDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if lifxCommand == CMD_WAVEFORM:
                        # Stop any background timer brighten or dim operation
                        self.globals['lifx'][lifxCommandDevId]['stopRepeatDim'] = True
                        self.globals['lifx'][lifxCommandDevId]['stopRepeatBrighten'] = True

                        targetMode, targetHue, targetSaturation, targetBrightness, targetKelvin, targetTransient, targetPeriod, targetCycles, targetDuty_cycle, targetWaveform = lifxCommandParameters

                        if self.globals['lifx'][lifxCommandDevId]['connected']:
                            lifxDev = indigo.devices[lifxCommandDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)
                            self.clearWaveformOffTimer(lifxDev)

                            ioStatus, power, hsbk = self.getColor(lifxCommandDevId, self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']])
                            self.lifxlanHandlerDebugLogger.debug(u"LIFX COMMAND [COLOR] IOSTATUS for %s =  %s, HSBK = %s" % (indigo.devices[lifxCommandDevId].name, ioStatus, hsbk))
                            if ioStatus:
                                hue = hsbk[0]
                                saturation = hsbk[1]
                                brightness = hsbk[2]
                                kelvin = hsbk[3]

                                self.lifxlanHandlerDebugLogger.debug(u'LIFX COMMAND [COLOR]; GET-COLOR for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s' % (indigo.devices[lifxCommandDevId].name,  hue, saturation, brightness, kelvin))   

                                lifxDeviceAlreadyOn = True
                                if power == 0:
                                    lifxDeviceAlreadyOn = False
                                    duration = 0
                                    power = 65535
                                    duration = int(duration * 1000)    
                                    try:
                                        self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_power(power, duration)
                                    except:
                                        self.communicationLost(lifxCommandDevId, 'set_power')
                                        continue

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
                                hsbk = self.setHSBK(hue, saturation, brightness, kelvin)

                                if targetTransient:
                                    transient = int(1)
                                else:
                                    transient = int(0)
                                period = int(targetPeriod)
                                cycles = float(targetCycles)
                                duty_cycle = int(targetDuty_cycle)
                                waveform = int(targetWaveform)

                                self.lifxlanHandlerDebugLogger.debug(u'LIFX COMMAND [WAVEFORM]; SET-WAVEFORM for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s' % (indigo.devices[lifxCommandDevId].name,  hue, saturation, brightness, kelvin))   
                                self.lifxlanHandlerDebugLogger.debug(u'LIFX COMMAND [WAVEFORM]; SET-WAVEFORM for %s: Transient=%s, Period=%s, Cycles=%s, Duty_cycle=%s, Waveform=%s' % (indigo.devices[lifxCommandDevId].name,  transient, period, cycles, duty_cycle, waveform))   

                                try:
                                    self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_waveform(transient, hsbk, period, cycles, duty_cycle, waveform)
                                except:
                                    self.communicationLost(lifxCommandDevId, 'set_waveform')
                                    continue

                                if not lifxDeviceAlreadyOn:
                                    timerSetFor = float((float(period) / 1000.0) * cycles)
                                    self.globals['deviceTimers'][lifxCommandDevId]['WAVEFORM_OFF'] = threading.Timer(timerSetFor, self.handleTimerWaveformOffCommand, [lifxDev])
                                    self.globals['deviceTimers'][lifxCommandDevId]['WAVEFORM_OFF'].start()

                        self.globals['lifx'][lifxCommandDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if lifxCommand == CMD_SET_LABEL:
                        if self.globals['lifx'][lifxCommandDevId]['connected']:

                            self.lifxlanHandlerDebugLogger.debug(u"Processing %s for '%s' " % (lifxCommand, indigo.devices[lifxCommandDevId].name))

                            lifxDev = indigo.devices[lifxCommandDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            try:
                                self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_label(lifxDev.name)
                            except:
                                self.communicationLost(lifxCommandDevId, 'set_label')

                        self.globals['lifx'][lifxCommandDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if lifxCommand == CMD_GET_VERSION:
                        if self.globals['lifx'][lifxCommandDevId]['connected']:

                            self.lifxlanHandlerDebugLogger.debug(u"Processing %s for '%s' " % (lifxCommand, indigo.devices[lifxCommandDevId].name))

                            lifxDev = indigo.devices[lifxCommandDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            try:
                                product = self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].get_product()
                            except:
                                self.communicationLost(lifxCommandDevId, 'get_product')
                                continue

                            self.lifxlanHandlerDebugLogger.debug(u"PRODUCT for '%s' = '%s'" % (indigo.devices[lifxCommandDevId].name, product))

                            productFound = False
                            try:
                                model = str('%s' % (LIFX_PRODUCTS[product][LIFX_PRODUCT_NAME]))  # Defined in constants.py
                                productFound = True
                            except KeyError:
                                model = str('LIFX Product - %s' % product)

                            if lifxDev.model != model:
                                lifxDev.model = model
                                lifxDev.replaceOnServer()

                            if productFound:
                                props = lifxDev.pluginProps
                                propsChanged = False
                                if ("SupportsColor" not in props) or (props["SupportsColor"] != bool(LIFX_PRODUCTS[product][LIFX_PRODUCT_SUPPORTS_COLOR])):
                                    props["SupportsColor"] = True  # Applies even if just able to change White Levels / Temperature
                                    props["SupportsRGB"] = bool(LIFX_PRODUCTS[product][LIFX_PRODUCT_SUPPORTS_COLOR])
                                    propsChanged = True
                                if ("SupportsRGB" not in props) or (props["SupportsRGB"] != bool(LIFX_PRODUCTS[product][LIFX_PRODUCT_SUPPORTS_COLOR])):
                                    props["SupportsRGB"] = bool(LIFX_PRODUCTS[product][LIFX_PRODUCT_SUPPORTS_COLOR])
                                    propsChanged = True
                                if ("SupportsInfrared" not in props) or (props["SupportsInfrared"] != bool(LIFX_PRODUCTS[product][LIFX_PRODUCT_SUPPORTS_INFRARED])):
                                    props["SupportsInfrared"] = bool(LIFX_PRODUCTS[product][LIFX_PRODUCT_SUPPORTS_INFRARED])
                                    propsChanged = True
                                if ("SupportsMultizone" not in props) or (props["SupportsMultizone"] != bool(LIFX_PRODUCTS[product][LIFX_PRODUCT_SUPPORTS_MULTIZONE])):
                                    props["SupportsMultizone"] = bool(LIFX_PRODUCTS[product][LIFX_PRODUCT_SUPPORTS_MULTIZONE])
                                    propsChanged = True
                                if propsChanged:
                                    lifxDev.replacePluginPropsOnServer(props)

                        self.globals['lifx'][lifxCommandDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if lifxCommand == CMD_GET_HOST_FIRMWARE:
                        if self.globals['lifx'][lifxCommandDevId]['connected']:

                            self.lifxlanHandlerDebugLogger.debug(u"Processing %s for '%s' " % (lifxCommand, indigo.devices[lifxCommandDevId].name))

                            lifxDev = indigo.devices[lifxCommandDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            try:
                                firmware_version = str(self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].get_host_firmware_version())
                            except:
                                self.communicationLost(lifxCommandDevId, 'get_host_firmware_version')
                                continue

                            self.lifxlanHandlerDebugLogger.debug(u"HOST FIRMWARE VERSION for '%s': '%s'" % (indigo.devices[lifxCommandDevId].name, firmware_version))

                            props = lifxDev.pluginProps

                            if 'version' in props:
                                version = str(props['version']).split('|')
                            else:
                                props["version"] = ''
                                version = ['_']

                            if len(version) > 1:
                                if firmware_version == version[1]:
                                    newVersion = firmware_version
                                else:
                                    newVersion = firmware_version + '|' + version[1]
                            else:
                                newVersion = firmware_version

                            if props["version"] != newVersion:
                                props["version"] = newVersion
                                lifxDev.replacePluginPropsOnServer(props)

                        self.globals['lifx'][lifxCommandDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if lifxCommand == CMD_GET_PORT:
                        if self.globals['lifx'][lifxCommandDevId]['connected']:

                            self.lifxlanHandlerDebugLogger.debug(u"Processing %s for '%s' " % (lifxCommand, indigo.devices[lifxCommandDevId].name))

                            lifxDev = indigo.devices[lifxCommandDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            try:
                                port = str(self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].get_port())
                            except:
                                self.communicationLost(lifxCommandDevId, 'get_port')
                                continue

                            self.lifxlanHandlerDebugLogger.info(u"Port for '%s': '%s'" % (indigo.devices[lifxCommandDevId].name, port))

                            # props = lifxDev.pluginProps

                            # if 'version' in props:
                            #     version = str(props['version']).split('|')
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
                            #     lifxDev.replacePluginPropsOnServer(props)

                        self.globals['lifx'][lifxCommandDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if lifxCommand == CMD_GET_WIFI_FIRMWARE:
                        if self.globals['lifx'][lifxCommandDevId]['connected']:

                            self.lifxlanHandlerDebugLogger.debug(u"Processing %s for '%s' " % (lifxCommand, indigo.devices[lifxCommandDevId].name))

                            lifxDev = indigo.devices[lifxCommandDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            try:
                                wifi_firmware_version = str(self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].get_wifi_firmware_version())
                            except:
                                self.communicationLost(lifxCommandDevId, 'get_wifi_firmware_version')
                                continue

                            self.lifxlanHandlerDebugLogger.debug(u"WI-FI FIRMWARE VERSION for '%s': '%s'" % (indigo.devices[lifxCommandDevId].name, wifi_firmware_version))

                            props = lifxDev.pluginProps

                            if 'version' in props:
                                version = str(props['version']).split('|')
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
                                lifxDev.replacePluginPropsOnServer(props)

                        self.globals['lifx'][lifxCommandDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if lifxCommand == CMD_GET_WIFI_INFO:
                        if self.globals['lifx'][lifxCommandDevId]['connected']:

                            self.lifxlanHandlerDebugLogger.debug(u"Processing %s for '%s' " % (lifxCommand, indigo.devices[lifxCommandDevId].name))

                            lifxDev = indigo.devices[lifxCommandDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            try:
                                signal, tx, rx = self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].get_wifi_info_tuple()
                            except:
                                self.communicationLost(lifxCommandDevId, 'get_wifi_info_tuple')
                                continue

                            self.lifxlanHandlerDebugLogger.debug(u"WI-FI INFO [1] for '%s': Signal=%s, Tx=%s, Rx=%s" % (indigo.devices[lifxCommandDevId].name, signal, tx, rx))
                            if signal is not None:
                                signal = str('{:.16f}'.format(signal))[0:12]
                            locale.setlocale(locale.LC_ALL, 'en_US')
                            if tx is not None:
                                tx = locale.format("%d", tx, grouping=True)
                            if rx is not None:
                                rx = locale.format("%d", rx, grouping=True)

                            self.lifxlanHandlerDebugLogger.debug(u"WI-FI INFO [2] for '%s': Signal=%s, Tx=%s, Rx=%s" % (indigo.devices[lifxCommandDevId].name, signal, tx, rx))

                            keyValueList = [
                                {'key': 'wifiSignal', 'value': signal},
                                {'key': 'wifiTx', 'value': tx},
                                {'key': 'wifiRx', 'value': rx}
                            ]
                            lifxDev.updateStatesOnServer(keyValueList)

                        self.globals['lifx'][lifxCommandDevId]['previousLifxComand'] = lifxCommand
                        continue

                    continue

                    # TO BE CONTINUED !

                    if lifxCommand == CMD_GET_HOST_INFO:
                        self.lifxlanHandlerDebugLogger.debug(u"Processing %s" % lifxCommand)

                        payload = ''
                        dev = sendMessage[1]
                        ipAddress = self.globals['lifx'][dev.id]['ipAddress']
                        self.outputMessageToLifxDevice(ipAddress, DEV_GET_HOST_INFO, dev, payload)

                        continue

                    if lifxCommand == CMD_GET_LOCATION:
                        self.lifxlanHandlerDebugLogger.debug(u"Processing %s" % lifxCommand)

                        payload = ''
                        dev = sendMessage[1]
                        ipAddress = self.globals['lifx'][dev.id]['ipAddress']
                        self.outputMessageToLifxDevice(ipAddress, DEV_GET_LOCATION, dev, payload)

                        continue

                    if lifxCommand == CMD_GET_GROUP:
                        self.lifxlanHandlerDebugLogger.debug(u"Processing %s" % lifxCommand)

                        payload = ''
                        dev = sendMessage[1]
                        ipAddress = self.globals['lifx'][dev.id]['ipAddress']
                        self.outputMessageToLifxDevice(ipAddress, DEV_GET_GROUP, dev, payload)

                        continue

                    if lifxCommand == CMD_GET_INFO:
                        self.lifxlanHandlerDebugLogger.debug(u"Processing %s" % lifxCommand)

                        payload = ''
                        dev = sendMessage[1]
                        ipAddress = self.globals['lifx'][dev.id]['ipAddress']
                        self.outputMessageToLifxDevice(ipAddress, DEV_GET_INFO, dev, payload)

                        continue

                except Queue.Empty:
                    pass
                except StandardError, e:
                    self.lifxlanHandlerDebugLogger.error(u"StandardError detected communicating with LIFX lamp. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))   
                except:
                    sysTraceback = 'No INFO' if sys.exc_info()[2] is None else sys.exc_info()[2]
                    sysTraceBackUI = ''.join(traceback.format_tb(sysTraceback)) 
                    self.lifxlanHandlerDebugLogger.error(u"Exception detected communicating with LIFX devices '%s' - %s" % (sys.exc_info()[1], sysTraceBackUI)) 

        except StandardError, e:
            self.lifxlanHandlerDebugLogger.error(u"StandardError detected in LIFX Send Receive Message Thread. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))   

        self.lifxlanHandlerDebugLogger.debug(u"LIFX Send Receive Message Thread ended.")   

    def clearBrightenByTimerTimer(self, dev):
        self.methodTracer.threaddebug(u"CLASS: ThreadLifxlanHandlerMessages")

        if dev.id in self.globals['deviceTimers'] and 'BRIGHTEN_BY_TIMER' in self.globals['deviceTimers'][dev.id]:
            self.globals['deviceTimers'][dev.id]['BRIGHTEN_BY_TIMER'].cancel()

    def handleTimerRepeatingQueuedBrightenByTimerCommand(self, parameters):
        self.methodTracer.threaddebug(u"CLASS: ThreadLifxlanHandlerMessages")

        try:
            devId = parameters[0]
            dev = indigo.devices[devId]
            option = parameters[1]
            amountToBrightenDimBy = parameters[2]
            timerInterval = parameters[3]

            self.lifxlanHandlerDebugLogger.debug(u'Timer for %s [%s] invoked for repeating queued message BRIGHTEN_BY_TIMER. Stop = %s' % (dev.name, dev.address, self.globals['lifx'][devId]['stopRepeatBrighten']))

            try:
                del self.globals['deviceTimers'][devId]['BRIGHTEN_BY_TIMER']
            except:
                pass

            if not self.globals['lifx'][devId]['stopRepeatBrighten']:
                self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_COMMAND_MEDIUM, CMD_REPEAT_BRIGHTEN_BY_TIMER, dev.id, [option, amountToBrightenDimBy, timerInterval]])

        except StandardError, e:
            self.lifxlanHandlerDebugLogger.error(u"handleTimerRepeatingQueuedBrightenByTimerCommand error detected. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))   

    def clearDimByTimerTimer(self, dev):
        self.methodTracer.threaddebug(u"CLASS: ThreadLifxlanHandlerMessages")

        if dev.id in self.globals['deviceTimers'] and 'DIM_BY_TIMER' in self.globals['deviceTimers'][dev.id]:
            self.globals['deviceTimers'][dev.id]['DIM_BY_TIMER'].cancel()

    def handleTimerRepeatingQueuedDimByTimerCommand(self, parameters):
        self.methodTracer.threaddebug(u"CLASS: ThreadLifxlanHandlerMessages")

        try:
            devId = parameters[0]
            dev = indigo.devices[devId]
            option = parameters[1]
            amountToBrightenDimBy = parameters[2]
            timerInterval = parameters[3]

            self.lifxlanHandlerDebugLogger.debug(u'Timer for %s [%s] invoked for repeating queued message DIM_BY_TIMER. Stop = %s' % (dev.name, dev.address, self.globals['lifx'][devId]['stopRepeatDim']))

            try:
                del self.globals['deviceTimers'][devId]['DIM_BY_TIMER']
            except:
                pass

            if not self.globals['lifx'][devId]['stopRepeatDim']:
                self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_COMMAND_MEDIUM, CMD_REPEAT_DIM_BY_TIMER, dev.id, [option, amountToBrightenDimBy, timerInterval]])

        except StandardError, e:
            self.lifxlanHandlerDebugLogger.error(u"handleTimerRepeatingQueuedDimByTimerCommand error detected. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))   


    def handleTimerDiscovery(self):
        self.methodTracer.threaddebug(u"CLASS: ThreadLifxlanHandlerMessages")

        try: 
            self.lifxlanHandlerDebugLogger.debug(u'Discovery Timer invoked')

            try:
                del self.globals['discovery']['timer']
            except:
                pass

            self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_DISCOVERY, CMD_DISCOVERY, None, None])

        except StandardError, e:
            self.lifxlanHandlerDebugLogger.error(u"handleTimerDiscovery error detected. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))   



    def clearStatusTimer(self, dev):
        self.methodTracer.threaddebug(u"CLASS: ThreadLifxlanHandlerMessages")

        if dev.id in self.globals['deviceTimers'] and 'STATUS' in self.globals['deviceTimers'][dev.id]:
            self.globals['deviceTimers'][dev.id]['STATUS'].cancel()

    def handleTimerRepeatingQueuedStatusCommand(self, dev, seconds):
        self.methodTracer.threaddebug(u"CLASS: ThreadLifxlanHandlerMessages")

        try: 
            self.lifxlanHandlerDebugLogger.debug(u'Timer for %s [%s] invoked for repeating queued message STATUS - %s seconds left' % (dev.name, dev.address, seconds))

            try:
                del self.globals['deviceTimers'][dev.id]['STATUS']
            except:
                pass

            self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_STATUS_HIGH, CMD_STATUS, dev.id, None])

            if seconds > 0:
                seconds -= 1
                self.globals['deviceTimers'][dev.id]['STATUS'] = threading.Timer(1.0, self.handleTimerRepeatingQueuedStatusCommand, [dev, seconds])
                self.globals['deviceTimers'][dev.id]['STATUS'].start()

        except StandardError, e:
            self.lifxlanHandlerDebugLogger.error(u"handleTimerRepeatingQueuedStatusCommand error detected. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))   

    def clearWaveformOffTimer(self, dev):
        self.methodTracer.threaddebug(u"CLASS: ThreadLifxlanHandlerMessages")

        if 'WAVEFORM_OFF' in self.globals['deviceTimers'][dev.id]:
            self.globals['deviceTimers'][dev.id]['WAVEFORM_OFF'].cancel()

    def handleTimerWaveformOffCommand(self, dev):
        self.methodTracer.threaddebug(u"CLASS: ThreadLifxlanHandlerMessages")

        try: 
            self.lifxlanHandlerDebugLogger.debug(u'Timer for %s [%s] invoked to turn off LIFX device (Used by Waveform)' % (dev.name, dev.address))

            try:
                del self.globals['deviceTimers'][dev.id]['WAVEFORM_OFF']
            except:
                pass

            self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_STATUS_HIGH, CMD_WAVEFORM_OFF, dev.id, None])

        except StandardError, e:
            self.lifxlanHandlerDebugLogger.error(u"handleTimerRepeatingQueuedStatusCommand error detected. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))   

    def communicationLost(self, lifxCommandDevId, lifxlanCommand):
        if self.globals['lifx'][lifxCommandDevId]['connected']:
            self.globals['lifx'][lifxCommandDevId]['connected'] = False
            lifxDev = indigo.devices[lifxCommandDevId]
            lifxDev.updateStateOnServer(key='connected', value=self.globals['lifx'][lifxCommandDevId]['connected'])
            lifxDev.setErrorStateOnServer(u"no ack")
            mac = self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].mac_addr
            ip = self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].ip_addr

            self.lifxlanHandlerMonitorLogger.error(u"No acknowledgement received from '%s' when attempting a '%s' command: MAC='%s', IP='%s'" % (lifxDev.name, lifxlanCommand, mac, ip))  

    def getColor(self, lifxCommandDevId, argLifxLanLightObject):
        lifxlanCommand = 'get_color'
        try:
            hsbk = argLifxLanLightObject.get_color()
            power = argLifxLanLightObject.power_level
            status = True
        except IOError, e:
            self.lifxlanHandlerDebugLogger.debug(u"GET_COLOR [IOERROR ERROR] for \"%s\" = %s" % (indigo.devices[lifxCommandDevId].name, e))
            status = False
            hsbk = (0, 0, 0, 3500)
            power = 0
            self.communicationLost(lifxCommandDevId, lifxlanCommand)
        except StandardError, e:
            self.lifxlanHandlerDebugLogger.debug(u"GET_COLOR [STANDARD ERROR] for \"%s\" = %s" % (indigo.devices[lifxCommandDevId].name, e)) 
            status = False
            hsbk = (0, 0, 0, 3500)
            power = 0
            self.communicationLost(lifxCommandDevId, lifxlanCommand)
        except WorkflowException, e:
            self.lifxlanHandlerDebugLogger.debug(u"GET_COLOR [WORKFLOW EXCEPTION] for \"%s\" = %s" % (indigo.devices[lifxCommandDevId].name, e))
            status = False
            hsbk = (0, 0, 0, 3500)
            power = 0
            self.communicationLost(lifxCommandDevId, lifxlanCommand)
        except:
            self.lifxlanHandlerDebugLogger.debug(u"GET_COLOR [TOTAL ERROR] for \"%s\" = %s" % (indigo.devices[lifxCommandDevId].name, sys.exc_info()[0]))
            status = False
            hsbk = (0, 0, 0, 3500)
            power = 0
            self.communicationLost(lifxCommandDevId, lifxlanCommand)

        return status, power, hsbk

    def getInfrared(self, lifxCommandDevId, argLifxLanLightObject):
        lifxlanCommand = 'get_infrared'
        try:
            infraredBrightness = argLifxLanLightObject.get_infrared()
            status = True
        except IOError, e:
            self.lifxlanHandlerDebugLogger.debug(u"GET_INFRARED [IOERROR ERROR] for \"%s\" = %s" % (indigo.devices[lifxCommandDevId].name, e))
            status = False
            infraredBrightness = 0
            self.communicationLost(lifxCommandDevId, lifxlanCommand)
        except StandardError, e:
            self.lifxlanHandlerDebugLogger.debug(u"GET_INFRARED [STANDARD ERROR] for \"%s\" = %s" % (indigo.devices[lifxCommandDevId].name, e)) 
            status = False
            infraredBrightness = 0
            self.communicationLost(lifxCommandDevId, lifxlanCommand)
        except WorkflowException, e:
            self.lifxlanHandlerDebugLogger.debug(u"GET_INFRARED [WORKFLOW EXCEPTION] for \"%s\" = %s" % (indigo.devices[lifxCommandDevId].name, e))
            status = False
            infraredBrightness = 0
            self.communicationLost(lifxCommandDevId, lifxlanCommand)
        except:
            self.lifxlanHandlerDebugLogger.debug(u"GET_INFRARED [TOTAL ERROR] for \"%s\" = %s" % (indigo.devices[lifxCommandDevId].name, sys.exc_info()[0]))
            status = False
            infraredBrightness = 0
            self.communicationLost(lifxCommandDevId, lifxlanCommand)

        return status, infraredBrightness

    def calculateBrightnesssLevelFromSV(self, argSaturation, argBrightness):

        # arguments Saturation and Brightness are (float) values 0.0 to 100.0
        saturation = argSaturation
        if saturation == 0.0:
            saturation = 1.0
        brightnessLevel = (argBrightness / 2.0) + ((100 - saturation) / 2)

        return float(brightnessLevel)


    def setHSBK(self, hue, saturation, brightness, kelvin):
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

    def updateStatusFromMsg(self, lifxCommand, lifxCommandDevId, power, hsbk):
        self.methodTracer.threaddebug(u"ThreadHandleMessages")

        try:
            lifxDev = indigo.devices[lifxCommandDevId]

            hue, saturation, brightness, kelvin = hsbk
            self.lifxlanHandlerDebugLogger.debug(u"HANDLE '%s' MESSAGE for %s: Power=%s, Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s" % (lifxCommand, indigo.devices[lifxCommandDevId].name, power, hue, saturation, brightness, kelvin))

            if power > 0:
                self.globals['lifx'][lifxCommandDevId]['onState'] = True
                self.globals['lifx'][lifxCommandDevId]['onOffState'] = 'on'
            else:
                self.globals['lifx'][lifxCommandDevId]['onState'] = False                                    
                self.globals['lifx'][lifxCommandDevId]['onOffState'] = 'off'
            self.globals['lifx'][lifxCommandDevId]['powerLevel'] = power

            # Color [0-7]: HSBK
            # Reserved [8-9]: signed 16-bit integer
            # Power [10-11]: unsigned 16-bit integer
            # Label [12-43]: string, size=32 bytes
            # Reserved [44-51]: unsigned 64-bit integer
            self.globals['lifx'][lifxCommandDevId]['hsbkHue'] = hue
            self.globals['lifx'][lifxCommandDevId]['hsbkSaturation'] = saturation
            self.globals['lifx'][lifxCommandDevId]['hsbkBrightness'] = brightness
            self.globals['lifx'][lifxCommandDevId]['hsbkKelvin'] = kelvin

            self.lifxlanHandlerDebugLogger.debug(u'LAMP IP ADDRESS [%s] vs DEBUG FILTERED IP ADDRESS [%s]' % (self.globals['lifx'][lifxCommandDevId]['ipAddress'], self.globals['debug']['debugFilteredIpAddresses']))

            self.lifxlanHandlerDebugLogger.debug(u"  LIGHT_STATE = Power: %s" % (self.globals['lifx'][lifxCommandDevId]['powerLevel']))
            self.lifxlanHandlerDebugLogger.debug(u"  LIGHT_STATE = onState: %s" % (self.globals['lifx'][lifxCommandDevId]['onState']))
            self.lifxlanHandlerDebugLogger.debug(u"  LIGHT_STATE = onOffState: %s" % (self.globals['lifx'][lifxCommandDevId]['onOffState']))

            # At this point we have an Indigo device id for the lamp and can confirm that the indigo device has been started

            self.globals['lifx'][lifxCommandDevId]['lastResponseToPollCount'] = self.globals['polling']['count']  # Set the current poll count (for 'no ack' check)
            self.lifxlanHandlerDebugLogger.debug(u'LAST RESPONSE TO POLL COUNT for %s = %s' % (lifxDev.name, self.globals['polling']['count']))

            self.globals['lifx'][lifxCommandDevId]['initialisedFromlamp'] = True

            if self.globals['lifx'][lifxCommandDevId]['onState']:
                self.globals['lifx'][lifxCommandDevId]['whenLastOnHsbkHue'] = self.globals['lifx'][lifxCommandDevId]['hsbkHue']         # Value between 0 and 65535
                self.globals['lifx'][lifxCommandDevId]['whenLastOnHsbkSaturation'] = self.globals['lifx'][lifxCommandDevId]['hsbkSaturation']  # Value between 0 and 65535 (e.g. 20% = 13107)
                self.globals['lifx'][lifxCommandDevId]['whenLastOnHsbkBrightness'] = self.globals['lifx'][lifxCommandDevId]['hsbkBrightness']  # Value between 0 and 65535
                self.globals['lifx'][lifxCommandDevId]['whenLastOnHsbkKelvin'] = self.globals['lifx'][lifxCommandDevId]['hsbkKelvin']      # Value between 2500 and 9000
                self.globals['lifx'][lifxCommandDevId]['whenLastOnPowerLevel'] = self.globals['lifx'][lifxCommandDevId]['powerLevel']      # Value between 0 and 65535

            try:
                self.globals['lifx'][lifxCommandDevId]['indigoHue'] = float((self.globals['lifx'][lifxCommandDevId]['hsbkHue'] * 360) / 65535)  # Bug Fix 2016-07-09
            except:
                self.globals['lifx'][lifxCommandDevId]['indigoHue'] = float(0)
            try:
                self.globals['lifx'][lifxCommandDevId]['indigoSaturation'] = float((self.globals['lifx'][lifxCommandDevId]['hsbkSaturation'] * 100) / 65535)
            except:
                self.globals['lifx'][lifxCommandDevId]['indigoSaturation'] = float(0)
            try:
                self.globals['lifx'][lifxCommandDevId]['indigoBrightness'] = float((self.globals['lifx'][lifxCommandDevId]['hsbkBrightness'] * 100) / 65535)
            except:
                self.globals['lifx'][lifxCommandDevId]['indigoBrightness'] = float(0)
            try:
                self.globals['lifx'][lifxCommandDevId]['indigoKelvin'] = float(self.globals['lifx'][lifxCommandDevId]['hsbkKelvin'])
            except:
                self.globals['lifx'][lifxCommandDevId]['indigoKelvin'] = float(3500)
            try:
                self.globals['lifx'][lifxCommandDevId]['indigoPowerLevel'] = float((self.globals['lifx'][lifxCommandDevId]['powerLevel'] * 100) / 65535)
            except:
                self.globals['lifx'][lifxCommandDevId]['indigoPowerLevel'] = float(0)

            hsv_hue = float(self.globals['lifx'][lifxCommandDevId]['hsbkHue']) / 65535.0
            hsv_value = float(self.globals['lifx'][lifxCommandDevId]['hsbkBrightness']) / 65535.0
            hsv_saturation = float(self.globals['lifx'][lifxCommandDevId]['hsbkSaturation']) / 65535.0
            red, green, blue = colorsys.hsv_to_rgb(hsv_hue, hsv_saturation, hsv_value)

            self.globals['lifx'][lifxCommandDevId]['indigoRed'] = float(red * 100.0)
            self.globals['lifx'][lifxCommandDevId]['indigoGreen'] = float(green * 100.0)
            self.globals['lifx'][lifxCommandDevId]['indigoBlue'] = float(blue * 100.0)

            # Set brightness according to LIFX Lamp on/off state - if 'on' use the LIFX Lamp state else set to zero
            if self.globals['lifx'][lifxCommandDevId]['onState']:
                if self.globals['lifx'][lifxCommandDevId]['indigoSaturation'] > 0.0:  # check if white or colour (colour if saturation > 0.0)
                    # Colour
                    saturation = hsv_saturation * 100.0
                    brightness = hsv_value * 100.0
                    calculatedBrightnessLevel = self.calculateBrightnesssLevelFromSV(saturation, brightness)  # returns Float value
                    self.globals['lifx'][lifxCommandDevId]['brightnessLevel'] = int(calculatedBrightnessLevel * (self.globals['lifx'][lifxCommandDevId]['powerLevel'] / 65535.0))
                    # self.globals['lifx'][lifxCommandDevId]['brightnessLevel'] = int(self.globals['lifx'][lifxCommandDevId]['powerLevel'])  # returns Int value
                    # self.lifxlanHandlerDebugLogger.info(u'BRIGHTNESS LEVEL [RECEIVE]: [%s] = %s' % (type(self.globals['lifx'][lifxCommandDevId]['brightnessLevel']), self.globals['lifx'][lifxCommandDevId]['brightnessLevel']))       
                else:
                    # White
                    self.globals['lifx'][lifxCommandDevId]['brightnessLevel'] = int(self.globals['lifx'][lifxCommandDevId]['indigoBrightness'] * (self.globals['lifx'][lifxCommandDevId]['powerLevel'] / 65535.0))
                    self.globals['lifx'][lifxCommandDevId]['indigoWhiteLevel'] = float(self.globals['lifx'][lifxCommandDevId]['indigoBrightness'])
            else:       
                self.globals['lifx'][lifxCommandDevId]['brightnessLevel'] = 0

            self.globals['lifx'][lifxCommandDevId]['connected'] = True
            self.globals['lifx'][lifxCommandDevId]['noAckState'] = False

            keyValueList = [
                {'key': 'ipAddress', 'value': self.globals['lifx'][lifxCommandDevId]['ipAddress']},

                {'key': 'lifxOnState', 'value': self.globals['lifx'][lifxCommandDevId]['onState']},
                {'key': 'lifxOnOffState', 'value': self.globals['lifx'][lifxCommandDevId]['onOffState']},

                {'key': 'hsbkHue', 'value': self.globals['lifx'][lifxCommandDevId]['hsbkHue']},
                {'key': 'hsbkSaturation', 'value': self.globals['lifx'][lifxCommandDevId]['hsbkSaturation']},
                {'key': 'hsbkBrightness', 'value': self.globals['lifx'][lifxCommandDevId]['hsbkBrightness']},
                {'key': 'hsbkKelvin', 'value': self.globals['lifx'][lifxCommandDevId]['hsbkKelvin']},
                {'key': 'powerLevel', 'value': self.globals['lifx'][lifxCommandDevId]['powerLevel']},

                {'key': 'groupLabel', 'value': self.globals['lifx'][lifxCommandDevId]['groupLabel']},
                {'key': 'locationLabel', 'value': self.globals['lifx'][lifxCommandDevId]['locationLabel']},

                {'key': 'whenLastOnHsbkHue', 'value': self.globals['lifx'][lifxCommandDevId]['whenLastOnHsbkHue']},
                {'key': 'whenLastOnHsbkSaturation', 'value': self.globals['lifx'][lifxCommandDevId]['whenLastOnHsbkSaturation']},
                {'key': 'whenLastOnHsbkBrightness', 'value': self.globals['lifx'][lifxCommandDevId]['whenLastOnHsbkBrightness']},
                {'key': 'whenLastOnHsbkKelvin', 'value': self.globals['lifx'][lifxCommandDevId]['whenLastOnHsbkKelvin']},
                {'key': 'whenLastOnPowerLevel', 'value': self.globals['lifx'][lifxCommandDevId]['whenLastOnPowerLevel']},

                {'key': 'whiteTemperature', 'value': self.globals['lifx'][lifxCommandDevId]['indigoKelvin']},
                {'key': 'whiteLevel', 'value': self.globals['lifx'][lifxCommandDevId]['indigoWhiteLevel']},

                {'key': 'indigoHue', 'value': self.globals['lifx'][lifxCommandDevId]['indigoHue']},
                {'key': 'indigoSaturation', 'value': self.globals['lifx'][lifxCommandDevId]['indigoSaturation']},
                {'key': 'indigoBrightness', 'value': self.globals['lifx'][lifxCommandDevId]['indigoBrightness']},
                {'key': 'indigoKelvin', 'value': self.globals['lifx'][lifxCommandDevId]['indigoKelvin']},
                {'key': 'indigoPowerLevel', 'value': self.globals['lifx'][lifxCommandDevId]['indigoPowerLevel']},

                {'key': 'brightnessLevel', 'value': int(self.globals['lifx'][lifxCommandDevId]['brightnessLevel']), 'uiValue': str(self.globals['lifx'][lifxCommandDevId]['brightnessLevel'])},

                {'key': 'duration', 'value': self.globals['lifx'][lifxCommandDevId]['duration']},
                {'key': 'durationDimBrighten', 'value': self.globals['lifx'][lifxCommandDevId]['durationDimBrighten']},
                {'key': 'durationOn', 'value': self.globals['lifx'][lifxCommandDevId]['durationOn']},
                {'key': 'durationOff', 'value': self.globals['lifx'][lifxCommandDevId]['durationOff']},
                {'key': 'durationColorWhite', 'value': self.globals['lifx'][lifxCommandDevId]['durationColorWhite']},
                {'key': 'noAckState', 'value': self.globals['lifx'][lifxCommandDevId]['noAckState']},
                {'key': 'connected', 'value': self.globals['lifx'][lifxCommandDevId]['connected']}

            ]

            props = lifxDev.pluginProps
            if ("SupportsRGB" in props) and props["SupportsRGB"]:
                keyValueList.append({'key': 'redLevel', 'value': self.globals['lifx'][lifxCommandDevId]['indigoRed']})
                keyValueList.append({'key': 'greenLevel', 'value': self.globals['lifx'][lifxCommandDevId]['indigoGreen']})
                keyValueList.append({'key': 'blueLevel', 'value': self.globals['lifx'][lifxCommandDevId]['indigoBlue']})

            lifxDev.updateStatesOnServer(keyValueList)

            lifxDev.updateStateImageOnServer(indigo.kStateImageSel.Auto)

        except StandardError, e:
            self.lifxlanHandlerDebugLogger.error(u"StandardError detected in 'handleLifxLampMessage'. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))   
