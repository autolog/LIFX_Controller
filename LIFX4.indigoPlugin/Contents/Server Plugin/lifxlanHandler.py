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
import time as timeMethod
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

        self.threadStop = event

        self.lifxlan = None

    def run(self):
        self.methodTracer.threaddebug(u"ThreadLifxlanHandlerMessages")
 
        try:
            # Initialise the LIFX Lamps on startup
            self.lifxlan = LifxLAN(None)  # Force discovery of LIFX Devices
            self.lifxDevices = self.lifxlan.get_lights()

            self.numberOfLifxDevices = len(self.lifxDevices)
            self.lifxlanHandlerMonitorLogger.info(u"Number of LIFX devices discovered: %d" % int(len(self.lifxDevices)))

            self.lifxDiscoveredDevicesMapping = dict()
            for lifxDevice in self.lifxDevices:
                self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr] = dict()
                self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['lifxlanDeviceIndex'] = self.lifxDevices.index(lifxDevice)
                self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['discovered'] = True
                self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['ipAddress'] = lifxDevice.ip_addr
                self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['port'] = lifxDevice.port
                self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['lifxDevId'] = 0  # Indigo Device Id (not yet known)

                lifxDeviceRefreshed = False
                try:
                    lifxDevice.req_with_resp(GetService, StateService)
                    lifxDevice.refresh()
                    lifxDeviceRefreshed = True
                except WorkflowException:
                    pass

                indexUi = self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['lifxlanDeviceIndex'] + 1

                if lifxDeviceRefreshed:
                    self.lifxlanHandlerMonitorLogger.info(u"LIFX Device %d: '%s' [%s] at address %s on port %s'" % (indexUi, lifxDevice.label, lifxDevice.mac_addr, lifxDevice.ip_addr, lifxDevice.port))
                else:
                    self.lifxlanHandlerMonitorLogger.info(u"LIFX Device %d: '-- Name not known --' [%s] at address %s on port %s'" % (indexUi, lifxDevice.mac_addr, lifxDevice.ip_addr, lifxDevice.port))

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

                    if lifxCommand == 'STOPTHREAD':
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

                    self.lifxlanHandlerDebugLogger.debug(u"Dequeued lifxlanHandler Command '%s' to process with priority: %s" % (lifxCommand, lifxQueuePriority))

                    if lifxCommand == 'DISCOVERY':
                        # Discover LIFX Lamps on demand
                        self.lifxlan = LifxLAN(None)  # Force discovery of LIFX Devices
                        self.lifxDevices = self.lifxlan.get_lights()

                        self.numberOfLifxDevices = len(self.lifxDevices)
                        self.lifxlanHandlerMonitorLogger.info(u"Number of LIFX devices discovered: %d" % int(len(self.lifxDevices)))

                        try:
                            test = self.lifxDiscoveredDevicesMapping
                        except AttributeError:
                            self.lifxDiscoveredDevicesMapping = dict()

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

                            lifxDeviceRefreshed = False
                            try:
                                lifxDevId = self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['lifxDevId']
                                if lifxDevId == 0 or lifxDevId not in self.globals['lifx'] or not self.globals['lifx'][lifxDevId]['connected']: 
                                    # indigo.server.log(u"REFRESHING '%s'" % lifxDevice.ip_addr)
                                    lifxDevice.req_with_resp(GetService, StateService)
                                    lifxDevice.refresh()
                                    lifxDeviceRefreshed = True
                                #else:
                                    #indigo.server.log(u"SKIPPING REFRESH FOR '%s'" % lifxDevice.ip_addr)
                            except WorkflowException:
                                pass

                            if lifxDeviceRefreshed:

                                indexUi = self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['lifxlanDeviceIndex'] + 1

                                self.lifxlanHandlerMonitorLogger.info(u"LIFX Device %d: '%s' [%s] at address %s on port %s' [DEV.ID = %s]" % (indexUi, lifxDevice.label, lifxDevice.mac_addr, lifxDevice.ip_addr, lifxDevice.port, self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['lifxDevId']))

                                lifxDeviceMatchedtoIndigoDevice = False
                                for dev in indigo.devices.iter("self"):
                                    if lifxDevice.mac_addr == dev.address:
                                        lifxDeviceMatchedtoIndigoDevice = True
                                        self.lifxDiscoveredDevicesMapping[lifxDevice.mac_addr]['lifxDevId'] = dev.id  # Indigo Device Id
                                        break
                                                
                                if not lifxDeviceMatchedtoIndigoDevice:
                                    lifxDeviceLabel = str(lifxDevice.label).rstrip()
                                    newDev = (indigo.device.create(protocol=indigo.kProtocol.Plugin,
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
                                                  "WhiteTemperatureMax": 9000  
                                                  },
                                           folder=self.globals['folders']['DevicesId']))
                            continue

                    if lifxCommand == 'STATUS':
                        ioStatus, power, hsbk = self.getColor(lifxCommandDevId, self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']])
                        if ioStatus:
                            wasConnected = self.globals['lifx'][lifxCommandDevId]['connected']  
                            self.updateStatusFromMsg(lifxCommand, lifxCommandDevId, power, hsbk)

                            if not wasConnected:
                                self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_LOW, 'GETVERSION', lifxCommandDevId, None])
                                self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_LOW, 'GETHOSTFIRMWARE', lifxCommandDevId, None])
                                self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_LOW, 'GETWIFIFIRMWARE', lifxCommandDevId, None])
                                self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_LOW, 'GETWIFIINFO', lifxCommandDevId, None])

                            props = lifxDev.pluginProps
                            if ("SupportsInfrared" in props) and props["SupportsInfrared"]:
                                try:
                                    infraredBrightness = self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].get_infrared()
                                except:
                                    sysTraceback = 'No INFO' if sys.exc_info()[2] is None else sys.exc_info()[2]
                                    sysTraceBackUI = ''.join(traceback.format_tb(sysTraceback)) 
                                    self.lifxlanHandlerDebugLogger.error(u"'SupportsInfrared' error detected in LIFX Send Receive Message with LIFX device '%s': '%s' - %s" % (lifxDev.name, sys.exc_info()[1], sysTraceBackUI)) 

                                    infraredBrightness = 0
                                    self.communicationLost(lifxCommandDevId)

                                IndigoInfraredBrightness = float((infraredBrightness * 100) / 65535)
                                keyValueList = [
                                    {'key': 'infraredBrightness', 'value': infraredBrightness},
                                    {'key': 'indigoInfraredBrightness', 'value': IndigoInfraredBrightness}]
                                lifxDev.updateStatesOnServer(keyValueList)

                                self.lifxlanHandlerDebugLogger.debug(u"LifxlanHandler Infrared Level for '%s' is: %s" % (lifxDev.name, IndigoInfraredBrightness))


                        self.globals['lifx'][lifxCommandDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if (lifxCommand == 'ON') or (lifxCommand == 'OFF') or (lifxCommand == 'WAVEFORM_OFF') or (lifxCommand == 'IMMEDIATE-ON'):
                        if self.globals['lifx'][lifxCommandDevId]['connected']:

                            self.lifxlanHandlerDebugLogger.debug(u"Processing %s for '%s' " % (lifxCommand, indigo.devices[lifxCommandDevId].name))

                            lifxDev = indigo.devices[lifxCommandDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            if lifxCommand == 'ON':
                                duration = float(self.globals['lifx'][lifxCommandDevId]['durationOn'])
                                power = 65535
                            elif lifxCommand == 'IMMEDIATE-ON':
                                duration = 0
                                power = 65535
                            elif lifxCommand == 'OFF':
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
                                self.communicationLost(lifxCommandDevId)
                                continue

                            self.globals['deviceTimers'][lifxCommandDevId]['STATUS'] = threading.Timer(1.0, self.handleTimerRepeatingQueuedStatusCommand, [lifxDev, timerDuration])
                            self.globals['deviceTimers'][lifxCommandDevId]['STATUS'].start()
                        
                        self.globals['lifx'][lifxCommandDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if (lifxCommand == 'INFRARED_ON') or (lifxCommand == 'INFRARED_OFF') or (lifxCommand == 'INFRARED_SET'):
                        if self.globals['lifx'][lifxCommandDevId]['connected']:

                            self.lifxlanHandlerDebugLogger.debug(u"Processing %s for '%s' " % (lifxCommand, indigo.devices[lifxCommandDevId].name))

                            lifxDev = indigo.devices[lifxCommandDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            if lifxCommand == 'INFRARED_OFF':
                                infraredBrightness = 0
                            elif lifxCommand == 'INFRARED_ON':
                                infraredBrightness = 65535
                            elif lifxCommand == 'INFRARED_SET':
                                infraredBrightness = lifxCommandParameters[0]
                                infraredBrightness = int((infraredBrightness * 65535.0) / 100.0)
                                if infraredBrightness > 65535:
                                    infraredBrightness = 65535  # Just in case ;)

                            try:
                                self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_infrared(infraredBrightness)
                                self.lifxlanHandlerDebugLogger.debug(u"Processing %s for '%s'; Infrared Brightness = %s" % (lifxCommand, indigo.devices[lifxCommandDevId].name, infraredBrightness))
                            except:
                                self.communicationLost(lifxCommandDevId)
                                continue

                            self.globals['deviceTimers'][lifxCommandDevId]['STATUS'] = threading.Timer(1.0, self.handleTimerRepeatingQueuedStatusCommand, [lifxDev, 2])
                            self.globals['deviceTimers'][lifxCommandDevId]['STATUS'].start()
                        
                        self.globals['lifx'][lifxCommandDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if lifxCommand == 'BRIGHTNESS':
                        if self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']:
                            newBrightness = lifxCommandParameters[0]
                            newBrightness = int((newBrightness * 65535.0) / 100.0)

                            lifxDev = indigo.devices[lifxCommandDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            ioStatus, power, hsbk = self.getColor(lifxCommandDevId, self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']])

                            self.lifxlanHandlerDebugLogger.debug(u"LIFX COMMAND [BRIGHTNESS] IOSTATUS for %s =  %s, HSBK = %s" % (indigo.devices[lifxCommandDevId].name, ioStatus, hsbk))
                            if ioStatus:
                                hue = hsbk[0]
                                saturation = hsbk[1]
                                brightness = hsbk[2]
                                kelvin = hsbk[3]

                                self.lifxlanHandlerDebugLogger.debug(u'LIFX COMMAND [BRIGHTNESS]; GET-COLOR for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s' % (indigo.devices[lifxCommandDevId].name,  hue, saturation, brightness, kelvin))   
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

                                if newBrightness > 0 and power == 0:
                                    # Need to reset existing brightness to 0 before turning on
                                    try:
                                        hsbkWithBrightnessZero = [hue, saturation, 0, kelvin]
                                        self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_color(hsbkWithBrightnessZero, 0)
                                    except:
                                        self.communicationLost(lifxCommandDevId)
                                        continue
                                    # Need to turn on LIFX device as currently off
                                    power = 65535
                                    try:
                                        self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_power(power, 0)
                                    except:
                                        self.communicationLost(lifxCommandDevId)
                                        continue

                                hsbk = [hue, saturation, brightness, kelvin]
                                if lifxCommand == 'BRIGHTNESS':
                                    duration = int(self.globals['lifx'][lifxCommandDevId]['durationDimBrighten'] * 1000)
                                else:
                                    duration = 0

                                self.lifxlanHandlerDebugLogger.debug(u'LIFX COMMAND [BRIGHTNESS]; SET-COLOR for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s' % (indigo.devices[lifxCommandDevId].name,  hue, saturation, brightness, kelvin))   

                                try:
                                    self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_color(hsbk, duration)
                                except:
                                    self.communicationLost(lifxCommandDevId)
                                    continue

                                if lifxCommand == 'BRIGHTNESS':
                                    timerDuration = int(self.globals['lifx'][lifxCommandDevId]['durationDimBrighten'])
                                    self.globals['deviceTimers'][lifxCommandDevId]['STATUS'] = threading.Timer(1.0, self.handleTimerRepeatingQueuedStatusCommand, [lifxDev, timerDuration])

                                    self.globals['deviceTimers'][lifxCommandDevId]['STATUS'].start()

                        self.globals['lifx'][lifxCommandDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if lifxCommand == 'brightenDimByTimer':
                        if self.globals['lifx'][lifxCommandDevId]['connected']:
                            pass

                    if lifxCommand == 'DIM' or lifxCommand == 'BRIGHTEN':
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

                            hsbk = [hue, saturation, brightness, kelvin]

                            # self.lifxlanHandlerDebugLogger.debug(u'LIFX COMMAND [BRIGHTNESS]; SET-COLOR for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s' % (indigo.devices[lifxCommandDevId].name,  hue, saturation, brightness, kelvin))   

                            try:
                                self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_color(hsbk, 0, True)
                            except:
                                self.communicationLost(lifxCommandDevId)
                                continue

                        self.globals['lifx'][lifxCommandDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if lifxCommand == 'WHITE':
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
                                        hsbkWithBrightnessZero = [hue, saturation, 0, kelvin]
                                        self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_color(hsbkWithBrightnessZero, 0)
                                    except:
                                        self.communicationLost(lifxCommandDevId)
                                        continue
                                    # Need to turn on LIFX device as currently off
                                    power = 65535
                                    try:
                                        self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_power(power, 0)
                                    except:
                                        self.communicationLost(lifxCommandDevId)
                                        continue
                                        
                                saturation = 0
                                brightness = int((targetWhiteLevel * 65535.0) / 100.0)
                                kelvin = int(targetWhiteTemperature)
                                hsbk = [hue, saturation, brightness, kelvin]
                                duration = int(self.globals['lifx'][lifxCommandDevId]['durationColorWhite'] * 1000)

                                self.lifxlanHandlerDebugLogger.debug(u'LIFX COMMAND [WHITE]; SET-COLOR for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s' % (indigo.devices[lifxCommandDevId].name,  hue, saturation, brightness, kelvin))   

                                try:
                                    self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_color(hsbk, duration)
                                except:
                                    self.communicationLost(lifxCommandDevId)
                                    continue

                                timerDuration = int(self.globals['lifx'][lifxCommandDevId]['durationColorWhite'])
                                self.globals['deviceTimers'][lifxCommandDevId]['STATUS'] = threading.Timer(1.0, self.handleTimerRepeatingQueuedStatusCommand, [lifxDev, timerDuration])

                                self.globals['deviceTimers'][lifxCommandDevId]['STATUS'].start()

                        self.globals['lifx'][lifxCommandDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if lifxCommand == 'COLOR':
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
                                        hsbkWithBrightnessZero = [hue, saturation, 0, kelvin]
                                        self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_color(hsbkWithBrightnessZero, 0)
                                    except:
                                        self.communicationLost(lifxCommandDevId)
                                        continue
                                    # Need to turn on LIFX device as currently off
                                    power = 65535
                                    try:
                                        self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_power(power, 0)
                                    except:
                                        self.communicationLost(lifxCommandDevId)
                                        continue

                                hue = targetHue
                                saturation = targetSaturation
                                brightness = targetBrightness
                                hsbk = [hue, saturation, brightness, kelvin]
                                duration = int(self.globals['lifx'][lifxCommandDevId]['durationColorWhite'] * 1000)

                                self.lifxlanHandlerDebugLogger.debug(u'LIFX COMMAND [COLOR]; SET-COLOR for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s, Duration=%s' % (indigo.devices[lifxCommandDevId].name,  hue, saturation, brightness, kelvin, duration))   

                                try:
                                    self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_color(hsbk, duration)
                                except:
                                    self.communicationLost(lifxCommandDevId)
                                    continue

                                timerDuration = int(self.globals['lifx'][lifxCommandDevId]['durationColorWhite'])
                                self.globals['deviceTimers'][lifxCommandDevId]['STATUS'] = threading.Timer(1.0, self.handleTimerRepeatingQueuedStatusCommand, [lifxDev, timerDuration])

                                self.globals['deviceTimers'][lifxCommandDevId]['STATUS'].start()

                        self.globals['lifx'][lifxCommandDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if lifxCommand == 'STANDARD':
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
                                hsbk = [hue, saturation, brightness, kelvin]

                                if targetDuration != '-':
                                    duration = int(float(targetDuration) * 1000)
                                else:
                                    duration = int(self.globals['lifx'][lifxCommandDevId]['durationColorWhite'] * 1000)

                                self.lifxlanHandlerDebugLogger.debug(u'LIFX COMMAND [STANDARD][%s]; SET-COLOR for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s, duration=%s' % (targetMode, indigo.devices[lifxCommandDevId].name,  hue, saturation, brightness, kelvin, duration))   

                                if power == 0 and turnOnIfOff:
                                    try:
                                        self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_color(hsbk, 0)
                                    except:
                                        self.communicationLost(lifxCommandDevId)
                                        continue
                                    power = 65535
                                    try:
                                        self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_power(power, duration)
                                    except:
                                        self.communicationLost(lifxCommandDevId)
                                        continue
                                else:
                                    if power == 0:
                                        duration = 0  # As power is off. might as well do apply command straight away
                                    try:
                                        self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_color(hsbk, duration)
                                    except:
                                        self.communicationLost(lifxCommandDevId)
                                        continue

                                timerDuration = int(duration/1000)  # Convert back from milliseconds
                                self.globals['deviceTimers'][lifxCommandDevId]['STATUS'] = threading.Timer(1.0, self.handleTimerRepeatingQueuedStatusCommand, [lifxDev, timerDuration])

                                self.globals['deviceTimers'][lifxCommandDevId]['STATUS'].start()

                        self.globals['lifx'][lifxCommandDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if lifxCommand == 'WAVEFORM':
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
                                        self.communicationLost(lifxCommandDevId)
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
                                hsbk = [hue, saturation, brightness, kelvin]

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
                                    self.communicationLost(lifxCommandDevId)
                                    continue

                                if not lifxDeviceAlreadyOn:
                                    timerSetFor = float((float(period) / 1000.0) * cycles)
                                    self.globals['deviceTimers'][lifxCommandDevId]['WAVEFORM_OFF'] = threading.Timer(timerSetFor, self.handleTimerWaveformOffCommand, [lifxDev])
                                    self.globals['deviceTimers'][lifxCommandDevId]['WAVEFORM_OFF'].start()

                        self.globals['lifx'][lifxCommandDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if lifxCommand == 'SETLABEL':
                        if self.globals['lifx'][lifxCommandDevId]['connected']:

                            self.lifxlanHandlerDebugLogger.debug(u"Processing %s for '%s' " % (lifxCommand, indigo.devices[lifxCommandDevId].name))

                            lifxDev = indigo.devices[lifxCommandDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            try:
                                self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].set_label(lifxDev.name)
                            except:
                                self.communicationLost(lifxCommandDevId)

                        self.globals['lifx'][lifxCommandDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if lifxCommand == 'GETVERSION':
                        if self.globals['lifx'][lifxCommandDevId]['connected']:

                            self.lifxlanHandlerDebugLogger.debug(u"Processing %s for '%s' " % (lifxCommand, indigo.devices[lifxCommandDevId].name))

                            lifxDev = indigo.devices[lifxCommandDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            try:
                                product = self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].get_product()
                            except:
                                self.communicationLost(lifxCommandDevId)
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

                    if lifxCommand == 'GETHOSTFIRMWARE':
                        if self.globals['lifx'][lifxCommandDevId]['connected']:

                            self.lifxlanHandlerDebugLogger.debug(u"Processing %s for '%s' " % (lifxCommand, indigo.devices[lifxCommandDevId].name))

                            lifxDev = indigo.devices[lifxCommandDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            try:
                                firmware_version = str(self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].get_host_firmware_version())
                            except:
                                self.communicationLost(lifxCommandDevId)
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

                    if lifxCommand == 'GETPORT':
                        if self.globals['lifx'][lifxCommandDevId]['connected']:

                            self.lifxlanHandlerDebugLogger.debug(u"Processing %s for '%s' " % (lifxCommand, indigo.devices[lifxCommandDevId].name))

                            lifxDev = indigo.devices[lifxCommandDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            try:
                                port = str(self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].get_port())
                            except:
                                self.communicationLost(lifxCommandDevId)
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

                    if lifxCommand == 'GETWIFIFIRMWARE':
                        if self.globals['lifx'][lifxCommandDevId]['connected']:

                            self.lifxlanHandlerDebugLogger.debug(u"Processing %s for '%s' " % (lifxCommand, indigo.devices[lifxCommandDevId].name))

                            lifxDev = indigo.devices[lifxCommandDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            try:
                                wifi_firmware_version = str(self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].get_wifi_firmware_version())
                            except:
                                self.communicationLost(lifxCommandDevId)
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

                    if lifxCommand == 'GETWIFIINFO':
                        if self.globals['lifx'][lifxCommandDevId]['connected']:

                            self.lifxlanHandlerDebugLogger.debug(u"Processing %s for '%s' " % (lifxCommand, indigo.devices[lifxCommandDevId].name))

                            lifxDev = indigo.devices[lifxCommandDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            try:
                                signal, tx, rx = self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].get_wifi_info_tuple()
                            except:
                                self.communicationLost(lifxCommandDevId)
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

                    if lifxCommand == 'GETHOSTINFO':
                        self.lifxlanHandlerDebugLogger.debug(u"Processing %s" % lifxCommand)

                        payload = ''
                        dev = sendMessage[1]
                        ipAddress = self.globals['lifx'][dev.id]['ipAddress']
                        self.outputMessageToLifxDevice(ipAddress, DEV_GET_HOST_INFO, dev, payload)

                        continue

                    if lifxCommand == 'GETLOCATION':
                        self.lifxlanHandlerDebugLogger.debug(u"Processing %s" % lifxCommand)

                        payload = ''
                        dev = sendMessage[1]
                        ipAddress = self.globals['lifx'][dev.id]['ipAddress']
                        self.outputMessageToLifxDevice(ipAddress, DEV_GET_LOCATION, dev, payload)

                        continue

                    if lifxCommand == 'GETGROUP':
                        self.lifxlanHandlerDebugLogger.debug(u"Processing %s" % lifxCommand)

                        payload = ''
                        dev = sendMessage[1]
                        ipAddress = self.globals['lifx'][dev.id]['ipAddress']
                        self.outputMessageToLifxDevice(ipAddress, DEV_GET_GROUP, dev, payload)

                        continue

                    if lifxCommand == 'GETINFO':
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

            self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_STATUS_HIGH, 'STATUS', dev.id, None])

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

            self.globals['queues']['messageToSend'][dev.id].put([QUEUE_PRIORITY_STATUS_HIGH, 'WAVEFORM_OFF'])

        except StandardError, e:
            self.lifxlanHandlerDebugLogger.error(u"handleTimerRepeatingQueuedStatusCommand error detected. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))   

    def communicationLost(self, lifxCommandDevId):
        if self.globals['lifx'][lifxCommandDevId]['connected']:
            self.globals['lifx'][lifxCommandDevId]['connected'] = False
            lifxDev = indigo.devices[lifxCommandDevId]
            lifxDev.updateStateOnServer(key='connected', value=self.globals['lifx'][lifxCommandDevId]['connected'])
            lifxDev.setErrorStateOnServer(u"no ack")
            name = self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].label
            mac = self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].mac_addr
            ip = self.lifxDevices[self.globals['lifx'][lifxCommandDevId]['lifxlanDeviceIndex']].ip_addr

            self.lifxlanHandlerMonitorLogger.error(u"No acknowledgement received from '%s': MAC='%s', IP='%s'" % (lifxDev.name, mac, ip))  

    def getColor(self, lifxCommandDevId, argLifxLanLightObject):
        try:
            hsbk = argLifxLanLightObject.get_color()
            power = argLifxLanLightObject.power_level
            status = True
        except IOError, e:
            self.lifxlanHandlerDebugLogger.debug(u"GET_COLOR [IOERROR ERROR] for \"%s\" = %s" % (indigo.devices[lifxCommandDevId].name, e))
            status = False
            hsbk = (0, 0, 0, 3500)
            power = 0
            self.communicationLost(lifxCommandDevId)
        except StandardError, e:
            self.lifxlanHandlerDebugLogger.debug(u"GET_COLOR [STANDARD ERROR] for \"%s\" = %s" % (indigo.devices[lifxCommandDevId].name, e)) 
            status = False
            hsbk = (0, 0, 0, 3500)
            power = 0
            self.communicationLost(lifxCommandDevId)

        except WorkflowException, e:
            self.lifxlanHandlerDebugLogger.debug(u"GET_COLOR [WORKFLOW EXCEPTION] for \"%s\" = %s" % (indigo.devices[lifxCommandDevId].name, e))
            status = False
            hsbk = (0, 0, 0, 3500)
            power = 0
            self.communicationLost(lifxCommandDevId)

        except:
            self.lifxlanHandlerDebugLogger.debug(u"GET_COLOR [TOTAL ERROR] for \"%s\" = %s" % (indigo.devices[lifxCommandDevId].name, sys.exc_info()[0]))
            status = False
            hsbk = (0, 0, 0, 3500)
            power = 0
            self.communicationLost(lifxCommandDevId)

        return status, power, hsbk

    def calculateBrightnesssLevelFromSV(self, argSaturation, argBrightness):

        # arguments Saturation and Brightness are (float) values 0.0 to 100.0
        saturation = argSaturation
        if saturation == 0.0:
            saturation = 1.0
        brightnessLevel = (argBrightness / 2.0) + ((100 - saturation) / 2)

        return float(brightnessLevel)

    def setHsbk(self, hsbk):
        try:
            hue = struct.unpack("<H", hsbk[0:2])[0]  # '<' = little-endian and 'H' = unsigned integer
            saturation = struct.unpack("<H", hsbk[2:4])[0]
            brightness = struct.unpack("<H", hsbk[4:6])[0]
            kelvin = struct.unpack("<H", hsbk[6:8])[0]

            return int(hue), int(saturation), int(brightness), int(kelvin)
        except StandardError, e:
            self.generalLogger.error(u"StandardError detected setting LIFX lamp HSBK values. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))
            return int(0), int(0), int(0), int(0)

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
