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
import socket
import struct
import sys
import threading
from time import time, sleep
import traceback

from constants import *
from lifxlan.lifxlan import *


class ThreadSendReceiveMessages(threading.Thread):

    # This class controls the sending of commands to the lifx lamp and handles their response.

    def __init__(self, globals):

        threading.Thread.__init__(self)

        self.globals = globals[0]

        self.sendReceiveMonitorLogger = logging.getLogger("Plugin.MonitorSendReceive")
        self.sendReceiveMonitorLogger.setLevel(self.globals['debug']['monitorSendReceive'])

        self.sendReceiveDebugLogger = logging.getLogger("Plugin.DebugSendReceive")
        self.sendReceiveDebugLogger.setLevel(self.globals['debug']['debugSendReceive'])

        self.methodTracer = logging.getLogger("Plugin.method")  
        self.methodTracer.setLevel(self.globals['debug']['debugMethodTrace'])

        self.sendReceiveDebugLogger.debug(u"Initialising LIFX Send and Receive Message Thread")  

    def run(self):
        self.methodTracer.threaddebug(u"ThreadSendReceiveMessages")
 
        try:
            self.sendReceiveDebugLogger.debug(u"LIFX Send Receive Message Thread initialised.")    

            while True:

                try:
                    lifxQueuedPriorityCommandData = self.globals['queues']['messageToSend'].get(True,5)

                    # self.sendReceiveDebugLogger.debug(u"LIFX QUEUED PRIORITY COMMAND DATA: %s" % lifxQueuedPriorityCommandData)    
                    lifxQueuePriority, lifxCommand, lifxCommandParameters = lifxQueuedPriorityCommandData

                    # Check if monitoring / debug options have changed and if so set accordingly
                    if self.globals['debug']['previousMonitorSendReceive'] != self.globals['debug']['monitorSendReceive']:
                        self.globals['debug']['previousMonitorSendReceive'] = self.globals['debug']['monitorSendReceive']
                        self.sendReceiveMonitorLogger.setLevel(self.globals['debug']['monitorSendReceive'])
                    if self.globals['debug']['previousDebugSendReceive'] != self.globals['debug']['debugSendReceive']:
                        self.globals['debug']['previousDebugSendReceive'] = self.globals['debug']['debugSendReceive']
                        self.sendReceiveDebugLogger.setLevel(self.globals['debug']['debugSendReceive'])
                    if self.globals['debug']['previousDebugMethodTrace'] !=self.globals['debug']['debugMethodTrace']:
                        self.globals['debug']['previousDebugMethodTrace'] = self.globals['debug']['debugMethodTrace']
                        self.methodTracer.setLevel(self.globals['debug']['debugMethodTrace'])

                    self.sendReceiveDebugLogger.debug(u"Dequeued Send Message to process [LIFXCOMMAND]: %s" % (lifxCommand))

                    # Handle commands to all LIFX lamps

                    if lifxCommand == 'STOPTHREAD':
                        break  # Exit While loop and quit thread


                    if lifxCommand == 'STATUSPOLLING':
                        for lifxDevId in self.globals['lifx']:
                            if self.globals['lifx'][lifxDevId]["started"] == True:
                                self.sendReceiveDebugLogger.debug(u"PROCESSING %s FOR %s" % (lifxCommand, indigo.devices[lifxDevId].name))
                                self.globals['queues']['messageToSend'].put([QUEUE_PRIORITY_STATUS_MEDIUM, 'STATUS', [lifxDevId]])
                                self.globals['queues']['messageToSend'].put([QUEUE_PRIORITY_LOW, 'GETWIFIINFO', [lifxDevId]])
                                 
                        continue  

                    if lifxCommand == 'STATUS':
                        lifxDevId = lifxCommandParameters[0]

                        if self.globals['lifx'][lifxDevId]["started"] == True:
                            lifxDev = indigo.devices[lifxDevId]

                            if self.globals['lifx'][lifxDevId]["started"] == True:
                                # self.sendReceiveDebugLogger.debug(u"PROCESSING [1] %s FOR '%s'" % (lifxCommand, indigo.devices[lifxDevId].name))

                                ioStatus, power, hsbk = self.getColor(lifxDev, self.globals['lifx'][lifxDevId]['lifxLanLightObject'])
                                if ioStatus:
                                    self.updateStatusFromMsg(lifxCommand, lifxDevId, power, hsbk)
                                # self.sendReceiveDebugLogger.debug(u"PROCESSING [2] %s FOR '%s'" % (lifxCommand, indigo.devices[lifxDevId].name))
                            props = lifxDev.pluginProps
                            if ("SupportsInfrared" in props) and props["SupportsInfrared"]:
                                try:
                                    infraredBrightness = self.globals['lifx'][lifxDevId]['lifxLanLightObject'].get_infrared()
                                except:
                                    self.sendReceiveDebugLogger.error(u"SupportsInfrared ERROR detected in LIFX Send Receive Message Thread. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, sys.exc_info()[0]))     
                                    infraredBrightness = 0
                                    self.communicationLost(lifxDev)

                                IndigoInfraredBrightness = float((infraredBrightness * 100) /  65535)
                                keyValueList = [
                                    {'key': 'infraredBrightness', 'value': infraredBrightness},
                                    {'key': 'indigoInfraredBrightness', 'value': IndigoInfraredBrightness}]
                                lifxDev.updateStatesOnServer(keyValueList)

                        self.globals['lifx'][lifxDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if (lifxCommand == 'ON') or (lifxCommand == 'OFF') or (lifxCommand == 'WAVEFORM_OFF') or (lifxCommand == 'IMMEDIATE-ON'):
                        lifxDevId = lifxCommandParameters[0]

                        if self.globals['lifx'][lifxDevId]["started"] == True:

                            self.sendReceiveDebugLogger.debug(u"Processing %s for '%s' " % (lifxCommand, indigo.devices[lifxDevId].name))

                            lifxDev = indigo.devices[lifxDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            if lifxCommand == 'ON':
                                duration = float(self.globals['lifx'][lifxDevId]['durationOn'])
                                power = 65535
                            elif lifxCommand == 'IMMEDIATE-ON':
                                duration = 0
                                power = 65535
                            elif lifxCommand == 'OFF':
                                duration = float(self.globals['lifx'][lifxDevId]['durationOff'])
                                power = 0
                            else:
                                duration = 0
                                power = 0
                            timerDuration = duration
                            duration = int(duration * 1000)
                            try:    
                                self.globals['lifx'][lifxDevId]['lifxLanLightObject'].set_power(power, duration)
                            except:
                                self.communicationLost(lifxDev)
                                continue

                            self.globals['deviceTimers'][lifxDevId]['STATUS'] = threading.Timer(1.0, self.handleTimerRepeatingQueuedStatusCommand, [lifxDev, timerDuration])
                            self.globals['deviceTimers'][lifxDevId]['STATUS'].start()
                        
                        self.globals['lifx'][lifxDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if (lifxCommand == 'INFRARED_ON') or (lifxCommand == 'INFRARED_OFF') or (lifxCommand == 'INFRARED_SET'):
                        lifxDevId = lifxCommandParameters[0]

                        if self.globals['lifx'][lifxDevId]["started"] == True:

                            self.sendReceiveDebugLogger.debug(u"Processing %s for '%s' " % (lifxCommand, indigo.devices[lifxDevId].name))

                            lifxDev = indigo.devices[lifxDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            if lifxCommand == 'INFRARED_OFF':
                                infraredBrightness = 0
                            elif lifxCommand == 'INFRARED_ON':
                                infraredBrightness = 65535
                            elif lifxCommand == 'INFRARED_SET':
                                infraredBrightness = lifxCommandParameters[1]
                                infraredBrightness = int((infraredBrightness * 65535.0) / 100.0)
                                if infraredBrightness > 65535:
                                    infraredBrightness = 65535  # Just in case ;)

                            try:
                                self.globals['lifx'][lifxDevId]['lifxLanLightObject'].set_infrared(infraredBrightness)
                                self.sendReceiveDebugLogger.debug(u"Processing %s for '%s'; Infrared Brightness = %s" % (lifxCommand, indigo.devices[lifxDevId].name, infraredBrightness))
                            except:
                                self.communicationLost(lifxDev)
                                continue

                            self.globals['deviceTimers'][lifxDevId]['STATUS'] = threading.Timer(1.0, self.handleTimerRepeatingQueuedStatusCommand, [lifxDev, 2])
                            self.globals['deviceTimers'][lifxDevId]['STATUS'].start()
                        
                        self.globals['lifx'][lifxDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if lifxCommand == 'DISCOVERY_DELAYED':
                        if 'DISCOVERY' in self.globals['discoveryTimer']:
                            self.globals['discoveryTimer']['DISCOVERY'].cancel()

                        self.globals['discoveryTimer']['DISCOVERY'] = threading.Timer(30.0, self.handleTimerDiscoveryCommand,[])
                        self.globals['discoveryTimer']['DISCOVERY'].start()

                    if lifxCommand == 'DISCOVERY':
                        self.globals['lifxLanClient'] = LifxLAN(None)  # Discover LIFX Devices
                        self.globals['lifxDevices'] = self.globals['lifxLanClient'].get_lights()
                        for lifxDevice in self.globals['lifxDevices']:
                            lifxDeviceMacAddr = lifxDevice.mac_addr
                            lifxDeviceIpAddress = lifxDevice.ip_addr
                            lifxDeviceIpPort = lifxDevice.port
                            self.sendReceiveMonitorLogger.debug(u"LIFX Device discovered at %s [%s] using Port %s" % (lifxDeviceIpAddress, lifxDeviceMacAddr, lifxDeviceIpPort))

                            if ((len(self.globals['debug']['debugFilteredIpAddresses']) == 0) 
                                or ((len(self.globals['debug']['debugFilteredIpAddresses']) > 0) 
                                    # and ('ipAddress' in self.globals['lifx'][lifxDevice.id]) 
                                    and (lifxDeviceIpAddress in self.globals['debug']['debugFilteredIpAddresses']))):

                                lifxDeviceMatchedtoIndigoDevice = False
                                for devId in self.globals['lifx']:
                                    if lifxDevice.mac_addr == self.globals['lifx'][devId]['mac_addr']:
                                        lifxDeviceMatchedtoIndigoDevice = True
                                        break
                                if not lifxDeviceMatchedtoIndigoDevice:
                                    lifxDeviceLabel = str(lifxDevice.get_label()).rstrip()
                                    dev = indigo.device.create(protocol=indigo.kProtocol.Plugin,
                                        address=lifxDeviceMacAddr,
                                        name=lifxDeviceLabel, 
                                        description='LIFX Device', 
                                        pluginId="com.autologplugin.indigoplugin.lifxcontroller",
                                        deviceTypeId="lifxDevice",
                                        props={"onBrightensToLast": True, 
                                               "SupportsColor": True,
                                               "SupportsRGB": True,
                                               "SupportsWhite": True,
                                               "SupportsTwoWhiteLevels": False,
                                               "SupportsWhiteTemperature": True},
                                        folder=self.globals['folders']['DevicesId'])

                                    dev.setErrorStateOnServer(u"no ack")  # Default to 'no ack' status

                                    self.globals['lifx'][dev.id] = {}
                                    self.globals['lifx'][dev.id]['started']             = False
                                    self.globals['lifx'][dev.id]['initialisedFromlamp'] = False
                                    self.globals['lifx'][dev.id]['mac_addr']            = dev.address         # eg. 'd0:73:d5:0a:bc:de'
                                    self.globals['lifx'][dev.id]['ipAddress']           = lifxDeviceIpAddress
                                    devId = dev.id
                                    self.sendReceiveMonitorLogger.info(u"New LIFX Device '%s' discovered at %s [%s] using Port %s" % (lifxDeviceLabel, lifxDeviceIpAddress, lifxDeviceMacAddr, lifxDeviceIpPort))
                                else:
                                    dev = indigo.devices[devId]
                                    if not dev.states['connected']:
                                        self.sendReceiveMonitorLogger.info(u"LIFX Device '%s' re-connected at %s [%s] using Port %s" % (dev.name, lifxDeviceIpAddress, lifxDeviceMacAddr, lifxDeviceIpPort))
                                        dev.updateStateImageOnServer(indigo.kStateImageSel.Auto)
                                        self.globals['lifx'][dev.id]['started'] = True
                                        self.sendReceiveMonitorLogger.info(u"LIFX Device '%s' started." % (dev.name))

                                        self.globals['queues']['messageToSend'].put([QUEUE_PRIORITY_STATUS_MEDIUM, 'STATUS', [dev.id]])
                                        self.globals['queues']['messageToSend'].put([QUEUE_PRIORITY_LOW, 'GETVERSION', [dev.id]])
                                        self.globals['queues']['messageToSend'].put([QUEUE_PRIORITY_LOW, 'GETHOSTFIRMWARE', [dev.id]])
                                        self.globals['queues']['messageToSend'].put([QUEUE_PRIORITY_LOW, 'GETWIFIFIRMWARE', [dev.id]])
                                        self.globals['queues']['messageToSend'].put([QUEUE_PRIORITY_LOW, 'GETWIFIINFO', [dev.id]])

                                self.globals['lifx'][devId]['lifxLanLightObject']  = Light(lifxDeviceMacAddr, lifxDeviceIpAddress)
                                self.globals['lifx'][devId]['port']  = lifxDeviceIpPort

                        # Now check if further discovery required
                        discoveryRequired = False
                        for devId in self.globals['lifx']:
                            if (len(self.globals['debug']['debugFilteredIpAddresses']) > 0) and ('ipAddress' in self.globals['lifx'][devId]) and (self.globals['lifx'][devId]['ipAddress'] in self.globals['debug']['debugFilteredIpAddresses']):
                                if indigo.devices[devId].errorState == 'no ack':
                                    discoveryRequired = True
                                    break
                        if self.globals['discoveryCount'] < START_UP_REQUIRED_DISCOVERY_COUNT: 
                            self.globals['discoveryCount'] += 1
                            discoveryRequired = True
                        if discoveryRequired:
                            self.globals['queues']['messageToSend'].put([QUEUE_PRIORITY_LOW, 'DISCOVERY_DELAYED', []])

                        continue

                    if (lifxCommand == 'BRIGHTNESS'):
                        lifxDevId = lifxCommandParameters[0]

                        if self.globals['lifx'][lifxDevId]["started"] == True:
                            newBrightness = lifxCommandParameters[1]
                            newBrightness = int((newBrightness * 65535.0) / 100.0)

                            lifxDev = indigo.devices[lifxDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            ioStatus, power, hsbk = self.getColor(lifxDev, self.globals['lifx'][lifxDevId]['lifxLanLightObject'])

                            self.sendReceiveDebugLogger.debug(u"LIFX COMMAND [BRIGHTNESS] IOSTATUS for %s =  %s, HSBK = %s" % (indigo.devices[lifxDevId].name, ioStatus, hsbk))
                            if ioStatus:
                                hue = hsbk[0]
                                saturation = hsbk[1]
                                brightness = hsbk[2]
                                kelvin = hsbk[3]

                                self.sendReceiveDebugLogger.debug(u'LIFX COMMAND [BRIGHTNESS]; GET-COLOR for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s' % (indigo.devices[lifxDevId].name,  hue, saturation, brightness, kelvin))   
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
                                        self.globals['lifx'][lifxDevId]['lifxLanLightObject'].set_color(hsbkWithBrightnessZero, 0)
                                    except:
                                        self.communicationLost(lifxDev)
                                        continue
                                    # Need to turn on LIFX device as currently off
                                    power = 65535
                                    try:
                                        self.globals['lifx'][lifxDevId]['lifxLanLightObject'].set_power(power, 0)
                                    except:
                                        self.communicationLost(lifxDev)
                                        continue

                                hsbk = [hue, saturation, brightness, kelvin]
                                if lifxCommand == 'BRIGHTNESS':
                                    duration = int(self.globals['lifx'][lifxDevId]['durationDimBrighten'] * 1000)
                                else:
                                    duration = 0

                                self.sendReceiveDebugLogger.debug(u'LIFX COMMAND [BRIGHTNESS]; SET-COLOR for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s' % (indigo.devices[lifxDevId].name,  hue, saturation, brightness, kelvin))   

                                try:
                                    self.globals['lifx'][lifxDevId]['lifxLanLightObject'].set_color(hsbk, duration)
                                except:
                                    self.communicationLost(lifxDev)
                                    continue

                                if lifxCommand == 'BRIGHTNESS':
                                    timerDuration = int(self.globals['lifx'][lifxDevId]['durationDimBrighten'])
                                    self.globals['deviceTimers'][lifxDevId]['STATUS'] = threading.Timer(1.0, self.handleTimerRepeatingQueuedStatusCommand, [lifxDev, timerDuration])

                                    self.globals['deviceTimers'][lifxDevId]['STATUS'].start()

                        self.globals['lifx'][lifxDevId]['previousLifxComand'] = lifxCommand
                        continue


                    if lifxCommand == 'DIM' or lifxCommand == 'BRIGHTEN':
                        lifxDevId = lifxCommandParameters[0]

                        if self.globals['lifx'][lifxDevId]["started"] == True:
                            newBrightness = lifxCommandParameters[1]
                            newBrightness = int((newBrightness * 65535.0) / 100.0)

                            lifxDev = indigo.devices[lifxDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            hue        = self.globals['lifx'][lifxDevId]['hsbkHue']         # Value between 0 and 65535
                            saturation = self.globals['lifx'][lifxDevId]['hsbkSaturation']  # Value between 0 and 65535 (e.g. 20% = 13107)
                            kelvin     = self.globals['lifx'][lifxDevId]['hsbkKelvin']      # Value between 2500 and 9000
                            powerLevel = self.globals['lifx'][lifxDevId]['powerLevel']      # Value between 0 and 65535 

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

                            # self.sendReceiveDebugLogger.debug(u'LIFX COMMAND [BRIGHTNESS]; SET-COLOR for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s' % (indigo.devices[lifxDevId].name,  hue, saturation, brightness, kelvin))   

                            try:
                                self.globals['lifx'][lifxDevId]['lifxLanLightObject'].set_color(hsbk, 0, True)
                            except:
                                self.communicationLost(lifxDev)
                                continue

                        self.globals['lifx'][lifxDevId]['previousLifxComand'] = lifxCommand
                        continue


                    if lifxCommand == 'WHITE':
                        lifxDevId, targetWhiteLevel, targetWhiteTemperature = lifxCommandParameters

                        if self.globals['lifx'][lifxDevId]["started"] == True:
                            lifxDev = indigo.devices[lifxDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            ioStatus, power, hsbk = self.getColor(lifxDev, self.globals['lifx'][lifxDevId]['lifxLanLightObject'])

                            self.sendReceiveDebugLogger.debug(u"LIFX COMMAND [WHITE] IOSTATUS for %s =  %s, HSBK = %s" % (indigo.devices[lifxDevId].name, ioStatus, hsbk))
                            if ioStatus:
                                hue = hsbk[0]
                                saturation = hsbk[1]
                                brightness = hsbk[2]
                                kelvin = hsbk[3]

                                self.sendReceiveDebugLogger.debug(u'LIFX COMMAND [WHITE]; GET-COLOR for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s' % (indigo.devices[lifxDevId].name,  hue, saturation, brightness, kelvin))   

                                if power == 0 and self.globals['lifx'][lifxDevId]['turnOnIfOff']:
                                    # Need to reset existing brightness to 0 before turning on
                                    try:
                                        hsbkWithBrightnessZero = [hue, saturation, 0, kelvin]
                                        self.globals['lifx'][lifxDevId]['lifxLanLightObject'].set_color(hsbkWithBrightnessZero, 0)
                                    except:
                                        self.communicationLost(lifxDev)
                                        continue
                                    # Need to turn on LIFX device as currently off
                                    power = 65535
                                    try:
                                        self.globals['lifx'][lifxDevId]['lifxLanLightObject'].set_power(power, 0)
                                    except:
                                        self.communicationLost(lifxDev)
                                        continue
                                        
                                saturation = 0
                                brightness = int((targetWhiteLevel * 65535.0) / 100.0)
                                kelvin = int(targetWhiteTemperature)
                                hsbk = [hue, saturation, brightness, kelvin]
                                duration = int(self.globals['lifx'][lifxDevId]['durationColorWhite'] * 1000)

                                self.sendReceiveDebugLogger.debug(u'LIFX COMMAND [WHITE]; SET-COLOR for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s' % (indigo.devices[lifxDevId].name,  hue, saturation, brightness, kelvin))   

                                try:
                                    self.globals['lifx'][lifxDevId]['lifxLanLightObject'].set_color(hsbk, duration)
                                except:
                                    self.communicationLost(lifxDev)
                                    continue

                                timerDuration = int(self.globals['lifx'][lifxDevId]['durationColorWhite'])
                                self.globals['deviceTimers'][lifxDevId]['STATUS'] = threading.Timer(1.0, self.handleTimerRepeatingQueuedStatusCommand, [lifxDev, timerDuration])

                                self.globals['deviceTimers'][lifxDevId]['STATUS'].start()

                        self.globals['lifx'][lifxDevId]['previousLifxComand'] = lifxCommand
                        continue


                    if lifxCommand == 'COLOR':
                        lifxDevId, targetHue, targetSaturation, targetBrightness = lifxCommandParameters

                        if self.globals['lifx'][lifxDevId]["started"] == True:
                            lifxDev = indigo.devices[lifxDevId]
 
                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            ioStatus, power, hsbk = self.getColor(lifxDev, self.globals['lifx'][lifxDevId]['lifxLanLightObject'])
                            self.sendReceiveDebugLogger.debug(u"LIFX COMMAND [COLOR] IOSTATUS for %s =  %s, HSBK = %s" % (indigo.devices[lifxDevId].name, ioStatus, hsbk))
                            if ioStatus:
                                hue = hsbk[0]
                                saturation = hsbk[1]
                                brightness = hsbk[2]
                                kelvin = hsbk[3]

                                self.sendReceiveDebugLogger.debug(u'LIFX COMMAND [COLOR]; GET-COLOR for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s' % (indigo.devices[lifxDevId].name,  hue, saturation, brightness, kelvin))   

                                if power == 0 and self.globals['lifx'][dev.id]['turnOnIfOff']:
                                    # Need to reset existing brightness to 0 before turning on
                                    try:
                                        hsbkWithBrightnessZero = [hue, saturation, 0, kelvin]
                                        self.globals['lifx'][lifxDevId]['lifxLanLightObject'].set_color(hsbkWithBrightnessZero, 0)
                                    except:
                                        self.communicationLost(lifxDev)
                                        continue
                                    # Need to turn on LIFX device as currently off
                                    power = 65535
                                    try:
                                        self.globals['lifx'][lifxDevId]['lifxLanLightObject'].set_power(power, 0)
                                    except:
                                        self.communicationLost(lifxDev)
                                        continue

                                hue = targetHue
                                saturation = targetSaturation
                                brightness = targetBrightness
                                hsbk = [hue, saturation, brightness, kelvin]
                                duration = int(self.globals['lifx'][lifxDevId]['durationColorWhite'] * 1000)

                                self.sendReceiveDebugLogger.debug(u'LIFX COMMAND [COLOR]; SET-COLOR for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s, Duration=%s' % (indigo.devices[lifxDevId].name,  hue, saturation, brightness, kelvin, duration))   

                                try:
                                    self.globals['lifx'][lifxDevId]['lifxLanLightObject'].set_color(hsbk, duration)
                                except:
                                    self.communicationLost(lifxDev)
                                    continue

                                timerDuration = int(self.globals['lifx'][lifxDevId]['durationColorWhite'])
                                self.globals['deviceTimers'][lifxDevId]['STATUS'] = threading.Timer(1.0, self.handleTimerRepeatingQueuedStatusCommand, [lifxDev, timerDuration])

                                self.globals['deviceTimers'][lifxDevId]['STATUS'].start()

                        self.globals['lifx'][lifxDevId]['previousLifxComand'] = lifxCommand
                        continue


                    if lifxCommand == 'STANDARD':
                        lifxDevId, turnOnIfOff, targetMode, targetHue, targetSaturation, targetBrightness, targetKelvin, targetDuration = lifxCommandParameters

                        if self.globals['lifx'][lifxDevId]["started"] == True:
                            lifxDev = indigo.devices[lifxDevId]

                            self.sendReceiveDebugLogger.debug(u'LIFX COMMAND [STANDARD]; Target for %s: TOIF=%s, Mode=%s, Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s, Duration=%s' % (indigo.devices[lifxDevId].name,  turnOnIfOff, targetMode, targetHue, targetSaturation, targetBrightness, targetKelvin, targetDuration))   
 
                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            ioStatus, power, hsbk = self.getColor(lifxDev, self.globals['lifx'][lifxDevId]['lifxLanLightObject'])
                            self.sendReceiveDebugLogger.debug(u"LIFX COMMAND [COLOR] IOSTATUS for %s =  %s, HSBK = %s" % (indigo.devices[lifxDevId].name, ioStatus, hsbk))
                            if ioStatus:
                                hue = hsbk[0]
                                saturation = hsbk[1]
                                brightness = hsbk[2]
                                kelvin = hsbk[3]

                                self.sendReceiveDebugLogger.debug(u'LIFX COMMAND [COLOR]; GET-COLOR for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s' % (indigo.devices[lifxDevId].name,  hue, saturation, brightness, kelvin))   

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
                                    duration = int(self.globals['lifx'][lifxDevId]['durationColorWhite'] * 1000)

                                self.sendReceiveDebugLogger.debug(u'LIFX COMMAND [STANDARD][%s]; SET-COLOR for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s, duration=%s' % (targetMode, indigo.devices[lifxDevId].name,  hue, saturation, brightness, kelvin, duration))   


                                if power == 0 and turnOnIfOff:
                                    try:
                                        self.globals['lifx'][lifxDevId]['lifxLanLightObject'].set_color(hsbk, 0)
                                    except:
                                        self.communicationLost(lifxDev)
                                        continue
                                    power = 65535
                                    try:
                                        self.globals['lifx'][lifxDevId]['lifxLanLightObject'].set_power(power, duration)
                                    except:
                                        self.communicationLost(lifxDev)
                                        continue
                                else:
                                    if power == 0:
                                        duration = 0  # As power is off. might as well do apply command straight away
                                    try:
                                        self.globals['lifx'][lifxDevId]['lifxLanLightObject'].set_color(hsbk, duration)
                                    except:
                                        self.communicationLost(lifxDev)
                                        continue

                                timerDuration = int(duration/1000)  # Convert back from milliseconds
                                self.globals['deviceTimers'][lifxDevId]['STATUS'] = threading.Timer(1.0, self.handleTimerRepeatingQueuedStatusCommand, [lifxDev, timerDuration])

                                self.globals['deviceTimers'][lifxDevId]['STATUS'].start()

                        self.globals['lifx'][lifxDevId]['previousLifxComand'] = lifxCommand
                        continue


                    if lifxCommand == 'WAVEFORM':
                        lifxDevId, targetMode, targetHue, targetSaturation, targetBrightness, targetKelvin, targetTransient, targetPeriod, targetCycles, targetDuty_cycle, targetWaveform = lifxCommandParameters

                        if self.globals['lifx'][lifxDevId]["started"] == True:
                            lifxDev = indigo.devices[lifxDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)
                            self.clearWaveformOffTimer(lifxDev)

                            ioStatus, power, hsbk = self.getColor(lifxDev, self.globals['lifx'][lifxDevId]['lifxLanLightObject'])
                            self.sendReceiveDebugLogger.debug(u"LIFX COMMAND [COLOR] IOSTATUS for %s =  %s, HSBK = %s" % (indigo.devices[lifxDevId].name, ioStatus, hsbk))
                            if ioStatus:
                                hue = hsbk[0]
                                saturation = hsbk[1]
                                brightness = hsbk[2]
                                kelvin = hsbk[3]

                                self.sendReceiveDebugLogger.debug(u'LIFX COMMAND [COLOR]; GET-COLOR for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s' % (indigo.devices[lifxDevId].name,  hue, saturation, brightness, kelvin))   

                                lifxDeviceAlreadyOn = True
                                if power == 0:
                                    lifxDeviceAlreadyOn = False
                                    duration = 0
                                    power = 65535
                                    duration = int(duration * 1000)    
                                    try:
                                        self.globals['lifx'][lifxDevId]['lifxLanLightObject'].set_power(power, duration)
                                    except:
                                        self.communicationLost(lifxDev)
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

                                self.sendReceiveDebugLogger.debug(u'LIFX COMMAND [WAVEFORM]; SET-WAVEFORM for %s: Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s' % (indigo.devices[lifxDevId].name,  hue, saturation, brightness, kelvin))   
                                self.sendReceiveDebugLogger.debug(u'LIFX COMMAND [WAVEFORM]; SET-WAVEFORM for %s: Transient=%s, Period=%s, Cycles=%s, Duty_cycle=%s, Waveform=%s' % (indigo.devices[lifxDevId].name,  transient, period, cycles, duty_cycle, waveform))   

                                try:
                                    self.globals['lifx'][lifxDevId]['lifxLanLightObject'].set_waveform(transient, hsbk, period, cycles, duty_cycle, waveform)
                                except:
                                    self.communicationLost(lifxDev)
                                    continue

                                if not lifxDeviceAlreadyOn:
                                    timerSetFor = float((float(period) / 1000.0) * cycles)
                                    self.globals['deviceTimers'][lifxDevId]['WAVEFORM_OFF'] = threading.Timer(timerSetFor, self.handleTimerWaveformOffCommand, [lifxDev])
                                    self.globals['deviceTimers'][lifxDevId]['WAVEFORM_OFF'].start()

                        self.globals['lifx'][lifxDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if lifxCommand == 'SETLABEL':
                        lifxDevId = lifxCommandParameters[0]
                        if self.globals['lifx'][lifxDevId]["started"] == True:

                            self.sendReceiveDebugLogger.debug(u"Processing %s for '%s' " % (lifxCommand, indigo.devices[lifxDevId].name))

                            lifxDev = indigo.devices[lifxDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            try:
                                self.globals['lifx'][lifxDevId]['lifxLanLightObject'].set_label(lifxDev.name)
                            except:
                                self.communicationLost(lifxDev)

                        self.globals['lifx'][lifxDevId]['previousLifxComand'] = lifxCommand
                        continue


                    if lifxCommand == 'GETVERSION':
                        lifxDevId = lifxCommandParameters[0]
                        if self.globals['lifx'][lifxDevId]["started"] == True:

                            self.sendReceiveDebugLogger.debug(u"Processing %s for '%s' " % (lifxCommand, indigo.devices[lifxDevId].name))

                            lifxDev = indigo.devices[lifxDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            try:
                                product = self.globals['lifx'][lifxDevId]['lifxLanLightObject'].get_product()
                            except:
                                self.communicationLost(lifxDev)
                                continue

                            self.sendReceiveDebugLogger.debug(u"PRODUCT for '%s' = '%s'" % (indigo.devices[lifxDevId].name, product))

                            productFound = False
                            try:
                                model = str('%s' % (LIFX_PRODUCTS[product][LIFX_PRODUCT_NAME]))  # Defined in constants.py
                                productFound = True
                            except KeyError:
                                model = str('LIFX Product - %s' % (product))

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

                        self.globals['lifx'][lifxDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if lifxCommand == 'GETHOSTFIRMWARE':
                        lifxDevId = lifxCommandParameters[0]
                        if self.globals['lifx'][lifxDevId]["started"] == True:

                            self.sendReceiveDebugLogger.debug(u"Processing %s for '%s' " % (lifxCommand, indigo.devices[lifxDevId].name))

                            lifxDev = indigo.devices[lifxDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            try:
                                firmware_version = str(self.globals['lifx'][lifxDevId]['lifxLanLightObject'].get_host_firmware_version())
                            except:
                                self.communicationLost(lifxDev)
                                continue

                            self.sendReceiveDebugLogger.debug(u"HOST FIRMWARE VERSION for '%s': '%s'" % (indigo.devices[lifxDevId].name, firmware_version))

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

                        self.globals['lifx'][lifxDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if lifxCommand == 'GETPORT':
                        lifxDevId = lifxCommandParameters[0]
                        if self.globals['lifx'][lifxDevId]["started"] == True:

                            self.sendReceiveDebugLogger.debug(u"Processing %s for '%s' " % (lifxCommand, indigo.devices[lifxDevId].name))

                            lifxDev = indigo.devices[lifxDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            try:
                                port = str(self.globals['lifx'][lifxDevId]['lifxLanLightObject'].get_port())
                            except:
                                self.communicationLost(lifxDev)
                                continue

                            self.sendReceiveDebugLogger.info(u"Port for '%s': '%s'" % (indigo.devices[lifxDevId].name, port))

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

                        self.globals['lifx'][lifxDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if lifxCommand == 'GETWIFIFIRMWARE':
                        lifxDevId = lifxCommandParameters[0]
                        if self.globals['lifx'][lifxDevId]["started"] == True:

                            self.sendReceiveDebugLogger.debug(u"Processing %s for '%s' " % (lifxCommand, indigo.devices[lifxDevId].name))

                            lifxDev = indigo.devices[lifxDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            try:
                                wifi_firmware_version = str(self.globals['lifx'][lifxDevId]['lifxLanLightObject'].get_wifi_firmware_version())
                            except:
                                self.communicationLost(lifxDev)
                                continue

                            self.sendReceiveDebugLogger.debug(u"WI-FI FIRMWARE VERSION for '%s': '%s'" % (indigo.devices[lifxDevId].name, wifi_firmware_version))

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

                        self.globals['lifx'][lifxDevId]['previousLifxComand'] = lifxCommand
                        continue

                    if lifxCommand == 'GETWIFIINFO':
                        lifxDevId = lifxCommandParameters[0]
                        if self.globals['lifx'][lifxDevId]["started"] == True and indigo.devices[lifxDevId].states['connected']:

                            self.sendReceiveDebugLogger.debug(u"Processing %s for '%s' " % (lifxCommand, indigo.devices[lifxDevId].name))

                            lifxDev = indigo.devices[lifxDevId]

                            # Clear any outstanding timers
                            self.clearStatusTimer(lifxDev)

                            try:
                                signal, tx, rx = self.globals['lifx'][lifxDevId]['lifxLanLightObject'].get_wifi_info_tuple()
                            except:
                                self.communicationLost(lifxDev)
                                continue

                            self.sendReceiveDebugLogger.debug(u"WI-FI INFO [1] for '%s': Signal=%s, Tx=%s, Rx=%s" % (indigo.devices[lifxDevId].name, signal, tx, rx))
                            if signal != None:
                                signal = str('{:.16f}'.format(signal))[0:12]
                            locale.setlocale(locale.LC_ALL, 'en_US')
                            if tx != None:
                                tx = locale.format("%d", tx, grouping=True)
                            if rx != None:
                                rx = locale.format("%d", rx, grouping=True)

                            self.sendReceiveDebugLogger.debug(u"WI-FI INFO [2] for '%s': Signal=%s, Tx=%s, Rx=%s" % (indigo.devices[lifxDevId].name, signal, tx, rx))

                            keyValueList = [
                                {'key': 'wifiSignal', 'value': signal},
                                {'key': 'wifiTx', 'value': tx},
                                {'key': 'wifiRx', 'value': rx}
                            ]
                            lifxDev.updateStatesOnServer(keyValueList)

                        self.globals['lifx'][lifxDevId]['previousLifxComand'] = lifxCommand
                        continue

                    continue

                    # TO BE CONTINUED !

                    if lifxCommand == 'GETHOSTINFO':
                        self.sendReceiveDebugLogger.debug(u"Processing %s" % (lifxCommand))

                        payload = ''
                        dev = sendMessage[1]
                        ipAddress =  self.globals['lifx'][dev.id]['ipAddress']
                        self.outputMessageToLifxDevice(ipAddress, DEV_GET_HOST_INFO, dev, payload)

                        continue

                    if lifxCommand == 'GETLOCATION':
                        self.sendReceiveDebugLogger.debug(u"Processing %s" % (lifxCommand))

                        payload = ''
                        dev = sendMessage[1]
                        ipAddress =  self.globals['lifx'][dev.id]['ipAddress']
                        self.outputMessageToLifxDevice(ipAddress, DEV_GET_LOCATION, dev, payload)

                        continue

                    if lifxCommand == 'GETGROUP':
                        self.sendReceiveDebugLogger.debug(u"Processing %s" % (lifxCommand))

                        payload = ''
                        dev = sendMessage[1]
                        ipAddress =  self.globals['lifx'][dev.id]['ipAddress']
                        self.outputMessageToLifxDevice(ipAddress, DEV_GET_GROUP, dev, payload)

                        continue

                    if lifxCommand == 'GETINFO':
                        self.sendReceiveDebugLogger.debug(u"Processing %s" % (lifxCommand))

                        payload = ''
                        dev = sendMessage[1]
                        ipAddress =  self.globals['lifx'][dev.id]['ipAddress']
                        self.outputMessageToLifxDevice(ipAddress, DEV_GET_INFO, dev, payload)

                        continue

                except Queue.Empty:
                    pass
                # except StandardError, e:
                #     self.sendReceiveDebugLogger.error(u"StandardError detected communicating with LIFX lamp. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))   
                except:
                    self.sendReceiveDebugLogger.error(u"Exception detected communicating with LIFX lamp:") 
                    errorLines = traceback.format_exc().splitlines()
                    for errorLine in errorLines:
                        self.sendReceiveDebugLogger.error(u"%s" % errorLine)   

        except StandardError, e:
            self.sendReceiveDebugLogger.error(u"StandardError detected in LIFX Send Receive Message Thread. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))   

        self.sendReceiveDebugLogger.debug(u"LIFX Send Receive Message Thread ended.")   

    def clearStatusTimer(self, dev):
        self.methodTracer.threaddebug(u"CLASS: ThreadSendReceiveMessages")

        if dev.id in self.globals['deviceTimers'] and 'STATUS' in self.globals['deviceTimers'][dev.id]:
            self.globals['deviceTimers'][dev.id]['STATUS'].cancel()

    def handleTimerRepeatingQueuedStatusCommand(self, dev, seconds):
        self.methodTracer.threaddebug(u"CLASS: ThreadSendReceiveMessages")

        try: 
            self.sendReceiveDebugLogger.debug(u'Timer for %s [%s] invoked for repeating queued message STATUS - %s seconds left' % (dev.name, dev.address, seconds))

            try:
                del self.globals['deviceTimers'][dev.id]['STATUS']
            except:
                pass

            self.globals['queues']['messageToSend'].put([QUEUE_PRIORITY_STATUS_HIGH, 'STATUS', [dev.id]])

            if seconds > 0:
                seconds -= 1
                self.globals['deviceTimers'][dev.id]['STATUS'] = threading.Timer(1.0, self.handleTimerRepeatingQueuedStatusCommand, [dev, seconds])
                self.globals['deviceTimers'][dev.id]['STATUS'].start()

        except StandardError, e:
            self.sendReceiveDebugLogger.error(u"handleTimerRepeatingQueuedStatusCommand error detected. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))   

    def handleTimerDiscoveryCommand(self):
        self.methodTracer.threaddebug(u"CLASS: ThreadSendReceiveMessages")

        try:
            self.sendReceiveDebugLogger.debug(u'Timer for Discovery invoked to discover LIFX devices)')

            try:
                del self.globals['discoveryTimer']['DISCOVERY']
            except:
                pass

            self.globals['queues']['messageToSend'].put([QUEUE_PRIORITY_LOW, 'DISCOVERY', []])


        except StandardError, e:
            self.sendReceiveDebugLogger.error(u"handleTimerDiscoveryCommand error detected. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))   


    def clearWaveformOffTimer(self, dev):
        self.methodTracer.threaddebug(u"CLASS: ThreadSendReceiveMessages")

        if 'WAVEFORM_OFF' in self.globals['deviceTimers'][dev.id]:
            self.globals['deviceTimers'][dev.id]['WAVEFORM_OFF'].cancel()

    def handleTimerWaveformOffCommand(self, dev):
        self.methodTracer.threaddebug(u"CLASS: ThreadSendReceiveMessages")

        try: 
            self.sendReceiveDebugLogger.debug(u'Timer for %s [%s] invoked to turn off LIFX device (Used by Waveform)' % (dev.name, dev.address))

            try:
                del self.globals['deviceTimers'][dev.id]['WAVEFORM_OFF']
            except:
                pass

            self.globals['queues']['messageToSend'].put([QUEUE_PRIORITY_STATUS_HIGH, 'WAVEFORM_OFF', [dev.id]])

        except StandardError, e:
            self.sendReceiveDebugLogger.error(u"handleTimerRepeatingQueuedStatusCommand error detected. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))   

    def communicationLost(self, argLifxDev):
        if argLifxDev.states['connected'] == True:
            argLifxDev.updateStateOnServer(key='connected', value=False)
            argLifxDev.setErrorStateOnServer(u"no ack")
            self.sendReceiveMonitorLogger.debug(u"Communication lost with \"%s\" - status set to 'No Acknowledgment' (no ack)" % argLifxDev.name)  

    def getColor(self, argLifxDev, argLifxLanLightObject):
        try:
            hsbk = argLifxLanLightObject.get_color()
            power = argLifxLanLightObject.power_level
            status = True
        except IOError, e:
            self.sendReceiveDebugLogger.debug(u"GET_COLOR [IOERROR ERROR] for \"%s\" = %e" % (argLifxDev.name, e))  
            status = False
            hsbk = (0, 0, 0, 3500)
            power = 0
            self.communicationLost(argLifxDev)
        except StandardError, e:
            self.sendReceiveDebugLogger.debug(u"GET_COLOR [STANDARD ERROR] for \"%s\" = %s" % (argLifxDev.name, e)) 
            status = False
            hsbk = (0, 0, 0, 3500)
            power = 0
            self.communicationLost(argLifxDev)

        except:
            self.sendReceiveDebugLogger.debug(u"GET_COLOR [TOTAL ERROR] for \"%s\" = %s" % (argLifxDev.name, sys.exc_info()[0]))
            status = False
            hsbk = (0, 0, 0, 3500)
            power = 0
            self.communicationLost(argLifxDev)

        return (status, power, hsbk)

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

            return (int(hue), int(saturation), int(brightness), int(kelvin))
        except StandardError, e:
            self.generalLogger.error(u"StandardError detected setting LIFX lamp HSBK values. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))
            return (int(0),int(0),int(0),int(0))   

    def updateStatusFromMsg(self, lifxCommand, lifxDevId, power, hsbk):
        self.methodTracer.threaddebug(u"ThreadHandleMessages")

        try:
            lifxDev = indigo.devices[lifxDevId]

            hue, saturation, brightness, kelvin = hsbk
            self.sendReceiveDebugLogger.debug(u'HANDLE MESSAGE for %s: Power=%s, Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s' % (indigo.devices[lifxDevId].name, power, hue, saturation, brightness, kelvin))   


            if power > 0:
                self.globals['lifx'][lifxDevId]['onState'] = True
                self.globals['lifx'][lifxDevId]['onOffState'] = 'on'
            else:
                self.globals['lifx'][lifxDevId]['onState'] = False                                    
                self.globals['lifx'][lifxDevId]['onOffState'] = 'off'
            self.globals['lifx'][lifxDevId]['powerLevel'] = power

            # Color [0-7]: HSBK
            # Reserved [8-9]: signed 16-bit integer
            # Power [10-11]: unsigned 16-bit integer
            # Label [12-43]: string, size=32 bytes
            # Reserved [44-51]: unsigned 64-bit integer
            self.globals['lifx'][lifxDevId]['hsbkHue'] = hue
            self.globals['lifx'][lifxDevId]['hsbkSaturation'] = saturation
            self.globals['lifx'][lifxDevId]['hsbkBrightness'] = brightness
            self.globals['lifx'][lifxDevId]['hsbkKelvin'] = kelvin
                    

            self.sendReceiveDebugLogger.debug(u'LAMP IP ADDRESS [%s] vs DEBUG FILTERED IP ADDRESS [%s]' % (self.globals['lifx'][lifxDevId]['ipAddress'], self.globals['debug']['debugFilteredIpAddresses']))

            self.sendReceiveDebugLogger.debug(u"  LIGHT_STATE = Power: %s" % (self.globals['lifx'][lifxDevId]['powerLevel']))
            self.sendReceiveDebugLogger.debug(u"  LIGHT_STATE = onState: %s" % (self.globals['lifx'][lifxDevId]['onState']))
            self.sendReceiveDebugLogger.debug(u"  LIGHT_STATE = onOffState: %s" % (self.globals['lifx'][lifxDevId]['onOffState']))

            # At this point we have an Indigo device id for the lamp and can confirm that the indigo device has been started

            self.globals['lifx'][lifxDevId]['lastResponseToPollCount'] = self.globals['polling']['count']  # Set the current poll count (for 'no ack' check)
            self.sendReceiveDebugLogger.debug(u'LAST RESPONSE TO POLL COUNT for %s = %s' % (lifxDev.name, self.globals['polling']['count']))


            self.globals['lifx'][lifxDevId]['initialisedFromlamp'] = True

            if self.globals['lifx'][lifxDevId]['onState'] == True:
                self.globals['lifx'][lifxDevId]['whenLastOnHsbkHue']        = self.globals['lifx'][lifxDevId]['hsbkHue']         # Value between 0 and 65535
                self.globals['lifx'][lifxDevId]['whenLastOnHsbkSaturation'] = self.globals['lifx'][lifxDevId]['hsbkSaturation']  # Value between 0 and 65535 (e.g. 20% = 13107)
                self.globals['lifx'][lifxDevId]['whenLastOnHsbkBrightness'] = self.globals['lifx'][lifxDevId]['hsbkBrightness']  # Value between 0 and 65535
                self.globals['lifx'][lifxDevId]['whenLastOnHsbkKelvin']     = self.globals['lifx'][lifxDevId]['hsbkKelvin']      # Value between 2500 and 9000
                self.globals['lifx'][lifxDevId]['whenLastOnPowerLevel']     = self.globals['lifx'][lifxDevId]['powerLevel']      # Value between 0 and 65535 

            try:
                self.globals['lifx'][lifxDevId]['indigoHue'] = float((self.globals['lifx'][lifxDevId]['hsbkHue'] * 360) /  65535)  # Bug Fix 2016-07-09
            except:
                self.globals['lifx'][lifxDevId]['indigoHue'] = float(0)
            try:
                self.globals['lifx'][lifxDevId]['indigoSaturation'] = float((self.globals['lifx'][lifxDevId]['hsbkSaturation'] * 100) /  65535)
            except:
                self.globals['lifx'][lifxDevId]['indigoSaturation'] = float(0)
            try:
                self.globals['lifx'][lifxDevId]['indigoBrightness'] = float((self.globals['lifx'][lifxDevId]['hsbkBrightness'] * 100) /  65535)
            except:
                self.globals['lifx'][lifxDevId]['indigoBrightness'] = float(0)
            try:
                self.globals['lifx'][lifxDevId]['indigoKelvin'] = float(self.globals['lifx'][lifxDevId]['hsbkKelvin'])
            except:
                self.globals['lifx'][lifxDevId]['indigoKelvin'] = float(3500)
            try:
                self.globals['lifx'][lifxDevId]['indigoPowerLevel'] = float((self.globals['lifx'][lifxDevId]['powerLevel'] * 100) /  65535)
            except:
                self.globals['lifx'][lifxDevId]['indigoPowerLevel'] = float(0)

            hsv_hue = float(self.globals['lifx'][lifxDevId]['hsbkHue']) / 65535.0
            hsv_value = float(self.globals['lifx'][lifxDevId]['hsbkBrightness']) / 65535.0
            hsv_saturation = float(self.globals['lifx'][lifxDevId]['hsbkSaturation']) / 65535.0
            red, green, blue = colorsys.hsv_to_rgb(hsv_hue, hsv_saturation, hsv_value)

            self.globals['lifx'][lifxDevId]['indigoRed']   = float(red * 100.0)
            self.globals['lifx'][lifxDevId]['indigoGreen'] = float(green * 100.0)
            self.globals['lifx'][lifxDevId]['indigoBlue']  = float(blue * 100.0)

            # Set brightness according to LIFX Lamp on/off state - if 'on' use the LIFX Lamp state else set to zero
            if self.globals['lifx'][lifxDevId]['onState']:
                if self.globals['lifx'][lifxDevId]['indigoSaturation'] > 0.0:  # check if white or colour (colour if saturation > 0.0)
                    # Colour
                    saturation = hsv_saturation * 100.0
                    brightness = hsv_value * 100.0
                    calculatedBrightnessLevel = self.calculateBrightnesssLevelFromSV(saturation, brightness)  # returns Float value
                    self.globals['lifx'][lifxDevId]['brightnessLevel'] = int(calculatedBrightnessLevel * (self.globals['lifx'][lifxDevId]['powerLevel'] / 65535.0))
                    #self.globals['lifx'][lifxDevId]['brightnessLevel'] = int(self.globals['lifx'][lifxDevId]['powerLevel'])  # returns Int value
                    # self.sendReceiveDebugLogger.info(u'BRIGHTNESS LEVEL [RECEIVE]: [%s] = %s' % (type(self.globals['lifx'][lifxDevId]['brightnessLevel']), self.globals['lifx'][lifxDevId]['brightnessLevel']))       
                else:
                    # White
                    self.globals['lifx'][lifxDevId]['brightnessLevel'] = int(self.globals['lifx'][lifxDevId]['indigoBrightness'] * (self.globals['lifx'][lifxDevId]['powerLevel'] / 65535.0))
                    self.globals['lifx'][lifxDevId]['indigoWhiteLevel'] = float(self.globals['lifx'][lifxDevId]['indigoBrightness'])
            else:       
                self.globals['lifx'][lifxDevId]['brightnessLevel'] = 0

            keyValueList = [
                {'key': 'ipAddress', 'value': self.globals['lifx'][lifxDevId]['ipAddress']},

                {'key': 'lifxOnState', 'value': self.globals['lifx'][lifxDevId]['onState']},
                {'key': 'lifxOnOffState', 'value': self.globals['lifx'][lifxDevId]['onOffState']},

                {'key': 'hsbkHue', 'value': self.globals['lifx'][lifxDevId]['hsbkHue']},
                {'key': 'hsbkSaturation', 'value': self.globals['lifx'][lifxDevId]['hsbkSaturation']},
                {'key': 'hsbkBrightness', 'value': self.globals['lifx'][lifxDevId]['hsbkBrightness']},
                {'key': 'hsbkKelvin', 'value': self.globals['lifx'][lifxDevId]['hsbkKelvin']},
                {'key': 'powerLevel', 'value': self.globals['lifx'][lifxDevId]['powerLevel']},

                {'key': 'groupLabel', 'value': self.globals['lifx'][lifxDevId]['groupLabel']},
                {'key': 'locationLabel', 'value': self.globals['lifx'][lifxDevId]['locationLabel']},

                {'key': 'whenLastOnHsbkHue', 'value': self.globals['lifx'][lifxDevId]['whenLastOnHsbkHue']},
                {'key': 'whenLastOnHsbkSaturation', 'value': self.globals['lifx'][lifxDevId]['whenLastOnHsbkSaturation']},
                {'key': 'whenLastOnHsbkBrightness', 'value': self.globals['lifx'][lifxDevId]['whenLastOnHsbkBrightness']},
                {'key': 'whenLastOnHsbkKelvin', 'value': self.globals['lifx'][lifxDevId]['whenLastOnHsbkKelvin']},
                {'key': 'whenLastOnPowerLevel', 'value': self.globals['lifx'][lifxDevId]['whenLastOnPowerLevel']},

                {'key': 'whiteTemperature', 'value': self.globals['lifx'][lifxDevId]['indigoKelvin']},
                {'key': 'whiteLevel', 'value': self.globals['lifx'][lifxDevId]['indigoWhiteLevel']},

                {'key': 'indigoHue', 'value': self.globals['lifx'][lifxDevId]['indigoHue']},
                {'key': 'indigoSaturation', 'value': self.globals['lifx'][lifxDevId]['indigoSaturation']},
                {'key': 'indigoBrightness', 'value': self.globals['lifx'][lifxDevId]['indigoBrightness']},
                {'key': 'indigoKelvin', 'value': self.globals['lifx'][lifxDevId]['indigoKelvin']},
                {'key': 'indigoPowerLevel', 'value': self.globals['lifx'][lifxDevId]['indigoPowerLevel']},

                {'key': 'brightnessLevel', 'value': int(self.globals['lifx'][lifxDevId]['brightnessLevel'])},

                {'key': 'duration', 'value': self.globals['lifx'][lifxDevId]['duration']},
                {'key': 'durationDimBrighten', 'value': self.globals['lifx'][lifxDevId]['durationDimBrighten']},
                {'key': 'durationOn', 'value': self.globals['lifx'][lifxDevId]['durationOn']},
                {'key': 'durationOff', 'value': self.globals['lifx'][lifxDevId]['durationOff']},
                {'key': 'durationColorWhite', 'value': self.globals['lifx'][lifxDevId]['durationColorWhite']},
                {'key': 'connected', 'value': True}

            ]

            props = lifxDev.pluginProps
            if ("SupportsRGB" in props) and props["SupportsRGB"]:
                keyValueList.append({'key': 'redLevel', 'value': self.globals['lifx'][lifxDevId]['indigoRed']})
                keyValueList.append({'key': 'greenLevel', 'value': self.globals['lifx'][lifxDevId]['indigoGreen']})
                keyValueList.append({'key': 'blueLevel', 'value': self.globals['lifx'][lifxDevId]['indigoBlue']})

            lifxDev.updateStatesOnServer(keyValueList)

            lifxDev.updateStateImageOnServer(indigo.kStateImageSel.Auto)

 
        except StandardError, e:
            self.sendReceiveDebugLogger.error(u"StandardError detected in 'handleLifxLampMessage'. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))   

