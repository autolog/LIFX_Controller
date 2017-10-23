#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# LIFX V5 Controller - Main © Autolog 2016-2017
#

import colorsys
from datetime import datetime
try:
    import indigo
except:
    pass
import logging
import Queue
import re
import sys
import threading
from time import localtime, strftime

from constants import *
from ghpu import GitHubPluginUpdater
from lifxlan.lifxlan import *
from lifxlanHandler import ThreadLifxlanHandler
from polling import ThreadPolling


# noinspection PyPep8Naming,PyUnresolvedReferences
class Plugin(indigo.PluginBase):

    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        # Initialise dictionary to store plugin Globals
        self.globals = dict()

        # Initialise Indigo plugin info
        self.globals['pluginInfo'] = {}
        self.globals['pluginInfo']['pluginId'] = pluginId
        self.globals['pluginInfo']['pluginDisplayName'] = pluginDisplayName
        self.globals['pluginInfo']['pluginVersion'] = pluginVersion

        # Initialise dictionary for debug in plugin Globals
        self.globals['debug'] = {}
        self.globals['debug']['monitorDebugEnabled'] = False  # if False it indicates no debugging is active else it indicates that at least one type of debug is active
        self.globals['debug']['debugFilteredIpAddresses'] = []  # Set to LIFX Lamp IP Address(es) to limit processing for debug purposes
        self.globals['debug']['debugFilteredIpAddressesUI'] = ''  # Set to LIFX Lamp IP Address(es) to limit processing for debug purposes (UI version)
        self.globals['debug']['debugGeneral'] = logging.INFO  # For general debugging of the main thread

        self.globals['debug']['monitorLifxlanHandler'] = logging.DEBUG  # For monitoring lifxlan handler
        self.globals['debug']['debugLifxlanHandler'] = logging.DEBUG  # For debugging  lifxlan handler

        self.globals['debug']['debugMethodTrace'] = logging.INFO  # For displaying method invocations i.e. trace method
        self.globals['debug']['debugPolling'] = logging.INFO  # For polling debugging

        self.globals['debug']['previousDebugGeneral'] = logging.INFO  # For general debugging of the main thread
        self.globals['debug']['previousMonitorLifxlanHandler'] = logging.INFO  # For monitoring messages sent to LIFX lamps 
        self.globals['debug']['previousDebugLifxlanHandler'] = logging.INFO  # For debugging messages sent to LIFX lamps
        self.globals['debug']['previousDebugMethodTrace'] = logging.INFO  # For displaying method invocations i.e. trace method
        self.globals['debug']['previousDebugPolling'] = logging.INFO  # For polling debugging

        # Setup Logging
        logformat = logging.Formatter('%(asctime)s.%(msecs)03d\t%(levelname)-12s\t%(name)s.%(funcName)-25s %(msg)s', datefmt='%Y-%m-%d %H:%M:%S')
        self.plugin_file_handler.setFormatter(logformat)
        self.plugin_file_handler.setLevel(logging.INFO)  # Master Logging Level for Plugin Log file
        self.indigo_log_handler.setLevel(logging.INFO)   # Logging level for Indigo Event Log
        self.generalLogger = logging.getLogger("Plugin.general")
        self.generalLogger.setLevel(self.globals['debug']['debugGeneral'])
        self.methodTracer = logging.getLogger("Plugin.method")  
        self.methodTracer.setLevel(self.globals['debug']['debugMethodTrace'])

        # Now logging is set-up, output Initialising Message
        self.generalLogger.info(u"Autolog 'LIFX V5 Controller' initializing . . .")

        # Initialise dictionary to store internal details about LIFX devices
        self.globals['lifx'] = {} 

        # Initialise dictionary to store folder Ids
        self.globals['folders'] = {}
        self.globals['folders']['DevicesId'] = 0  # Id of Devices folder to hold LIFX devices
        self.globals['folders']['VariablesId'] = 0   # Id of Variables folder to hold LIFX preset variables


        # Initialise dictionary to store per-lamp timers
        self.globals['deviceTimers'] = {}

        # Initialise dictionary to store message queues
        self.globals['queues'] = {}
        self.globals['queues']['lifxlanHandler'] = {}  # There will be one 'messageToSend' queue for each LIFX device - set-up in LIFX device start
        self.globals['queues']['initialised'] = {} # There will be one 'initialised' flag for each LIFX device - set-up in LIFX device start


        # Initialise dictionary to store threads
        self.globals['threads'] = {}
        self.globals['threads']['polling'] = {}  # There is only one 'polling' thread for all LIFX devices
        self.globals['threads']['lifxlanHandler'] = {}  # There is only one 'lifxlanHandler' thread for all LIFX devices

        self.globals['threads']['runConcurrentActive'] = False

        # Initialise dictionary for polling (single thread for all LIFX devices)
        self.globals['polling'] = {}
        self.globals['polling']['threadActive'] = False        
        self.globals['polling']['status'] = False
        self.globals['polling']['seconds'] = float(300.0)  # 5 minutes
        self.globals['polling']['forceThreadEnd'] = False
        self.globals['polling']['quiesced'] = False
        self.globals['polling']['missedPollLimit'] = int(2)  # Default to 2 missed polls
        self.globals['polling']['maxNoAckLimit'] = int(0)  # Default to zero 'no ack's i.e. effectively don't reload plugin
        self.globals['polling']['count'] = int(0)
        self.globals['polling']['trigger'] = int(0)

        # Initialise dictionary for constants
        self.globals['constant'] = {}
        self.globals['constant']['defaultDatetime'] = datetime.strptime("2000-01-01","%Y-%m-%d")

        # Initialise dictionary for update checking
        self.globals['update'] = {}

        # Set Plugin Config Values
        self.closedPrefsConfigUi(pluginPrefs, False)
 
    def __del__(self):

        indigo.PluginBase.__del__(self)

    def updatePlugin(self):
        self.globals['update']['updater'].update()

    def checkForUpdates(self):
        self.globals['update']['updater'].checkForUpdate()

    def forceUpdate(self):
        self.globals['update']['updater'].update(currentVersion='0.0.0')

    def checkRateLimit(self):
        limiter = self.globals['update']['updater'].getRateLimit()
        indigo.server.log('RateLimit {limit:%d remaining:%d resetAt:%d}' % limiter)

    def startup(self):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        # Set-up update checker
        self.globals['update']['updater'] = GitHubPluginUpdater(self)
        self.globals['update']['nextCheckTime'] = time()

        # Create LIFX folder name in variables (for presets) and devices (for lamps)
        folderName = "LIFX"
        if folderName not in indigo.variables.folders:
            folder = indigo.variables.folder.create(folderName)
        self.globals['folders']['VariablesId'] = indigo.variables.folders.getId(folderName)

        folderName = "LIFX"
        if folderName not in indigo.devices.folders:
            folder = indigo.devices.folder.create(folderName)
        self.globals['folders']['DevicesId'] = indigo.devices.folders.getId(folderName)

        indigo.devices.subscribeToChanges()

        # Create lifxlanHandler process queue
        self.globals['queues']['lifxlanHandler'] = Queue.PriorityQueue()  # Used to queue lifxlanHandler commands

        self.globals['threads']['lifxlanHandler']['event']  = threading.Event()
        self.globals['threads']['lifxlanHandler']['thread'] = ThreadLifxlanHandler(self.globals, self.globals['threads']['lifxlanHandler']['event'])
        self.globals['threads']['lifxlanHandler']['thread'].start()

        if self.globals['polling']['status'] == True and self.globals['polling']['threadActive'] == False:
            self.globals['threads']['polling']['event']  = threading.Event()
            self.globals['threads']['polling']['thread'] = ThreadPolling(self.globals, self.globals['threads']['polling']['event'])
            self.globals['threads']['polling']['thread'].start()

        self.generalLogger.info(u"Autolog 'LIFX V5 Controller' initialization complete")
        
    def shutdown(self):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        if self.globals['polling']['threadActive']:
            self.globals['polling']['forceThreadEnd'] = True
            self.globals['threads']['polling']['event'].set()  # Stop the Polling Thread

        self.generalLogger.info(u"Autolog 'LIFX V5 Controller' Plugin shutdown complete")


    def validatePrefsConfigUi(self, valuesDict):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        try: 
            if "missedPollLimit" in valuesDict:
                try:
                    temp = int(valuesDict["missedPollLimit"])
                except:
                    errorDict = indigo.Dict()
                    errorDict["missedPollLimit"] = "Invalid number for missed polls limit"
                    errorDict["showAlertText"] = "The number of missed polls limit must be specified as an integer e.g 2, 5 etc."
                    return (False, valuesDict, errorDict)
            else:
                self.globals['polling']['missedPollLimit'] = int(360)  # Default to 6 minutes

            if "maxNoAckLimit" in valuesDict:
                try:
                    temp = int(valuesDict["maxNoAckLimit"])
                except:
                    errorDict = indigo.Dict()
                    errorDict["maxNoAckLimit"] = "Invalid number for Max No Ack limit"
                    errorDict["showAlertText"] = "The number of 'No Ack's limit must be specified as an integer e.g 0, 1, 2, 5 etc."
                    return (False, valuesDict, errorDict)

            if "defaultDurationDimBrighten" in valuesDict:
                try:
                    temp = float(valuesDict["defaultDurationDimBrighten"])
                except:
                    errorDict = indigo.Dict()
                    errorDict["defaultDurationDimBrighten"] = "Invalid number for seconds"
                    errorDict["showAlertText"] = "The number of seconds must be specified as an integer or float e.g. 2, 2.0 or 2.5 etc."
                    return (False, valuesDict, errorDict)

            if "defaultDurationDimBrighten" in valuesDict:
                try:
                    temp = float(valuesDict["defaultDurationDimBrighten"])
                except:
                    errorDict = indigo.Dict()
                    errorDict["defaultDurationDimBrighten"] = "Invalid number for seconds"
                    errorDict["showAlertText"] = "The number of seconds must be specified as an integer or float e.g. 2, 2.0 or 2.5 etc."
                    return (False, valuesDict, errorDict)

            if "defaultDurationOn" in valuesDict:
                try:
                    temp = float(valuesDict["defaultDurationOn"])
                except:
                    errorDict = indigo.Dict()
                    errorDict["defaultDurationOn"] = "Invalid number for seconds"
                    errorDict["showAlertText"] = "The number of seconds must be specified as an integer or float e.g. 2, 2.0 or 2.5 etc."
                    return (False, valuesDict, errorDict)

            if "defaultDurationOff" in valuesDict:
                try:
                    temp = float(valuesDict["defaultDurationOff"])
                except:
                    errorDict = indigo.Dict()
                    errorDict["defaultDurationOff"] = "Invalid number for seconds"
                    errorDict["showAlertText"] = "The number of seconds must be specified as an integer or float e.g. 2, 2.0 or 2.5 etc."
                    return (False, valuesDict, errorDict)

            if "defaultDurationColorWhite" in valuesDict:
                try:
                    temp = float(valuesDict["defaultDurationColorWhite"])
                except:
                    errorDict = indigo.Dict()
                    errorDict["defaultDurationColorWhite"] = "Invalid number for seconds"
                    errorDict["showAlertText"] = "The number of seconds must be specified as an integer or float e.g. 2, 2.0 or 2.5 etc."
                    return (False, valuesDict, errorDict)

            return True

        except StandardError, e:
            self.generalLogger.error(u"validatePrefsConfigUi error detected. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))   
            return True


    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        try:

            self.generalLogger.debug(u"'closePrefsConfigUi' called with userCancelled = %s" % (str(userCancelled)))  

            if userCancelled:
                return

            self.globals['update']['check'] = bool(valuesDict.get("updateCheck", False))
            self.globals['update']['checkFrequency'] = valuesDict.get("checkFrequency", 'DAILY')

            if self.globals['update']['check']:
                if self.globals['update']['checkFrequency'] == 'WEEKLY':
                    self.globals['update']['checkTimeIncrement'] = (7 * 24 * 60 * 60)  # In seconds
                else:
                    # DAILY 
                    self.globals['update']['checkTimeIncrement'] = (24 * 60 * 60)  # In seconds

            self.globals['polling']['status']          = bool(valuesDict.get("statusPolling", False))
            self.globals['polling']['seconds']         = float(valuesDict.get("pollingSeconds", float(300.0)))  # Default to 5 minutes
            self.globals['polling']['missedPollLimit'] = int(valuesDict.get("missedPollLimit", int(360)))  # Default to 6 minutes
            self.globals['polling']['maxNoAckLimit']   = int(valuesDict.get("maxNoAckLimit", int(0)))  # Default to Zero (no check)

            self.globals['pluginConfigDefault'] = {}
            self.globals['pluginConfigDefault']['durationDimBrighten'] = float(valuesDict.get("defaultDurationDimBrighten", float(1.0)))  # Default to one second
            self.globals['pluginConfigDefault']['durationOn']          = float(self.pluginPrefs.get("defaultDurationOn", 1.0))
            self.globals['pluginConfigDefault']['durationOff']         = float(self.pluginPrefs.get("defaultDurationOff", 1.0))
            self.globals['pluginConfigDefault']['durationColorWhite']  = float(self.pluginPrefs.get("defaultDurationColorWhite ", 1.0))

            # Check monitoring / debug / filered IP address options  
            self.setDebuggingLevels(valuesDict)

            # Following logic checks whether polling is required.
            #
            # If it isn't required, then it checks if a polling thread exists and if it does it ends it
            # If it is required, then it checks if a pollling thread exists and 
            #   if a polling thread doesn't exist it will create one as long as the start logic has completed and created a LIFX Command Queue.
            #   In the case where a LIFX command queue hasn't been created then it means 'Start' is yet to run and so 
            #   'Start' will create the polling thread. So this bit of logic is mainly used where polling has been turned off
            #   after starting and then turned on again
            # If polling is required and a polling thread exists, then the logic 'sets' an event to cause the polling thread to awaken and
            #   update the polling interval

            if not self.globals['polling']['status']:
                if self.globals['polling']['threadActive']:
                    self.globals['polling']['forceThreadEnd'] = True
                    self.globals['threads']['polling']['event'].set()  # Stop the Polling Thread
                    self.globals['threads']['polling']['thread'].join(5.0)  # Wait for up t0 5 seconds for it to end
                    del self.globals['threads']['polling']['thread']  # Delete thread so that it can be recreated if polling is turned on again
            else:
                if not self.globals['polling']['threadActive']:
                    if self.globals['queues']['initialised']:
                        self.globals['polling']['forceThreadEnd'] = False
                        self.globals['threads']['polling']['event'] = threading.Event()
                        self.globals['threads']['polling']['thread'] = ThreadPolling(self.globals, self.globals['threads']['polling']['event'])
                        self.globals['threads']['polling']['thread'].start()
                else:
                    self.globals['polling']['forceThreadEnd'] = False
                    self.globals['threads']['polling']['event'].set()  # cause the Polling Thread to update immediately with potentially new polling seconds value

        except StandardError, e:
            self.generalLogger.error(u"closedPrefsConfigUi error detected. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))   
            return True

    def setDebuggingLevels(self, valuesDict):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        self.globals['debug']['monitorDebugEnabled'] = bool(valuesDict.get("monitorDebugEnabled", False))

        self.globals['debug']['debugFilteredIpAddresses'] = []  # Set to LIFX Lamp IP Address(es) to limit processing for debug purposes
        self.globals['debug']['debugFilteredIpAddressesUI'] = ''  # Set to LIFX Lamp IP Address(es) to limit processing for debug purposes (UI version)

        # set filtered IP address (only if debugging enabled)
        if self.globals['debug']['monitorDebugEnabled'] and valuesDict.get("debugFilteredIpAddresses", '') != '':
            self.globals['debug']['debugFilteredIpAddresses'] = valuesDict.get("debugFilteredIpAddresses", '').replace(' ', '').split(',')  # Create List of IP Addresses to filter on

            if self.globals['debug']['debugFilteredIpAddresses']:  # Evaluates to True if list contains entries
                for ipAddress in self.globals['debug']['debugFilteredIpAddresses']:
                    if self.globals['debug']['debugFilteredIpAddressesUI'] == '':
                        self.globals['debug']['debugFilteredIpAddressesUI'] += ipAddress
                    else:
                        self.globals['debug']['debugFilteredIpAddressesUI'] += ', ' + ipAddress
                        
                if len(self.globals['debug']['debugFilteredIpAddresses']) == 1:    
                    self.generalLogger.warning(u"Filtering on LIFX Device with IP Address: %s" % (self.globals['debug']['debugFilteredIpAddressesUI']))
                else:  
                    self.generalLogger.warning(u"Filtering on LIFX Devices with IP Addresses: %s" % (self.globals['debug']['debugFilteredIpAddressesUI']))  

        self.globals['debug']['debugGeneral'] = logging.INFO  # For general debugging of the main thread
        self.globals['debug']['monitorLifxlanHandler'] = logging.INFO  # For logging messages 
        self.globals['debug']['debugLifxlanHandler'] = logging.INFO  # For debugging messages
        self.globals['debug']['debugMethodTrace'] = logging.INFO  # For displaying method invocations i.e. trace method
        self.globals['debug']['debugPolling'] = logging.INFO  # For polling debugging

        if not self.globals['debug']['monitorDebugEnabled']:
            self.plugin_file_handler.setLevel(logging.INFO)
        else:
            self.plugin_file_handler.setLevel(logging.THREADDEBUG)

        debugGeneral = bool(valuesDict.get("debugGeneral", False))
        monitorLifxlanHandler = bool(valuesDict.get("monitorLifxlanHandler", False))
        debugLifxlanHandler = bool(valuesDict.get("debugLifxlanHandler", False))
        debugMethodTrace = bool(valuesDict.get("debugMethodTrace", False))
        debugPolling = bool(valuesDict.get("debugPolling", False))

        if debugGeneral:
            self.globals['debug']['debugGeneral'] = logging.DEBUG  # For general debugging of the main thread
            self.generalLogger.setLevel(self.globals['debug']['debugGeneral'])
        if monitorLifxlanHandler:
            self.globals['debug']['monitorLifxlanHandler'] = logging.DEBUG  # For logging messages sent to LIFX lamps 
        if debugLifxlanHandler:
            self.globals['debug']['debugLifxlanHandler'] = logging.DEBUG  # For debugging messages sent to LIFX lamps
        if debugMethodTrace:
            self.globals['debug']['debugMethodTrace'] = logging.THREADDEBUG  # For displaying method invocations i.e. trace method
        if debugPolling:
            self.globals['debug']['debugPolling'] = logging.DEBUG  # For polling debugging

        self.globals['debug']['monitoringActive'] = monitorLifxlanHandler

        self.globals['debug']['debugActive'] = debugGeneral or debugLifxlanHandler or debugMethodTrace or debugPolling

        if not self.globals['debug']['monitorDebugEnabled'] or (not self.globals['debug']['monitoringActive'] and not self.globals['debug']['debugActive']):
            self.generalLogger.info(u"No monitoring or debugging requested")
        else:
            if not self.globals['debug']['monitoringActive']:
                self.generalLogger.info(u"No monitoring requested")
            else:
                monitorTypes = []
                if monitorLifxlanHandler:
                    monitorTypes.append('Lifxlan Handler')
                message = self.listActive(monitorTypes)   
                self.generalLogger.warning(u"Monitoring enabled for LIFX: %s" % (message))  

            if not self.globals['debug']['debugActive']:
                self.generalLogger.info(u"No debugging requested")
            else:
                debugTypes = []
                if debugGeneral:
                    debugTypes.append('General')
                if debugLifxlanHandler:
                    debugTypes.append('Lifxlan Handler')
                if debugMethodTrace:
                    debugTypes.append('Method Trace')
                if debugPolling:
                    debugTypes.append('Polling')
                message = self.listActive(debugTypes)   
                self.generalLogger.warning(u"Debugging enabled for LIFX: %s" % (message))  

    def listActive(self, monitorDebugTypes):            
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        loop = 0
        listedTypes = ''
        for monitorDebugType in monitorDebugTypes:
            if loop == 0:
                listedTypes = listedTypes + monitorDebugType
            else:
                listedTypes = listedTypes + ', ' + monitorDebugType
            loop += 1
        return listedTypes

    def runConcurrentThread(self):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        # This thread is used to detect plugin close down and check for updates
        try:
            self.sleep(5) # in seconds - Allow startup to complete
            while True:
                if self.globals['update']['check']:
                    if time() > self.globals['update']['nextCheckTime']:
                        if not 'checkTimeIncrement' in self.globals['update']:
                            self.globals['update']['checkTimeIncrement'] = (24 * 60 * 60)  # One Day In seconds
                        self.globals['update']['nextCheckTime'] = time() + self.globals['update']['checkTimeIncrement']
                        self.generalLogger.info(u"Autolog 'LIFX V5 Controller' checking for Plugin update")
                        self.globals['update']['updater'].checkForUpdate()

                        nextCheckTime = strftime('%A, %Y-%b-%d at %H:%M', localtime(self.globals['update']['nextCheckTime']))
                        self.generalLogger.info(u"Autolog 'LIFX V5 Controller' next update check scheduled for: %s" % nextCheckTime)
                self.sleep(60) # in seconds

        except self.StopThread:
            self.generalLogger.info(u"Autolog 'LIFX V5 Controller' Plugin shutdown requested")

            self.generalLogger.debug(u"runConcurrentThread being ended . . .") 

            if 'lifxlanHandler' in self.globals['threads']:
                self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_STOP_THREAD, 'STOPTHREAD', None, None])

            # Cancel any existing timers
            for lifxDevId in self.globals['deviceTimers']:
                for timer in self.globals['deviceTimers'][lifxDevId]:
                    self.globals['deviceTimers'][lifxDevId][timer].cancel()

            if self.globals['polling']['threadActive']:
                self.globals['polling']['forceThreadEnd'] = True
                self.globals['threads']['polling']['event'].set()  # Stop the Polling Thread
                self.globals['threads']['polling']['thread'].join(7.0)  # wait for thread to end
                self.generalLogger.debug(u"Polling thread now stopped")

            if 'lifxlanHandler' in self.globals['threads']:
                self.globals['threads']['lifxlanHandler']['thread'].join(7.0)  # wait for thread to end
                self.generalLogger.debug(u"LifxlanHandler thread now stopped")

        self.generalLogger.debug(u". . . runConcurrentThread now ended")   

    def deviceStartComm(self, dev):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        try:
            self.generalLogger.info(u"Starting  '%s' . . . " % (dev.name))

            if dev.deviceTypeId != "lifxDevice":
                self.generalLogger.error(u"Failed to start device [%s]: Device type [%s] not known by plugin." % (dev.name, dev.deviceTypeId))
                return

            tempPropsCopy = dev.pluginProps
            tempPropsCopy['WhiteTemperatureMin'] = 2500
            tempPropsCopy['WhiteTemperatureMax'] = 9000
            dev.replacePluginPropsOnServer(tempPropsCopy)

            # dev.setErrorStateOnServer(u"starting")  # Default to 'starting' status
            dev.updateStateImageOnServer(indigo.kStateImageSel.TimerOn)
            dev.updateStateOnServer(key='onOffState', value=False)
            dev.updateStateOnServer(key='brightnessLevel', value=0, uiValue='starting ...')
            # Set Timer and starting

            dev.stateListOrDisplayStateIdChanged()  # Ensure latest devices.xml is being used

            # Cancel any existing timers
            if dev.id in self.globals['deviceTimers']:
                for timer in self.globals['deviceTimers'][dev.id]:
                    self.globals['deviceTimers'][dev.id][timer].cancel()

            # Initialise LIFX Device Timers dictionary
            self.globals['deviceTimers'][dev.id] = {}

            # Initialise internal to plugin lifx lamp states to default values


            if dev.id not in self.globals['lifx']:
                self.globals['lifx'][dev.id] = {}
                self.globals['lifx'][dev.id]['connected'] = False
                self.globals['lifx'][dev.id]['mac_addr'] = dev.address  # eg. 'd0:73:d5:0a:bc:de'
                self.globals['lifx'][dev.id]['ipAddress'] = dev.states['ipAddress']
                self.globals['lifx'][dev.id]['port'] = dev.states['port']
                self.globals['lifx'][dev.id]['lifxlanDeviceIndex'] = None  # Once LIFX device has been discovered this will contain a mapping value
                self.globals['lifx'][dev.id]['ignoreNoAck'] = bool(dev.pluginProps.get('ignoreNoAck', False))
                self.globals['lifx'][dev.id]['noAckState'] = False
                
            if (len(self.globals['debug']['debugFilteredIpAddresses']) > 0) and (dev.states['ipAddress'] not in self.globals['debug']['debugFilteredIpAddresses']):
                dev.setErrorStateOnServer(u"filtered")  # Set to 'filtered' status
                self.generalLogger.info(u"LIFX Device '%s' not in filter list. As requested, LIFX Device not started" % (dev.name))
                self.globals['lifx'][dev.id]['filteredOut'] = True  # Set to True if filtered out and to be treated as disabled
                return
            else:
                self.globals['lifx'][dev.id]['filteredOut'] = False  # Set to False as not filtered out

            self.globals['lifx'][dev.id]['lastResponseToPollCount']  = 0
            self.globals['lifx'][dev.id]['currentLifxComand'] = ''  # Record of current command invoked for LIFX device (just before Queue Get)
            self.globals['lifx'][dev.id]['previousLifxComand']       = ''  # Record of last command invoked for LIFX device

            self.globals['lifx'][dev.id]['datetimeStarted']          = indigo.server.getTime()

            self.globals['lifx'][dev.id]['onState']                  = False      # True or False
            self.globals['lifx'][dev.id]['onOffState']               = 'off'      # 'on' or 'off'
            self.globals['lifx'][dev.id]['turnOnIfOff']              = bool(dev.pluginProps.get('turnOnIfOff', True))

            hsbk = (0,0,0,3500)

            self.globals['lifx'][dev.id]['hsbkHue']                  = hsbk[0]     # Value between 0 and 65535
            self.globals['lifx'][dev.id]['hsbkSaturation']           = hsbk[1]     # Value between 0 and 65535 (e.g. 20% = 13107)
            self.globals['lifx'][dev.id]['hsbkBrightness']           = hsbk[2]     # Value between 0 and 65535
            self.globals['lifx'][dev.id]['hsbkKelvin']               = hsbk[3]  # Value between 2500 and 9000
            self.globals['lifx'][dev.id]['powerLevel']               = 0     # Value between 0 and 65535 

            self.globals['lifx'][dev.id]['groupLabel']               = ''
            self.globals['lifx'][dev.id]['locationLabel']            = ''

            self.globals['lifx'][dev.id]['whenLastOnHsbkHue']        = int(0)    # Value between 0 and 65535
            self.globals['lifx'][dev.id]['whenLastOnHsbkSaturation'] = int(0)    # Value between 0 and 65535 (e.g. 20% = 13107)
            self.globals['lifx'][dev.id]['whenLastOnHsbkBrightness'] = int(0)    # Value between 0 and 65535
            self.globals['lifx'][dev.id]['whenLastOnHsbkKelvin']     = int(3500) # Value between 2500 and 9000
            self.globals['lifx'][dev.id]['whenLastOnPowerLevel']     = int(0)    # Value between 0 and 65535 

            self.globals['lifx'][dev.id]['indigoRed']                = float(0)  # Value between 0.0 and 100.0
            self.globals['lifx'][dev.id]['indigoGreen']              = float(0)  # Value between 0.0 and 100.0
            self.globals['lifx'][dev.id]['indigoBlue']               = float(0)  # Value between 0.0 and 100.0

            self.globals['lifx'][dev.id]['indigoHue']                = float(0)  # Value between 0.0 and 360.0
            self.globals['lifx'][dev.id]['indigoSaturation']         = float(0)  # Value between 0.0 and 100.0
            self.globals['lifx'][dev.id]['indigoBrightness']         = float(0)  # Value between 0.0 and 100.0
            self.globals['lifx'][dev.id]['indigoKelvin']             = float(3500) # Value between 2500 & 9000
            self.globals['lifx'][dev.id]['indigoPowerLevel']         = float(0)  # Value between 0.0 and 100.0
            self.globals['lifx'][dev.id]['indigoWhiteLevel']         = float(0)  # Value between 0.0 and 100.0

            self.globals['lifx'][dev.id]['duration'] = float(1.0)
            if dev.pluginProps.get('overrideDefaultPluginDurations', False):
                self.globals['lifx'][dev.id]['durationDimBrighten'] = float(dev.pluginProps.get('defaultDurationDimBrighten', self.globals['pluginConfigDefault']['durationDimBrighten']))
                self.globals['lifx'][dev.id]['durationOn']          = float(dev.pluginProps.get('defaultDurationOn', self.globals['pluginConfigDefault']['durationOn']))
                self.globals['lifx'][dev.id]['durationOff']         = float(dev.pluginProps.get('defaultDurationOff', self.globals['pluginConfigDefault']['durationOff']))
                self.globals['lifx'][dev.id]['durationColorWhite']  = float(dev.pluginProps.get('defaultDurationColorWhite', self.globals['pluginConfigDefault']['durationColorWhite']))

            else:
                self.globals['lifx'][dev.id]['durationDimBrighten'] = float(self.globals['pluginConfigDefault']['durationDimBrighten'])
                self.globals['lifx'][dev.id]['durationOn']          = float(self.globals['pluginConfigDefault']['durationOn'])
                self.globals['lifx'][dev.id]['durationOff']         = float(self.globals['pluginConfigDefault']['durationOff'])
                self.globals['lifx'][dev.id]['durationColorWhite']  = float(self.globals['pluginConfigDefault']['durationColorWhite'])

            # variables for holding SETLAMP command values
            self.globals['lifx'][dev.id]['lampTarget'] = {}                    # Target states
            self.globals['lifx'][dev.id]['lampTarget']['active']     = False     
            self.globals['lifx'][dev.id]['lampTarget']['hue']        = '0.0'   # Value between 0.0 and 65535.0
            self.globals['lifx'][dev.id]['lampTarget']['saturation'] = '0.0'   # Value between 0.0 and 65535.0
            self.globals['lifx'][dev.id]['lampTarget']['kelvin']     = '3500'  # Value between 2500 and 9000
            self.globals['lifx'][dev.id]['lampTarget']['brightness'] = '0'     # Value between 0 and 100
            self.globals['lifx'][dev.id]['lampTarget']['duration']   = '0.0'

            keyValueList = [
                {'key': 'lifxOnState', 'value': self.globals['lifx'][dev.id]['onState']},
                {'key': 'lifxOnOffState', 'value': self.globals['lifx'][dev.id]['onOffState']},

                {'key': 'hsbkHue', 'value': self.globals['lifx'][dev.id]['hsbkHue']},
                {'key': 'hsbkSaturation', 'value': self.globals['lifx'][dev.id]['hsbkSaturation']},
                {'key': 'hsbkBrightness', 'value': self.globals['lifx'][dev.id]['hsbkBrightness']},
                {'key': 'hsbkKelvin', 'value': self.globals['lifx'][dev.id]['hsbkKelvin']},
                {'key': 'powerLevel', 'value': self.globals['lifx'][dev.id]['powerLevel']},
                {'key': 'ipAddress', 'value': self.globals['lifx'][dev.id]['ipAddress']},
                {'key': 'port', 'value': self.globals['lifx'][dev.id]['port']},

                {'key': 'groupLabel', 'value': self.globals['lifx'][dev.id]['groupLabel']},
                {'key': 'locationLabel', 'value': self.globals['lifx'][dev.id]['locationLabel']},

                {'key': 'whenLastOnHsbkHue', 'value': self.globals['lifx'][dev.id]['whenLastOnHsbkHue']},
                {'key': 'whenLastOnHsbkSaturation', 'value': self.globals['lifx'][dev.id]['whenLastOnHsbkSaturation']},
                {'key': 'whenLastOnHsbkBrightness', 'value': self.globals['lifx'][dev.id]['whenLastOnHsbkBrightness']},
                {'key': 'whenLastOnHsbkKelvin', 'value': self.globals['lifx'][dev.id]['whenLastOnHsbkKelvin']},
                {'key': 'whenLastOnPowerLevel', 'value': self.globals['lifx'][dev.id]['whenLastOnPowerLevel']},

                {'key': 'indigoHue', 'value': self.globals['lifx'][dev.id]['indigoHue']},
                {'key': 'indigoSaturation', 'value': self.globals['lifx'][dev.id]['indigoSaturation']},
                {'key': 'indigoBrightness', 'value': self.globals['lifx'][dev.id]['indigoBrightness']},
                {'key': 'indigoKelvin', 'value': self.globals['lifx'][dev.id]['indigoKelvin']},
                {'key': 'indigoPowerLevel', 'value': self.globals['lifx'][dev.id]['indigoPowerLevel']},

                {'key': 'whiteTemperature', 'value': self.globals['lifx'][dev.id]['indigoKelvin']},
                {'key': 'whiteLevel', 'value': self.globals['lifx'][dev.id]['indigoBrightness']},

                {'key': 'duration', 'value': self.globals['lifx'][dev.id]['duration']},
                {'key': 'durationDimBrighten', 'value': self.globals['lifx'][dev.id]['durationDimBrighten']},
                {'key': 'durationOn', 'value': self.globals['lifx'][dev.id]['durationOn']},
                {'key': 'durationOff', 'value': self.globals['lifx'][dev.id]['durationOff']},
                {'key': 'durationColorWhite', 'value': self.globals['lifx'][dev.id]['durationColorWhite']},
                {'key': 'noAckState', 'value': self.globals['lifx'][dev.id]['noAckState']},
                {'key': 'connected', 'value': False}]

            props = dev.pluginProps
            if ("SupportsRGB" in props) and props["SupportsRGB"]:
                keyValueList.append({'key': 'redLevel', 'value': self.globals['lifx'][dev.id]['indigoRed']})
                keyValueList.append({'key': 'greenLevel', 'value': self.globals['lifx'][dev.id]['indigoGreen']})
                keyValueList.append({'key': 'blueLevel', 'value': self.globals['lifx'][dev.id]['indigoBlue']})

            dev.updateStatesOnServer(keyValueList, clearErrorState=False)

            self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_STATUS_MEDIUM, 'STATUS', dev.id, None])
            # self.generalLogger.info(u". . . Started '%s' " % (dev.name))
        except StandardError, e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            self.generalLogger.error(u"deviceStartComm: StandardError detected for '%s' at line '%s' = %s" % (dev.name, exc_tb.tb_lineno,  e))   


    def deviceStopComm(self, dev):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        self.generalLogger.info(u"Stopping '%s'" % (dev.name))

        dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)  # Default to grey circle indicating 'offline'
        dev.updateStateOnServer(key='onOffState', value=False, clearErrorState=True)
        dev.updateStateOnServer(key='brightnessLevel', value=0, uiValue=u'not enabled', clearErrorState=True)
        self.globals['lifx'][dev.id]["connected"] = False

        # Cancel any existing timers
        if dev.id in self.globals['deviceTimers']:
            for timer in self.globals['deviceTimers'][dev.id]:
                self.globals['deviceTimers'][dev.id][timer].cancel()

    def deviceUpdated(self, origDev, newDev):

        if origDev.deviceTypeId == 'lifxDevice' and newDev.deviceTypeId == 'lifxDevice':
            #  self.methodTracer.threaddebug(u"CLASS: Plugin")  # Disabled as too many log messages!  
            if origDev.name != newDev.name: 
                if bool(newDev.pluginProps.get('setLifxLabelFromIndigoDeviceName', False)):  # Only change LIFX Lamp label if option set
                    self.generalLogger.info(u"Changing LIFX Lamp label from '%s' to '%s'" % (origDev.name, newDev.name))
                    self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_COMMAND, 'SETLABEL', newDev.id, None])
        indigo.PluginBase.deviceUpdated(self, origDev, newDev)

        return  

    ################################################################################
    # This is the method that's called to build the member device list.
    # Note: valuesDict is read-only so any changes you make to it will be discarded.
    ################################################################################
    def lifxDevicesList(self, filter, valuesDict, typeId, ahbDevId):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        self.generalLogger.debug(u"lifxDevicesList called with filter: %s  typeId: %s  Hue Hub: %s" % (filter, typeId, str(ahbDevId)))

        deviceList = list()
        for dev in indigo.devices:
            if dev.deviceTypeId == LIFX_DEVICE_TYPEID:
                deviceList.append((dev.id, dev.name))
        if len(deviceList)  == 0:
            deviceList = list((0,'NO LIFX DEVICES DETECTED'))
        return deviceList


    def validateDeviceConfigUi(self, valuesDict, typeId, devId):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        self.currentTime = indigo.server.getTime()

        if "ignoreNoAck" in valuesDict and devId in self.globals['lifx']:
            self.globals['lifx'][devId]['ignoreNoAck'] = bool(valuesDict.get("ignoreNoAck", False))

        if "overrideDefaultPluginDurations" in valuesDict and valuesDict["overrideDefaultPluginDurations"] == True:

            # Validate 'defaultDurationDimBrighten' value
            defaultDurationDimBrighten = valuesDict.get("defaultDurationDimBrighten", '1.0').rstrip().lstrip()
            try:
                if float(defaultDurationDimBrighten) <= 0.0:
                    raise ValueError('DefaultDurationDimBrighten must be greater than zero')
                valuesDict["defaultDurationDimBrighten"] = '%.1f' % float(defaultDurationDimBrighten)
            except:
                errorDict = indigo.Dict()
                errorDict["defaultDurationDimBrighten"] = "Default duration for dimming and brightness must be greater than zero"
                errorDict["showAlertText"] = "You must enter a valid Default Duration for dimming and brightness value for the LIFX lamp. It must be greater than zero"
                return (False, valuesDict, errorDict)

            # Validate 'defaultDurationOn' value
            defaultDurationOn = valuesDict.get("defaultDurationOn", '1.0').rstrip().lstrip()
            try:
                if float(defaultDurationOn) <= 0.0:
                    raise ValueError('DefaultDurationOn must be greater than zero')
                valuesDict["defaultDurationOn"] = '%.1f' % float(defaultDurationOn)
            except:
                errorDict = indigo.Dict()
                errorDict["defaultDurationOn"] = "Default Turn On duration must be greater than zero"
                errorDict["showAlertText"] = "You must enter a valid Default Turn On Duration value for the LIFX lamp. It must be greater than zero"
                return (False, valuesDict, errorDict)

            # Validate 'defaultDurationOff' value
            defaultDurationOff = valuesDict.get("defaultDurationOff", '1.0').rstrip().lstrip()
            try:
                if float(defaultDurationOff) <= 0.0:
                    raise ValueError('DefaultDurationOff must be greater than zero')
                valuesDict["defaultDurationOff"] = '%.1f' % float(defaultDurationOff)
            except:
                errorDict = indigo.Dict()
                errorDict["defaultDurationOff"] = "Default Turn Off duration must be greater than zero"
                errorDict["showAlertText"] = "You must enter a valid Default Turn Off Duration value for the LIFX lamp. It must be greater than zero"
                return (False, valuesDict, errorDict)

            # Validate 'defaultDurationColorWhite' value
            defaultDurationColorWhite = valuesDict.get("defaultDurationColorWhite", '1.0').rstrip().lstrip()
            try:
                if float(defaultDurationColorWhite) <= 0.0:
                    raise ValueError('DefaultDurationColorWhite must be greater than zero')
                valuesDict["defaultDurationColorWhite"] = '%.1f' % float(defaultDurationColorWhite)
            except:
                errorDict = indigo.Dict()
                errorDict["defaultDurationColorWhite"] = "Default Set Color/White duration must be greater than zero"
                errorDict["showAlertText"] = "You must enter a valid Default Set Color/White Duration value for the LIFX lamp. It must be greater than zero"
                return (False, valuesDict, errorDict)

        return (True, valuesDict)


    def getActionConfigUiValues(self, pluginProps, typeId, actionId):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        self.generalLogger.debug(u"getActionConfigUiValues: typeId [%s], actionId [%s], pluginProps[%s]" % (typeId, actionId, pluginProps))

        errorDict = indigo.Dict()
        valuesDict = pluginProps

        if typeId == "setColorWhite":  # <Action id="setColorWhite" deviceFilter="self.lifxDevice">

            valuesDict["option"] = 'SELECT_OPTION'
            valuesDict["optionPresetList"] = 'SELECT_PRESET'

            if 'actionType' not in valuesDict:
                valuesDict["actionType"] = 'SELECT_ACTION_TYPE'
            if 'turnOnifOffStandard' not in valuesDict:
                valuesDict["turnOnifOffStandard"] = True
            if 'modeStandard' not in valuesDict:
                valuesDict["modeStandard"] = 'SELECT_COLOR_OR_WHITE'
            if 'hueStandard' not in valuesDict:
                valuesDict["hueStandard"] = ''
            if 'saturationStandard' not in valuesDict:
                valuesDict["saturationStandard"] = ''
            if 'kelvinStandard' not in valuesDict:
                valuesDict["kelvinStandard"] = 'NONE'
            if 'brightnessStandard' not in valuesDict:
                valuesDict["brightnessStandard"] = ''
            if 'durationStandard' not in valuesDict:
                valuesDict["durationStandard"] = ''
            if 'modeWaveform' not in valuesDict:
                valuesDict["modeWaveform"] = 'SELECT_COLOR_OR_WHITE'
            if 'hueWaveform' not in valuesDict:
                valuesDict["hueWaveform"] = ''
            if 'saturationWaveform' not in valuesDict:
                valuesDict["saturationWaveform"] = ''
            if 'kelvinWaveform' not in valuesDict:
                valuesDict["kelvinWaveform"] = 'NONE'
            if 'brightnessWaveform' not in valuesDict:
                valuesDict["brightnessWaveform"] = ''
            if 'transientWaveform' not in valuesDict:
                valuesDict["transientWaveform"] = True
            if 'periodWaveform' not in valuesDict:
                valuesDict["periodWaveform"] = ''
            if 'cyclesWaveform' not in valuesDict:
                valuesDict["cyclesWaveform"] = ''
            if 'dutyCycleWaveform' not in valuesDict:
                valuesDict["dutyCycleWaveform"] = '0'  # Equal Time on Both
            if 'typeWaveform' not in valuesDict:
                valuesDict["typeWaveform"] = '0'  # Saw
 
            valuesDict["selectedPresetOption"] = 'NONE'
            valuesDict["resultPreset"] = 'resultNa'

            valuesDict = self.actionConfigOptionSelected(valuesDict, typeId, actionId)

            if 'actionType' in valuesDict:
                if valuesDict["actionType"] == 'Standard':
                    if 'modeStandard' in valuesDict:
                        if valuesDict["modeStandard"] == 'Color':
                            valuesDict, errorDict = self.hueSaturationBrightnessStandardUpdated(valuesDict, typeId, actionId)
                        elif valuesDict["modeStandard"] == 'White': 
                            valuesDict, errorDict = self.kelvinStandardUpdated(valuesDict, typeId, actionId)
                elif  valuesDict["actionType"] == 'Waveform':
                    if 'modeWaveform' in valuesDict:
                        if valuesDict["modeWaveform"] == 'Color':
                            valuesDict, errorDict = self.hueSaturationBrightnessWaveformUpdated(valuesDict, typeId, actionId)
                        elif valuesDict["modeWaveform"] == 'White': 
                            valuesDict, errorDict = self.kelvinWaveformUpdated(valuesDict, typeId, actionId)

        return (valuesDict, errorDict)


    def colorPickerUpdated(self, valuesDict, typeId, devId):
        if valuesDict["actionType"] == 'Standard':
            rgbHexList = valuesDict["colorStandardColorpicker"].split()

            # Convert color picker values for RGB (x00-xFF100) to colorSys values (0.0-1.0)
            red   = float(int(rgbHexList[0], 16) / 255.0)
            green = float(int(rgbHexList[1], 16) / 255.0)
            blue  = float(int(rgbHexList[2], 16) / 255.0)

            hsv_hue, hsv_saturation, hsv_brightness = colorsys.rgb_to_hsv(red, green, blue)

            # Convert colorsys values for HSV (0.0-1.0) to H (0-360), S (0.0-100.0) and V aka B (0.0-100.0) 
            valuesDict["hueStandard"] = '%s' % int(hsv_hue * 360.0)
            valuesDict["saturationStandard"] = '%s' % int(hsv_saturation * 100.0)
            valuesDict["brightnessStandard"] = '%s' % int(hsv_brightness * 100.0)
        elif valuesDict["actionType"] == 'Waveform':
            rgbHexList = valuesDict["colorWaveformColorpicker"].split()

            # Convert color picker values for RGB (x00-xFF100) to colorSys values (0.0-1.0)
            red   = float(int(rgbHexList[0], 16) / 255.0)
            green = float(int(rgbHexList[1], 16) / 255.0)
            blue  = float(int(rgbHexList[2], 16) / 255.0)

            hsv_hue, hsv_saturation, hsv_brightness = colorsys.rgb_to_hsv(red, green, blue)

            # Convert colorsys values for HSV (0.0-1.0) to H (0-360), S (0.0-100.0) and V aka B (0.0-100.0) 
            valuesDict["hueWaveform"] = '%s' % int(hsv_hue * 360.0)
            valuesDict["saturationWaveform"] = '%s' % int(hsv_saturation * 100.0)
            valuesDict["brightnessWaveform"] = '%s' % int(hsv_brightness * 100.0)

        return (valuesDict)


    def validateActionConfigUi(self, valuesDict, typeId, actionId):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        errorsDict = indigo.Dict()

        if typeId == "setColorWhite":
            validateResult = self.validateActionConfigUiSetColorWhite(valuesDict, typeId, actionId)
        else:
            self.generalLogger.debug(u"validateActionConfigUi [UNKNOWN]: typeId=[%s], actionId=[%s]" % (typeId, actionId))
            return (True, valuesDict)

        if validateResult[0]:
            return (True, validateResult[1])
        else:
            return (False, validateResult[1], validateResult[2])

 
    def validateActionConfigUiSetColorWhite(self, valuesDict, typeId, actionId):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        self.generalLogger.debug(u"validateActionConfigUiSetColorWhite: typeId=[%s], actionId=[%s]" % (typeId, actionId))

       # validate LIFX ActionType
        actionType = valuesDict["actionType"]
        if actionType != "Standard" and actionType != "Waveform":
            errorDict = indigo.Dict()
            errorDict["actionType"] = "LIFX Action must be set to one of 'Standard' or 'Waveform'"
            errorDict["showAlertText"] = "You must select a valid LIFX Action; either 'Standard' or 'Waveform'"
            return (False, valuesDict, errorDict)

        if actionType == 'Standard':
            # Validation for LIFX ActionType 'Waveform'

            valueCount = 0  # To count number of fields entered for consistency check

            # validate modeStandard
            modeStandard = valuesDict["modeStandard"]
            if modeStandard != "Color" and modeStandard != "White":
                errorDict = indigo.Dict()
                errorDict["modeStandard"] = "Color / White selection must be set to one of 'Color' or 'White'"
                errorDict["showAlertText"] = "YColor / White selection must be set to one of 'Color' or 'White'"
                return (False, valuesDict, errorDict)

            if modeStandard == "Color":
                # Validate 'hueStandard' value
                hueStandard = valuesDict["hueStandard"].rstrip().lstrip()  # Remove leading/trailing spaces
                if hueStandard == '' or hueStandard == '-':
                    valuesDict["hueStandard"] = '-'
                else:
                    try:
                        hueStandard = '%.1f' % float(hueStandard)
                        if float(hueStandard) < 0.0 or float(hueStandard) > 360.0:
                            raise ValueError('Hue must be set between 0.0 and 360.0 (inclusive)')
                        valuesDict["hueStandard"] = hueStandard
                        valueCount += 1  # At least one of the required fields now entered
                    except:
                        errorDict = indigo.Dict()
                        errorDict["hueStandard"] = "Hue must be set between 0.0 and 360.0 (inclusive) or '-' (dash) to not set value"
                        errorDict["showAlertText"] = "You must enter a valid Hue value for the LIFX device. It must be a value between 0.0 and 360.0 (inclusive) or '-' (dash) to leave an existing value unchanged"
                        return (False, valuesDict, errorDict)

            if modeStandard == "Color":
                # Validate 'saturationStandard' value
                saturationStandard = valuesDict["saturationStandard"].rstrip().lstrip()
                if saturationStandard == '' or saturationStandard == '-':
                    valuesDict["saturationStandard"] = '-'
                else:
                    try:
                        saturationStandard = '%.1f' % float(saturationStandard)
                        if float(saturationStandard) < 0.0 or float(saturationStandard) > 100.0:
                            raise ValueError('Saturation must be set between 0.0 and 100.0 (inclusive)')
                        valuesDict["saturationStandard"] = saturationStandard
                        valueCount += 1  # At least one of the required fields now entered
                    except:
                        errorDict = indigo.Dict()
                        errorDict["saturationStandard"] = "Saturation must be set between 0.0 and 100.0 (inclusive) or '-' (dash) to not set value"
                        errorDict["showAlertText"] = "You must enter a valid Saturation value for the LIFX device. It must be a value between 0.0 and 100.0 (inclusive) or '-' (dash) to leave an existing value unchanged"
                        return (False, valuesDict, errorDict)

            if modeStandard == "White":
                # Validate 'kelvinStandard' value
                kelvinStandard = valuesDict["kelvinStandard"]
                if kelvinStandard == '-': 
                    pass
                else:
                    try:
                        kelvinStandard = int(kelvinStandard)  # Extract Kelvin value from description
                        if kelvinStandard < 2500 or kelvinStandard > 9000:
                            raise ValueError('Kelvin must be set between 2500 and 9000 (inclusive)')
                        #valuesDict["kelvinStandard"] = kelvinStandard
                        valueCount += 1  # At least one of the required fields now entered
                    except:
                        errorDict = indigo.Dict()
                        errorDict["kelvinStandard"] = "Kelvin must be set to one of the presets between 2500 and 9000 (inclusive) or to 'Use current Kelvin value' to leave the existing value unchanged"
                        errorDict["showAlertText"] = "You must select a valid Kelvin value for the LIFX device or to 'Use current Kelvin value' to leave the existing value unchanged"
                        return (False, valuesDict, errorDict)

           # Validate 'brightnessStandard' value
            brightnessStandard = valuesDict["brightnessStandard"].rstrip().lstrip()
            if brightnessStandard == '' or brightnessStandard == '-':
                valuesDict["brightnessStandard"] = '-'
            else:
                try:
                    brightnessStandard = '%.1f' % float(brightnessStandard)
                    if float(brightnessStandard) < 0.0 or float(brightnessStandard) > 100.0:
                        raise ValueError('Brightness must be set between 0.0 and 100.0 (inclusive)')
                    valuesDict["brightnessStandard"] = brightnessStandard
                    valueCount += 1  # At least one of the required fields now entered
                except:
                    errorDict = indigo.Dict()
                    errorDict["brightnessStandard"] = "Brightness must be set between 0.0 and 100.0 (inclusive) or '-' (dash) to not set value"
                    errorDict["showAlertText"] = "You must enter a valid Brightness value for the LIFX device. It must be a value between 0.0 and 100.0 (inclusive) or '-' (dash) to leave an existing value unchanged"
                    return (False, valuesDict, errorDict)





            # Validate 'durationStandard' value
            durationStandard = valuesDict["durationStandard"].rstrip().lstrip()
            if durationStandard == '' or durationStandard == '-':
                durationStandard = '-'
            else:
                try:
                    durationStandard = '%.1f' % float(durationStandard)
                    valuesDict["durationStandard"] = durationStandard
                    valueCount += 1  # At least one of the required fields now entered
                except:
                    errorDict = indigo.Dict()
                    errorDict["durationStandard"] = "Duration must be numeric or '-' (dash) to not set value"
                    errorDict["showAlertText"] = "You must enter a valid Duration value for the LIFX device. It must be a numeric e.g. 2.5 (representing seconds)  or '-' (dash) to leave an existing value unchanged"
                    return (False, valuesDict, errorDict)

            if valueCount == 0:  # All values missing / not specified 
                errorDict = indigo.Dict()
                if modeStandard == 'Color':
                    errorMsg = u"One of Hue, Saturation, Brightness or Duration must be present"
                    errorDict["hueStandard"] = errorMsg
                    errorDict["saturationStandard"] = errorMsg
                else:
                    # 'White'
                    errorMsg = u"One of Kelvin, Brightness or Duration must be present"
                    errorDict["kelvinStandard"] = u"One of Hue, Kelvin, Brightness or Duration must be present"
                errorDict["brightnessStandard"] = errorMsg
                errorDict["durationStandard"] = errorMsg
                errorDict["showAlertText"] = errorMsg
                return (False, valuesDict, errorDict)

            if typeId == "setColorWhite":
                if valuesDict["selectedPresetOption"] != "NONE":
                    errorDict = indigo.Dict()
                    errorDict["selectedPresetOption"] = "Preset Options must be set to 'No Action'"
                    errorDict["showAlertText"] = "Preset Options must be set to 'No Action' before you can Save. This is a safety check in case you meant to save/update a Preset and forgot to do so ;-)"
                    return (False, valuesDict, errorDict)

            return (True, valuesDict)

        else:
            # Validation for LIFX ActionType 'Waveform'

            # validate modeWaveform
            modeWaveform = valuesDict["modeWaveform"]
            if modeWaveform != "Color" and modeWaveform != "White":
                errorDict = indigo.Dict()
                errorDict["modeWaveform"] = "Color / White selection must be set to one of 'Color' or 'White'"
                errorDict["showAlertText"] = "YColor / White selection must be set to one of 'Color' or 'White'"
                return (False, valuesDict, errorDict)

            if modeWaveform == "Color":
                # Validate 'hueWaveform' value
                hueWaveform = valuesDict["hueWaveform"].rstrip().lstrip()  # Remove leading/trailing spaces
                try:
                    hueWaveform = '%.1f' % float(hueWaveform)
                    if float(hueWaveform) < 0.0:
                        raise ValueError('Hue must be a positive number')
                    if float(hueWaveform) < 0.0 or float(hueWaveform) > 360.0:
                        raise ValueError('Hue must be set between 0.0 and 360.0 (inclusive)')
                    valuesDict["hueWaveform"] = hueWaveform
                except:
                    errorDict = indigo.Dict()
                    errorDict["hueWaveform"] = "Hue must be set between 0.0 and 360.0 (inclusive)"
                    errorDict["showAlertText"] = "You must enter a valid Hue value for the LIFX device. It must be a value between 0.0 and 360.0 (inclusive)"
                    return (False, valuesDict, errorDict)

            if modeWaveform == "Color":
                # Validate 'saturationWaveform' value
                saturationWaveform = valuesDict["saturationWaveform"].rstrip().lstrip()
                try:
                    saturationWaveform = '%.1f' % float(saturationWaveform)
                    if float(saturationWaveform) < 0.0 or float(saturationWaveform) > 100.0:
                        raise ValueError('Saturation must be set between 0.0 and 100.0 (inclusive)')
                    valuesDict["saturationWaveform"] = saturationWaveform
                except:
                    errorDict = indigo.Dict()
                    errorDict["saturationWaveform"] = "Saturation must be set between 0.0 and 100.0 (inclusive)"
                    errorDict["showAlertText"] = "You must enter a valid Saturation value for the LIFX device. It must be a value between 0.0 and 100.0 (inclusive)"
                    return (False, valuesDict, errorDict)

            if modeWaveform == "White":
                # Validate 'kelvinWaveform' value
                kelvinWaveform = valuesDict["kelvinWaveform"].rstrip().lstrip()
                try:
                    kelvinWaveform = int(kelvinWaveform)
                    if kelvinWaveform < 2500 or kelvinWaveform > 9000:
                        raise ValueError('Kelvin must be set between 2500 and 9000 (inclusive)')
                    valuesDict["kelvinWaveform"] = kelvinWaveform
                except:
                    errorDict = indigo.Dict()
                    errorDict["kelvinWaveform"] = "Kelvin must be set between 2500 and 9000 (inclusive)"
                    errorDict["showAlertText"] = "You must enter a valid Kelvin value for the LIFX device. It must be an integer between 2500 and 9000 (inclusive)"
                    return (False, valuesDict, errorDict)

           # Validate 'brightnessWaveform' value
            brightnessWaveform = valuesDict["brightnessWaveform"].rstrip().lstrip()
            try:
                brightnessWaveform = '%.1f' % float(brightnessWaveform)
                if float(brightnessWaveform) < 0.0 or float(brightnessWaveform) > 100.0:
                    raise ValueError('Brightness must be set between 0.0 and 100.0 (inclusive)')
                valuesDict["brightnessWaveform"] = brightnessWaveform
            except:
                errorDict = indigo.Dict()
                errorDict["brightnessWaveform"] = "Brightness must be set between 0.0 and 100.0 (inclusive)"
                errorDict["showAlertText"] = "You must enter a valid Brightness value for the LIFX device. It must be a value between 0.0 and 100.0 (inclusive)"
                return (False, valuesDict, errorDict)

            # Validate 'periodWaveform' value
            periodWaveform = valuesDict["periodWaveform"].rstrip().lstrip()
            try:
                periodWaveform = '%s' % int(periodWaveform)
                valuesDict["periodWaveform"] = periodWaveform
            except:
                errorDict = indigo.Dict()
                errorDict["periodWaveform"] = "Period must be numeric"
                errorDict["showAlertText"] = "You must enter a valid Period value for the LIFX device. It must be a numeric e.g. 750 (representing milliseconds)"
                return (False, valuesDict, errorDict)

            # Validate 'cyclesWaveform' value
            cyclesWaveform = valuesDict["cyclesWaveform"].rstrip().lstrip()
            try:
                cyclesWaveform = str(int(cyclesWaveform))
                valuesDict["cyclesWaveform"] = cyclesWaveform
            except:
                errorDict = indigo.Dict()
                errorDict["cyclesWaveform"] = "Cycles must be numeric"
                errorDict["showAlertText"] = "You must enter a valid Cycles value for the LIFX device. It must be a numeric e.g. 10 (representing whole seconds)"
                return (False, valuesDict, errorDict)

        if valuesDict["selectedPresetOption"] != "NONE":
            errorDict = indigo.Dict()
            errorDict["selectedPresetOption"] = "Preset Options must be set to 'No Action'"
            errorDict["showAlertText"] = "Preset Options must be set to 'No Action' before you can Save. A safety check to check if you were trying to save/update a Preset and forgot to do so ;-)"
            return (False, valuesDict, errorDict)

        return (True, valuesDict)


    def openedActionConfigUi(self, valuesDict, typeId, actionId):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        self.generalLogger.debug(u"openedActionConfigUi intercepted")

        return valuesDict

    def actionConfigListKelvinValues(self, filter="", valuesDict=None, typeId="", targetId=0):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        kelvinArray = [('NONE', '- Select Kelvin value -'), ('CURRENT', 'Use current Kelvin value')]
        for kelvin in LIFX_KELVINS:
            kelvinArray.append((str(kelvin), LIFX_KELVINS[kelvin][1]))  # Kelvin value, kelvin description
        def getKelvin(kelvinItem):
            return kelvinItem[1]
        return sorted(kelvinArray, key=getKelvin)


    def actionConfigListLifxDevices(self, filter="", valuesDict=None, typeId="", targetId=0):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        lifxArray = [('NONE', '- Select LIFX Device -')]
        for device in indigo.devices:
            if device.deviceTypeId == "lifxDevice" and device.id != targetId:  # Exclude own device
                lifxArray.append((device.id, device.name))
        def getLifxDeviceName(lifxDevItem):
            return lifxDevItem[1]
        return sorted(lifxArray, key=getLifxDeviceName)

    def actionConfigLifxDeviceSelected(self, valuesDict, typeId, actionId):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        self.generalLogger.debug(u"actionConfigLifxDeviceSelected [lifxLamp]= %s" % str(valuesDict["optionLifxDeviceList"]))
 
        lifxLampSelected = False  # Start with assuming no lamp selected in dialogue
        if "optionLifxDeviceList" in valuesDict:
            try:
                devId = int(valuesDict["optionLifxDeviceList"])
                try:
                    for dev in indigo.devices.iter("self"):  # CHECK FILTER FOR LIFX DEVICE ONLY!!!!
                        if dev.id == devId:
                            lifxLampSelected = True
                            break
                except:
                    pass
            except:
                pass

        if lifxLampSelected:
            valuesDict["lifxHue"]        = str(self.globals['lifx'][devId]['indigoHue'])
            valuesDict["lifxSaturation"] = str(self.globals['lifx'][devId]['indigoSaturation'])
            valuesDict["lifxBrightness"] = str(self.globals['lifx'][devId]['indigoBrightness'])
            valuesDict["lifxKelvin"]     = str(self.globals['lifx'][devId]['indigoKelvin'])

            hue = self.globals['lifx'][devId]['hsbkHue']
            saturation = self.globals['lifx'][devId]['hsbkSaturation']
            value = self.globals['lifx'][devId]['hsbkBrightness']
            kelvin = self.globals['lifx'][devId]['hsbkKelvin']

            if saturation != 0:
                valuesDict["lifxMode"] = 'Color'
                # Convert Color HSBK into RGBW
                valuesDict["colorLifxColorpicker"] = self.actionConfigSetColorSwatchRGB(hue, saturation, value)
                return valuesDict
            else:
                valuesDict["lifxMode"] = 'White'
                # Convert White HSBK into RGBW
                kelvin, kelvinDescription, kelvinRgb = self.actionConfigSetKelvinColorSwatchRGB(kelvin)
                valuesDict["lifxKelvinStatic"] = str(kelvinDescription)
                valuesDict["kelvinLifxColorpicker"] = kelvinRgb
                return valuesDict

        else:
            valuesDict["lifxHue"]        = "n/a"
            valuesDict["lifxSaturation"] = "n/a"
            valuesDict["lifxBrightness"] = "n/a"
            valuesDict["lifxKelvin"]     = "n/a"
        return valuesDict

    def modeStandardUpdated(self, valuesDict, typeId, actionId):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        if valuesDict["modeStandard"] == 'White':
            valuesDict, errorDict = self.kelvinStandardUpdated(valuesDict, typeId, actionId)
        else:
            valuesDict, errorDict = self.hueSaturationBrightnessStandardUpdated(valuesDict, typeId, actionId)
        return (valuesDict, errorDict)

    def modeWaveformUpdated(self, valuesDict, typeId, actionId):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        if valuesDict["modeWaveform"] == 'White':
            valuesDict, errorDict = self.kelvinWaveformUpdated(valuesDict, typeId, actionId)
        else:
            valuesDict, errorDict = self.hueSaturationBrightnessWaveformUpdated(valuesDict, typeId, actionId)
        return valuesDict



    def kelvinStandardUpdated(self, valuesDict, typeId, devId):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        errorDict = indigo.Dict()

        kelvin = 9000
        try:
            if valuesDict["kelvinStandard"] == 'CURRENT':
                kelvin = self.globals['lifx'][devId]['hsbkKelvin']
            else:
                kelvin = int(valuesDict["kelvinStandard"])            
        except:
            errorDict = indigo.Dict()
            errorDict["kelvinStandard"] = "Kelvin must be set between 2500 and 9000 (inclusive)"
            errorDict["showAlertText"] = "You must enter a valid Kelvin value for the LIFX device. It must be an integer between 2500 and 9000 (inclusive)"
            return (valuesDict, errorDict)

        kelvin, kelvinDescription, kelvinRgb = self.actionConfigSetKelvinColorSwatchRGB(kelvin)
        valuesDict["kelvinStandardColorpicker"] = kelvinRgb
        return (valuesDict, errorDict)

    def hueSaturationBrightnessStandardUpdated(self, valuesDict, typeId, devId):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        errorDict = indigo.Dict()

        if valuesDict["modeStandard"] == 'White':  # skip processing all fields if mode is 'White'
            return (valuesDict, errorDict)

        # Default color Swatch to black i.e. off / unset
        valuesDict["colorStandardColorpicker"] = self.actionConfigSetColorSwatchRGB(0.0, 65535.0, 0.0)

        brightnessStandard = valuesDict["brightnessStandard"].rstrip().lstrip()
        if brightnessStandard == '' or brightnessStandard == '-':
            brightness = self.globals['lifx'][devId]['hsbkBrightness']
        else:
            try:
                brightnessStandard = '%.1f' % float(brightnessStandard)
                if float(brightnessStandard) < 0.0 or float(brightnessStandard) > 100.0:
                    raise ValueError('Brightness must be set between 0.0 and 100.0 (inclusive)')
                brightness = float(float(brightnessStandard) * 65535.0 / 100.0)
            except:
                errorDict = indigo.Dict()
                errorDict["brightnessStandard"] = "Brightness must be set between 0.0 and 100.0 (inclusive) or '-' (dash) to not set value"
                errorDict["showAlertText"] = "You must enter a valid Brightness value for the LIFX device. It must be a value between 0.0 and 100.0 (inclusive) or '-' (dash) to leave an existing value unchanged"
                return (valuesDict, errorDict)

        hueStandard = valuesDict["hueStandard"].rstrip().lstrip()
        if hueStandard == '' or hueStandard == '-':
            hue = self.globals['lifx'][devId]['hsbkHue']
        else:
            try:
                hueStandard = '%.1f' % float(hueStandard)
                if float(hueStandard) < 0.0 or float(hueStandard) > 360.0:
                    raise ValueError('Hue must be set between 0.0 and 360.0 (inclusive)')
                hue = float(float(hueStandard) * 65535.0 / 360.0)
            except:
                errorDict = indigo.Dict()
                errorDict["hueStandard"] = "Hue must be set between 0.0 and 360.0 (inclusive) or '-' (dash) to not set value"
                errorDict["showAlertText"] = "You must enter a valid Hue value for the LIFX device. It must be a value between 0.0 and 360.0 (inclusive) or '-' (dash) to leave an existing value unchanged"
                return (valuesDict, errorDict)

        saturationStandard = valuesDict["saturationStandard"].rstrip().lstrip()
        if saturationStandard == '' or saturationStandard == '-':
            saturation = self.globals['lifx'][devId]['hsbkSaturation']
        else:
            try:
                saturationStandard = '%.1f' % float(saturationStandard)
                if float(saturationStandard) < 0.0 or float(saturationStandard) > 100.0:
                    raise ValueError('Saturation must be set between 0.0 and 100.0 (inclusive)')
                saturation = float(float(saturationStandard) * 65535.0 / 100.0)
            except:
                errorDict = indigo.Dict()
                errorDict["saturationStandard"] = "Saturation must be set between 0.0 and 100.0 (inclusive) or '-' (dash) to not set value"
                errorDict["showAlertText"] = "You must enter a valid Saturation value for the LIFX device. It must be a value between 0.0 and 100.0 (inclusive) or '-' (dash) to leave an existing value unchanged"
                return (valuesDict, errorDict)

        valuesDict["colorStandardColorpicker"] = self.actionConfigSetColorSwatchRGB(hue, saturation, brightness)
        return (valuesDict, errorDict)

    def kelvinWaveformUpdated(self, valuesDict, typeId, devId):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        errorDict = indigo.Dict()

        kelvin = 9000
        try:
            if valuesDict["kelvinWaveform"] == 'CURRENT':
                kelvin = self.globals['lifx'][devId]['hsbkKelvin']
            else:
                kelvin = int(valuesDict["kelvinWaveform"])            
        except:
            errorDict = indigo.Dict()
            errorDict["kelvinWaveform"] = "Kelvin must be set between 2500 and 9000 (inclusive)"
            errorDict["showAlertText"] = "You must enter a valid Kelvin value for the LIFX device. It must be an integer between 2500 and 9000 (inclusive)"
            return (valuesDict, errorDict)

        kelvin, kelvinDescription, kelvinRgb = self.actionConfigSetKelvinColorSwatchRGB(kelvin)
        valuesDict["kelvinWaveformColorpicker"] = kelvinRgb
        return (valuesDict, errorDict)


    def hueSaturationBrightnessWaveformUpdated(self, valuesDict, typeId, devId):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        errorDict = indigo.Dict()

        if valuesDict["modeWaveform"] == 'White':  # skip processing all fields if mode is 'White'
            return valuesDict

        # Default color Swatch to black i.e. off / unset
        valuesDict["colorWaveformColorpicker"] = self.actionConfigSetColorSwatchRGB(0.0, 65535.0, 0.0)

        brightnessWaveform = valuesDict["brightnessWaveform"].rstrip().lstrip()
        if brightnessWaveform == '' or brightnessWaveform == '-':
            brightness = self.globals['lifx'][devId]['hsbkBrightness']
        else:
            try:
                brightnessWaveform = '%.1f' % float(brightnessWaveform)
                if float(brightnessWaveform) < 0.0 or float(brightnessWaveform) > 100.0:
                    raise ValueError('Brightness must be set between 0.0 and 100.0 (inclusive)')
                brightness = float(float(brightnessWaveform) * 65535.0 / 100.0)
            except:
                errorDict = indigo.Dict()
                errorDict["brightnessWaveform"] = "Brightness must be set between 0.0 and 100.0 (inclusive) or '-' (dash) to not set value"
                errorDict["showAlertText"] = "You must enter a valid Brightness value for the LIFX device. It must be a value between 0.0 and 100.0 (inclusive) or '-' (dash) to leave an existing value unchanged"
                return (valuesDict, errorDict)

        hueWaveform = valuesDict["hueWaveform"].rstrip().lstrip()
        if hueWaveform == '' or hueWaveform == '-':
            hue = self.globals['lifx'][devId]['hsbkHue']
        else:
            try:
                hueWaveform = '%.1f' % float(hueWaveform)
                if float(hueWaveform) < 0.0 or float(hueWaveform) > 360.0:
                    raise ValueError('Hue must be set between 0.0 and 360.0 (inclusive)')
                hue = float(float(hueWaveform) * 65535.0 / 360.0)
            except:
                errorDict = indigo.Dict()
                errorDict["hueWaveform"] = "Hue must be set between 0.0 and 360.0 (inclusive) or '-' (dash) to not set value"
                errorDict["showAlertText"] = "You must enter a valid Hue value for the LIFX device. It must be a value between 0.0 and 360.0 (inclusive) or '-' (dash) to leave an existing value unchanged"
                return (valuesDict, errorDict)

        saturationWaveform = valuesDict["saturationWaveform"].rstrip().lstrip()
        if saturationWaveform == '' or saturationWaveform == '-':
            saturation = self.globals['lifx'][devId]['hsbkSaturation']
        else:
            try:
                saturationWaveform = '%.1f' % float(saturationWaveform)
                if float(saturationWaveform) < 0.0 or float(saturationWaveform) > 100.0:
                    raise ValueError('Saturation must be set between 0.0 and 100.0 (inclusive)')
                saturation = float(float(saturationWaveform) * 65535.0 / 100.0)
            except:
                errorDict = indigo.Dict()
                errorDict["saturationWaveform"] = "Saturation must be set between 0.0 and 100.0 (inclusive) or '-' (dash) to not set value"
                errorDict["showAlertText"] = "You must enter a valid Saturation value for the LIFX device. It must be a value between 0.0 and 100.0 (inclusive) or '-' (dash) to leave an existing value unchanged"
                return (valuesDict, errorDict)

        valuesDict["colorWaveformColorpicker"] = self.actionConfigSetColorSwatchRGB(hue, saturation, brightness)
        return (valuesDict, errorDict)


    def actionConfigSetColorSwatchRGB(self, hue, saturation, value):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        # hue, saturation and value are integers in the range 0 - 65535
        hue = float(hue) / 65535.0
        value = float(value) / 65535.0
        saturation = float(saturation) / 65535.0

        red, green, blue = colorsys.hsv_to_rgb(hue, saturation, value)

        red   = int(round(float(red * 255.0)))
        green = int(round(float(green * 255.0)))
        blue  = int(round(float(blue * 255.0)))

        rgb = [red,green,blue]
        rgbHexVals = []
        for byteLevel in rgb:
            if byteLevel < 0:
                byteLevel = 0
            elif byteLevel > 255:
                byteLevel = 255
            rgbHexVals.append("%02X" % byteLevel)
        return (' '.join(rgbHexVals))


    def actionConfigSetKelvinColorSwatchRGB(self, argKelvin):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        # Set ColorSwatch to nearest match to Kelvin value as shown in the iOS LIFX App
        kelvin = min(LIFX_KELVINS, key=lambda x:abs(x - argKelvin))
        rgb, kelvinDescription = LIFX_KELVINS[kelvin]
        # self.generalLogger.info(u"KELVIN COLOR SWATCH; argKelvin = %s, Kelvin = %s, LIFX_KELVINS[kelvin] = %s, RGB = %s" % (argKelvin, kelvin, LIFX_KELVINS[kelvin], rgb))
        rgbHexVals = []
        for byteLevel in rgb:
            if byteLevel < 0:
                byteLevel = 0
            elif byteLevel > 255:
                byteLevel = 255
            rgbHexVals.append("%02X" % byteLevel)
        return (kelvin, kelvinDescription, (' '.join(rgbHexVals)))


    def actionConfigPresetSelected(self, valuesDict, typeId, actionId):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        self.generalLogger.debug(u"actionConfigPresetSelected [Preset]= %s" % str(valuesDict["optionPresetList"]))
 
        valuesDict["actionTypePreset"] = 'No Preset Selected'
        presetSelected = False  # Start with assuming no preset selected in dialogue
        if "optionPresetList" in valuesDict:
            try:
                variableId = int(valuesDict["optionPresetList"])
                try:
                    if indigo.variables[variableId].folderId == self.globals['folders']['VariablesId']:
                        selectedPresetName = indigo.variables[variableId].name
                        selectedPresetValue = indigo.variables[variableId].value
                        presetSelected = True
                except:
                    pass
            except:
                pass

        if not presetSelected:
            valuesDict["presetSelected"] = 'NO'  # Hidden field for contriolling fields displayed
        else:
            valuesDict["presetSelected"] = 'YES'  # Hidden field for contriolling fields displayed


            actionType, mode, turnOnIfOff, hue, saturation, brightness, kelvin, duration, transient, period, cycles, dutyCycle, waveform = self.decodePreset(selectedPresetValue)

            valuesDict["actionTypePreset"] = actionType
            if actionType == 'Standard':

                if turnOnIfOff  == '0':
                    valuesDict["presetTurnOnIfOffStandardStatic"] = 'No'
                else:
                    valuesDict["presetTurnOnIfOffStandardStatic"] = 'Yes'
                if brightness != '':
                    valuesDict["presetBrightnessStandard"] = brightness
                else:
                    brightness = '100.0' # Default to 100% saturation (for Color Swatch)
                if mode == 'White':
                    if kelvin != '':
                        kelvin, kelvinDescription, kelvinRgb = self.actionConfigSetKelvinColorSwatchRGB(int(kelvin))
                        valuesDict["presetKelvinStandardStatic"] = str(kelvinDescription)
                        valuesDict["kelvinPresetColorpicker"] = kelvinRgb
                elif mode == 'Color':
                    valuesDict["actionTypePreset"] = actionType
                    valuesDict["presetModeStandard"] = mode
                    if hue != '':
                        valuesDict["presetHueStandard"] = hue
                    else:
                        hue = '360.0'  # Default to Red (for Color Swatch)
                    if saturation != '':
                        valuesDict["presetSaturationStandard"] = saturation
                    else:
                        saturation = '100.0' # Default to 100% saturation (for Color Swatch)
                    hue = float(float(hue) * 65535.0 / 360.0)
                    saturation = float(float(saturation) * 65535.0 / 100.0)
                    brightness = float(float(brightness) * 65535.0 / 100.0)
                    valuesDict["colorPresetColorpicker"] = self.actionConfigSetColorSwatchRGB(hue, saturation, brightness)
                else:
                    valuesDict["presetModeStandard"] = 'Preset has invalid mode'
                    return valuesDict  # Error: mode must be 'White' or 'Color'


                if duration != '':
                    valuesDict["presetDurationStandard"] = duration
                valuesDict["presetModeStandard"] = mode
            elif actionType == 'Waveform':
                if brightness != '':
                    valuesDict["presetBrightnessWaveform"] = brightness
                else:
                    brightness = '100.0' # Default to 100% saturation (for Color Swatch)
                if mode == 'White':
                    if kelvin != '':
                        kelvin, kelvinDescription, kelvinRgb = self.actionConfigSetKelvinColorSwatchRGB(int(kelvin))
                        valuesDict["presetKelvinWaveformStatic"] = str(kelvinDescription)
                        valuesDict["kelvinPresetWaveformColorpicker"] = kelvinRgb
                elif mode == 'Color':
                    if hue != '':
                        valuesDict["presetHueWaveform"] = hue
                    else:
                        hue = '360.0'  # Default to Red (for Color Swatch)
                    if saturation != '':
                        valuesDict["presetSaturationWaveform"] = saturation
                    else:
                        saturation = '100.0' # Default to 100% saturation (for Color Swatch)
                    hue = float(float(hue) * 65535.0 / 360.0)
                    saturation = float(float(saturation) * 65535.0 / 100.0)
                    brightness = float(float(brightness) * 65535.0 / 100.0)
                    valuesDict["colorPresetWaveformColorpicker"] = self.actionConfigSetColorSwatchRGB(hue, saturation, brightness)
                else:
                    valuesDict["presetModeWaveform"] = 'Preset has invalid mode'
                    return valuesDict  # Error: mode must be 'White' or 'Color'

                if transient != '':
                    valuesDict["presetTransientWaveform"] = transient
                if period != '':
                    valuesDict["presetPeriodWaveform"] = period
                if cycles != '':
                    valuesDict["presetCyclesWaveform"] = cycles
                if dutyCycle != '':
                    valuesDict["presetDutyCycleWaveform"] = dutyCycle
                if waveform != '':
                    valuesDict["presetTypeWaveform"] = waveform
                valuesDict["presetModeWaveform"] = mode
            else:
                valuesDict["presetModeStandard"] = 'Preset has invalid LIFX Action'
                valuesDict["presetModeWaveform"] = 'Preset has invalid LIFX Action'
                valuesDict["actionTypePreset"] = 'Preset has invalid LIFX Action'

        return valuesDict


    def actionConfigOptionSelected(self, valuesDict, typeId, actionId):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        self.generalLogger.debug(u"actionConfigOptionSelected")

        # Turn Off Save/Update Preset Dialogue
        valuesDict["resultPreset"] = "resultNa"
        valuesDict["newPresetName"] = ""
        valuesDict["selectedPresetOption"] = "NONE"

        valuesDict["optionLifxDeviceList"] = "NONE"
        valuesDict["lifxMode"] = "NONE"
        valuesDict["presetSelected"] = "NO"

        return valuesDict


    def actionConfigApplyLifxOptionValues(self, valuesDict, typeId, actionId):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        self.generalLogger.debug(u"actionConfigPresetApplyOptionValues: typeId[%s], actionId[%s], ValuesDict:\n%s" % (typeId, actionId, valuesDict))

        if valuesDict ["actionType"] == 'Standard':
            valuesDict["modeStandard"] = valuesDict["lifxMode"]
            valuesDict["brightnessStandard"] = valuesDict["lifxBrightness"]
            if valuesDict["lifxMode"] == 'Color':
                valuesDict["hueStandard"] = valuesDict["lifxHue"]
                valuesDict["saturationStandard"] = valuesDict["lifxSaturation"]
                hue = float(valuesDict["lifxHue"]) * 65535.0 / 360.0
                saturation = float(valuesDict["lifxSaturation"]) * 65535.0 / 100.0
                brightness = float(valuesDict["lifxBrightness"]) * 65535.0 / 100.0
                # Convert Color HSBK into RGBW
                valuesDict["colorStandardColorpicker"] = self.actionConfigSetColorSwatchRGB(hue, saturation, brightness)
                return valuesDict
            else:
                kelvin = float(valuesDict["lifxKelvinStatic"][0:4])  # lifxKelvinStatic is a Kelvin description filed e.g. '3200K Neutral Warm'
                # Convert White HSBK into RGBW
                kelvin, kelvinDescription, kelvinRgb = self.actionConfigSetKelvinColorSwatchRGB(kelvin)
                valuesDict["kelvinStandard"] = kelvin
                valuesDict["kelvinStandardColorpicker"] = kelvinRgb
                return valuesDict
        else:
            valuesDict["modeWaveform"] = valuesDict["lifxMode"]
            valuesDict["brightnessWaveform"] = valuesDict["lifxBrightness"]
            if valuesDict["lifxMode"] == 'Color':
                valuesDict["hueWaveform"] = valuesDict["lifxHue"]
                valuesDict["saturationWaveform"] = valuesDict["lifxSaturation"]
                hue = float(valuesDict["lifxHue"]) * 65535.0 / 360.0
                saturation = float(valuesDict["lifxSaturation"]) * 65535.0 / 100.0
                brightness = float(valuesDict["lifxBrightness"]) * 65535.0 / 100.0
                # Convert Color HSBK into RGBW
                valuesDict["colorWaveformColorpicker"] = self.actionConfigSetColorSwatchRGB(hue, saturation, brightness)
                return valuesDict
            else:
                kelvin = float(valuesDict["lifxKelvinStatic"][0:4])  # lifxKelvinStatic is a Kelvin description filed e.g. '3200K Neutral Warm'
                # Convert White HSBK into RGBW
                kelvin, kelvinDescription, kelvinRgb = self.actionConfigSetKelvinColorSwatchRGB(kelvin)
                valuesDict["kelvinWaveform"] = kelvin
                valuesDict["kelvinWaveformColorpicker"] = kelvinRgb
                return valuesDict


    def actionConfigApplyStandardPresetOptionValues(self, valuesDict, typeId, actionId):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        self.generalLogger.debug(u"actionConfigApplyStandardPresetOptionValues: typeId[%s], actionId[%s], ValuesDict:\n%s" % (typeId, actionId, valuesDict))

        valuesDict["actionType"] = 'Standard'
        if valuesDict["presetBrightnessStandard"] != '':
            valuesDict["brightnessStandard"] = valuesDict["presetBrightnessStandard"]
        if valuesDict["presetModeStandard"] == 'White':
            valuesDict["modeStandard"] = 'White'
            if valuesDict["presetKelvinStandardStatic"] != '':
                valuesDict["kelvinStandard"] = valuesDict["presetKelvinStandardStatic"][0:4]

            valuesDict, errorDict = self.kelvinStandardUpdated(valuesDict, typeId, actionId)

        elif valuesDict["presetModeStandard"] == 'Color':
            valuesDict["modeStandard"] = 'Color'
            if valuesDict["presetHueStandard"] != '':
                valuesDict["hueStandard"] = valuesDict["presetHueStandard"]
            if valuesDict["presetSaturationStandard"] != '':
                valuesDict["saturationStandard"] = valuesDict["presetSaturationStandard"]

            valuesDict, errorDict = self.hueSaturationBrightnessStandardUpdated(valuesDict, typeId, actionId)

            if valuesDict["presetDurationStandard"] != '':
                valuesDict["durationStandard"] = valuesDict["presetDurationStandard"]


        self.generalLogger.debug(u"actionConfigApplyStandardPresetOptionValues: Returned ValuesDict:\n%s" % (valuesDict))

        return (valuesDict, errorDict)


    def actionConfigApplyWaveformPresetOptionValues(self, valuesDict, typeId, actionId):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        self.generalLogger.debug(u"actionConfigApplyWaveformPresetOptionValues: typeId[%s], actionId[%s], ValuesDict:\n%s" % (typeId, actionId, valuesDict))

        valuesDict["actionType"] = 'Waveform'
        if valuesDict["presetBrightnessWaveform"] != '':
            valuesDict["brightnessWaveform"] = valuesDict["presetBrightnessWaveform"]
        if valuesDict["presetModeWaveform"] == 'White':
            valuesDict["modeWaveform"] = 'White'
            if valuesDict["presetKelvinWaveformStatic"] != '':
                valuesDict["kelvinWaveform"] = valuesDict["presetKelvinWaveformStatic"][0:4]

            valuesDict, errorDict = self.kelvinWaveformUpdated(valuesDict, typeId, actionId)

        if valuesDict["presetModeWaveform"] == 'Color':
            valuesDict["modeWaveform"] = 'Color'
            if valuesDict["presetHueWaveform"] != '':
                valuesDict["hueWaveform"] = valuesDict["presetHueWaveform"]
            if valuesDict["presetSaturationWaveform"] != '':
                valuesDict["saturationWaveform"] = valuesDict["presetSaturationWaveform"]

            valuesDict, errorDict = self.hueSaturationBrightnessWaveformUpdated(valuesDict, typeId, actionId)

        if valuesDict["presetTransientWaveform"] != '':
            valuesDict["transientWaveform"] = valuesDict["presetTransientWaveform"]
        if valuesDict["presetPeriodWaveform"] != '':
            valuesDict["periodWaveform"] = valuesDict["presetPeriodWaveform"]
        if valuesDict["presetCyclesWaveform"] != '':
            valuesDict["cyclesWaveform"] = valuesDict["presetCyclesWaveform"]
        if valuesDict["presetDutyCycleWaveform"] != '':
            valuesDict["dutyCycleWaveform"] = valuesDict["presetDutyCycleWaveform"]
        if valuesDict["presetTypeWaveform"] != '':
            valuesDict["typeWaveform"] = valuesDict["presetTypeWaveform"]

        self.generalLogger.debug(u"actionConfigApplyWaveformPresetOptionValues: Returned ValuesDict:\n%s" % (valuesDict))

        return valuesDict


    def actionConfigPresetActionSelected(self, valuesDict, typeId, actionId):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        self.generalLogger.debug(u"actionConfigPresetActionSelected: %s" % (valuesDict))


        valuesDict["resultPreset"] = "resultNa"
        valuesDict["newPresetName"] = ""

        return valuesDict


    def actionConfigPresetSaveButtonPressed(self, valuesDict, typeId, actionId):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        valuesDict["resultPreset"] = "resultNa"

        self.generalLogger.debug(u"actionConfigPresetSaveButtonPressed: typeId[%s], actionId[%s]" % (typeId, actionId))

        self.validation = self.validateActionConfigUi(valuesDict, "applyPreset", actionId)

        self.generalLogger.debug(u"self.validation: typeId[%s], actionId[%s]" % (type(self.validation), self.validation))

        valuesDict = self.validation[1]  # valuesDict

        if self.validation[0]:
            preset = self.buildPresetVariable(valuesDict)  # Build Preset Variable
            if len(preset) > 0:
                try:
                    if not re.match(r'\w+$', valuesDict["newPresetName"]):
                        raise ValueError("newPresetName must be a alphanumeric or '_'")
                    indigo.variable.create(valuesDict["newPresetName"], value=preset,  folder=self.globals['folders']['VariablesId'])
                    valuesDict["resultPreset"] = "resultSaveOk"
                except:
                    valuesDict["resultPreset"] = "resultSaveError"
                    errorDict = indigo.Dict()
                    errorDict["newPresetName"] = "Unable to create preset variable"
                    errorDict["showAlertText"] = "Unable to create preset variable. Check that the preset name format is valid (alphanumeric and underscore only) and that the preset variable doesn't already exist"
                    return (valuesDict, errorDict)
        else:
            valuesDict["resultPreset"] = "resultInvalidValue"
            return (valuesDict, self.validation[2]) 

        return valuesDict


    def actionConfigPresetUpdateButtonPressed(self, valuesDict, typeId, actionId):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        self.generalLogger.debug(u"actionConfigPresetUpdateButtonPressed: typeId[%s], actionId[%s]" % (typeId, actionId))

        valuesDict["resultPreset"] = "resultNa"

        self.validation = self.validateActionConfigUi(valuesDict, "setPreset", actionId)

        self.generalLogger.debug(u"self.validation: typeId[%s], actionId[%s]" % (type(self.validation), self.validation))

        valuesDict = self.validation[1]  # valuesDict

        if self.validation[0]:
            preset = self.buildPresetVariable(valuesDict)  # Build Preset Variable
            if len(preset) > 0:
                try:
                    presetVariableId = int(valuesDict["updatePresetList"])
                    presetVariableToUpdate =  indigo.variables[presetVariableId]
                    presetVariableToUpdate.value = preset
                    presetVariableToUpdate.replaceOnServer()
                    valuesDict["resultPreset"] = "resultUpdateOk"
                except:
                    valuesDict["resultPreset"] = "resultUpdateError"
                    errorDict = indigo.Dict()
                    errorDict["updatePresetList"] = "Unable to update preset variable"
                    errorDict["showAlertText"] = "Unable to update preset variable"
                    return (valuesDict, errorDict)
        else:
            self.generalLogger.debug(u"self.validation: FALSE")
            valuesDict["resultPreset"] = "resultInvalidValue"
            return (valuesDict, self.validation[2]) 

        return valuesDict


    def buildPresetVariable(self, valuesDict):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        preset = ""

        if valuesDict["actionType"] == 'Standard':
            if bool(valuesDict["turnOnIfOffStandard"]):
                turnOnIfOffStandard = '1'
            else:
                turnOnIfOffStandard = '0'
            preset = preset + ",ON=" + turnOnIfOffStandard
            if valuesDict["modeStandard"] == 'White':
                if valuesDict["kelvinStandard"].rstrip() != '':
                    preset = preset + ",K=" + valuesDict["kelvinStandard"].rstrip()
            elif valuesDict["modeStandard"] == 'Color':
                if valuesDict["hueStandard"].rstrip() != '':
                    preset = preset + ",H=" + valuesDict["hueStandard"].rstrip()
                if valuesDict["saturationStandard"].rstrip() != '':
                    preset = preset + ",S=" + valuesDict["saturationStandard"].rstrip()
            if valuesDict["brightnessStandard"].rstrip() != '':
                preset = preset + ",B=" + valuesDict["brightnessStandard"].rstrip()
        elif  valuesDict["actionType"] == 'Waveform':
            if valuesDict["modeWaveform"] == 'White':
                if valuesDict["kelvinWaveform"].rstrip() != '':
                    preset = preset + ",K=" + valuesDict["kelvinWaveform"].rstrip()
            elif valuesDict["modeWaveform"] == 'Color':
                if valuesDict["hueWaveform"].rstrip() != '':
                    preset = preset + ",H=" + valuesDict["hueWaveform"].rstrip()
                if valuesDict["saturationWaveform"].rstrip() != '':
                    preset = preset + ",S=" + valuesDict["saturationWaveform"].rstrip()
            if valuesDict["brightnessWaveform"].rstrip() != '':
                preset = preset + ",B=" + valuesDict["brightnessWaveform"].rstrip()
            transientWaveform = '1' if bool(valuesDict["transientWaveform"]) else '0'   
            preset = preset + ",T=" + transientWaveform
            if valuesDict["periodWaveform"].rstrip() != '':
                preset = preset + ",P=" + valuesDict["periodWaveform"].rstrip()
            if valuesDict["cyclesWaveform"].rstrip() != '':
                preset = preset + ",C=" + valuesDict["cyclesWaveform"].rstrip()
            if valuesDict["dutyCycleWaveform"].rstrip() != '':
                preset = preset + ",DC=" + valuesDict["dutyCycleWaveform"].rstrip()
            if valuesDict["typeWaveform"].rstrip() != '':
                preset = preset + ",W=" + valuesDict["typeWaveform"].rstrip()

        if len(preset) > 0:
            if valuesDict["actionType"] == 'Waveform':
                prefix = 'AT=W,M=W,' if valuesDict["modeWaveform"] == 'White' else 'AT=W,M=C,'
            else:
                prefix = 'AT=S,M=W,' if valuesDict["modeStandard"] == 'White' else 'AT=S,M=C,'
            preset = prefix + preset[1:]  # Remove leading ',' from preset

        return preset


    def getMenuActionConfigUiValues(self, menuId):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        valuesDict = indigo.Dict()
        errorMsgDict = indigo.Dict() 

        self.generalLogger.debug(u"QWERTY QWERTY = %s" % (menuId))

        # if menuId == "yourMenuItemId":
        #  valuesDict["someFieldId"] = someDefaultValue
        return (valuesDict, errorMsgDict)


    def actionControlUniversal(self, action, dev):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        ###### STATUS REQUEST ######
        if action.deviceAction == indigo.kUniversalAction.RequestStatus:
            self._processStatus(action, dev)


    def _processStatus(self, pluginAction, dev):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_STATUS_MEDIUM, 'STATUS', dev.id, None])
        self.generalLogger.info(u"sent \"%s\" %s" % (dev.name, "status request"))


    def actionControlDevice(self, action, dev):
        self.methodTracer.threaddebug(u"CLASS: Plugin")
        if dev.states['connected'] == False or self.globals['lifx'][dev.id]['connected'] == False:
            self.generalLogger.info(u"Unable to process  \"%s\" for \"%s\" as device not connected" % (action.deviceAction, dev.name))
            return

        ###### TURN ON ######
        if action.deviceAction ==indigo.kDeviceAction.TurnOn:
            self._processTurnOn(action, dev)

        ###### TURN OFF ######
        elif action.deviceAction ==indigo.kDeviceAction.TurnOff:
            self._processTurnOff(action, dev)

        ###### TOGGLE ######
        elif action.deviceAction ==indigo.kDeviceAction.Toggle:
            self._processTurnOnOffToggle(action, dev)

        ###### SET BRIGHTNESS ######
        elif action.deviceAction ==indigo.kDeviceAction.SetBrightness:
            newBrightness = action.actionValue  #  action.actionValue contains brightness value (0 - 100)
            self._processBrightnessSet(action, dev, newBrightness)

        ###### BRIGHTEN BY ######
        elif action.deviceAction ==indigo.kDeviceAction.BrightenBy:
            if not dev.onState:
                self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_COMMAND, 'IMMEDIATE-ON', dev.id, None])

            if dev.brightness < 100:
                brightenBy = action.actionValue #  action.actionValue contains brightness increase value
                newBrightness = dev.brightness + brightenBy
                if newBrightness > 100:
                    newBrightness = 100
                self.generalLogger.info(u"Brightening %s by %s to %s" % (dev.name, brightenBy, newBrightness))
                self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_COMMAND, 'BRIGHTEN', dev.id, [newBrightness]])
                dev.updateStateOnServer("brightnessLevel", newBrightness)
            else:
                self.generalLogger.info(u"Ignoring Brighten request for %s as device is at full brightness" % (dev.name))

        ###### DIM BY ######
        elif action.deviceAction ==indigo.kDeviceAction.DimBy:
            if dev.onState and dev.brightness > 0: 
                dimBy = action.actionValue #  action.actionValue contains brightness decrease value
                newBrightness = dev.brightness - dimBy
                if newBrightness < 0:
                    newBrightness = 0
                    dev.updateStateOnServer("brightnessLevel", newBrightness)
                    self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_COMMAND, 'OFF', dev.id, None])
                    self.generalLogger.info(u"sent \"%s\" %s" % (dev.name, 'dim to off'))
                else:
                    self.generalLogger.info(u"Dimming %s by %s to %s" % (dev.name, dimBy, newBrightness))
                    self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_COMMAND, 'DIM', dev.id, [newBrightness]])
                    dev.updateStateOnServer("brightnessLevel", newBrightness)
            else:
                    self.generalLogger.info(u"Ignoring Dim request for %s as device is Off" % (dev.name))

        ###### SET COLOR LEVELS ######
        elif action.deviceAction ==indigo.kDeviceAction.SetColorLevels:
            self.generalLogger.debug(u"SET COLOR LEVELS = \"%s\" %s" % (dev.name, action))
            self._processSetColorLevels(action, dev)

    def brightenDimByTimer(self, pluginAction, dev):  # Dev is a LIFX Lamp

        pass



    def _processTurnOn(self, pluginAction, dev, actionUi='on'):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        self.generalLogger.debug(u"LIFX 'processTurnOn' [%s]" % (self.globals['lifx'][dev.id]['ipAddress'])) 

        self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_COMMAND, 'ON', dev.id, None])

        duration = self.globals['lifx'][dev.id]['durationOn']
        self.generalLogger.info(u"sent \"%s\" %s with duration of %s seconds" % (dev.name, actionUi, duration))

    def _processTurnOff(self, pluginAction, dev, actionUi='off'):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        self.generalLogger.debug(u"LIFX 'processTurnOff' [%s]" % (self.globals['lifx'][dev.id]['ipAddress'])) 

        self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_COMMAND, 'OFF', dev.id, None])

        duration = self.globals['lifx'][dev.id]['durationOff']
        self.generalLogger.info(u"sent \"%s\" %s with duration of %s seconds" % (dev.name, actionUi, duration))

    def _processTurnOnOffToggle(self, pluginAction, dev):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        self.generalLogger.debug(u"LIFX 'processTurnOnOffToggle' [%s]" % (self.globals['lifx'][dev.id]['ipAddress'])) 

        onStateRequested = not dev.onState
        if onStateRequested:
            actionUi = "toggle from 'off' to 'on'"
            self._processTurnOn(pluginAction, dev, actionUi)
        else:
            actionUi = "toggle from 'on' to 'off'"
            self._processTurnOff(pluginAction, dev, actionUi)

    def _processBrightnessSet(self, pluginAction, dev, newBrightness):  # Dev is a LIFX Lamp
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        duration = self.globals['lifx'][dev.id]['durationDimBrighten']
        if newBrightness > 0:
            if newBrightness > dev.brightness:
                actionUi = 'brighten'
            else:
                actionUi = 'dim'  
            self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_COMMAND, 'BRIGHTNESS', dev.id, [newBrightness]])
            self.generalLogger.info(u"sent \"%s\" %s to %s with duration of %s seconds" % (dev.name, actionUi, newBrightness, duration))
        else:
            self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_COMMAND, 'OFF', dev.id, None])
            self.generalLogger.info(u"sent \"%s\" %s with duration of %s seconds" % (dev.name, 'dim to off', duration))


    def _processSetColorLevels(self, action, dev):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        try:
            self.generalLogger.debug(u'processSetColorLevels ACTION:\n%s ' % action)

                
            duration = str(self.globals['lifx'][dev.id]['durationColorWhite'])

            # Determine Color / White Mode
            colorMode = False

            # First check if color is being set by the action Set RGBW levels
            if 'redLevel' in action.actionValue and 'greenLevel' in action.actionValue and 'blueLevel' in action.actionValue:
                if float(action.actionValue['redLevel']) > 0.0 or float(action.actionValue['greenLevel']) > 0.0 or float(action.actionValue['blueLevel']) > 0.0:
                    colorMode = True

            if (not colorMode) and (('whiteLevel' in action.actionValue) or ('whiteTemperature' in action.actionValue)):
                # If either of 'whiteLevel' or 'whiteTemperature' are altered - assume mode is White

                whiteLevel = float(dev.states['whiteLevel'])
                whiteTemperature =  int(dev.states['whiteTemperature'])

                if 'whiteLevel' in action.actionValue:
                    whiteLevel = float(action.actionValue['whiteLevel'])
                    
                if 'whiteTemperature' in action.actionValue:
                    whiteTemperature = int(action.actionValue['whiteTemperature'])
                    if whiteTemperature < 2500:
                        whiteTemperature = 2500
                    elif whiteTemperature > 9000:
                        whiteTemperature = 9000

                kelvin = min(LIFX_KELVINS, key=lambda x:abs(x - whiteTemperature))
                rgb, kelvinDescription = LIFX_KELVINS[kelvin]

                self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_COMMAND, 'WHITE', dev.id, [whiteLevel, kelvin]])

                self.generalLogger.info(u"sent \"%s\" set White Level to \"%s\" and White Temperature to \"%s\" with duration of %s seconds" % (dev.name, int(whiteLevel), kelvinDescription, duration))

            else:
                # As neither of 'whiteTemperature' or 'whiteTemperature' are set - assume mode is Colour

                props = dev.pluginProps
                if ("SupportsRGB" in props) and props["SupportsRGB"]:  # Check device supports color
                    redLevel = float(dev.states['redLevel'])
                    greenLevel = float(dev.states['greenLevel'])
                    blueLevel = float(dev.states['blueLevel'])
 
                    if 'redLevel' in action.actionValue:
                        redLevel = float(action.actionValue['redLevel'])
                    if 'greenLevel' in action.actionValue:
                        greenLevel = float(action.actionValue['greenLevel'])
                    if 'blueLevel' in action.actionValue:
                        blueLevel = float(action.actionValue['blueLevel'])

                    self.generalLogger.debug(u"sent \"%s\" Red = %s[%s], Green = %s[%s], Blue = %s[%s]" % (dev.name, redLevel, int(redLevel * 2.56), greenLevel, int(greenLevel * 2.56), blueLevel, int(blueLevel * 2.56)))

                    # Convert Indigo values for rGB (0-100) to colorSys values (0.0-1.0)
                    red = float(redLevel / 100.0)         # e.g. 100.0/100.0 = 1.0
                    green = float(greenLevel / 100.0)     # e.g. 70.0/100.0 = 0.7
                    blue = float(blueLevel / 100.0)       # e.g. 40.0/100.0 = 0.4

                    hsv_hue, hsv_saturation, hsv_brightness = colorsys.rgb_to_hsv(red, green, blue)

                    # Convert colorsys values for HLS (0.0-1.0) to H (0-360), L aka B (0.0 -100.0) and S (0.0 -100.0)
                    hue = int(hsv_hue * 65535.0)
                    brightness = int(hsv_brightness * 65535.0)
                    saturation = int(hsv_saturation * 65535.0)

                    self.generalLogger.debug(u"ColorSys: \"%s\" R, G, B: %s, %s, %s = H: %s[%s], S: %s[%s], B: %s[%s]" % (dev.name, red, green, blue, hue, hsv_hue, saturation, hsv_saturation, brightness, hsv_brightness))

                    self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_COMMAND, 'COLOR', dev.id, [hue, saturation, brightness]])

                    hueUi = '%s' % int(((hue  * 360.0) / 65535.0))
                    saturationUi = '%s' % int(((saturation  * 100.0) / 65535.0))
                    brightnessUi = '%s' % int(((brightness  * 100.0) / 65535.0))

                    self.generalLogger.info(u"sent \"%s\" set Color Level to hue \"%s\", saturation \"%s\" and brightness \"%s\" with duration of %s seconds" % (dev.name, hueUi, saturationUi, brightnessUi, duration))
                else:
                    self.generalLogger.info(u"Failed to send \"%s\" set Color Level as device does not support color." % (dev.name))


        except StandardError, e:
            self.generalLogger.error(u"StandardError detected during processSetColorLevels. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))


    def turnOnInfrared(self, pluginAction, dev):  # Dev is a LIFX Lamp
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        if dev is None:
            self.generalLogger.info(u"No LIFX device selected in Action - request to Turn On infrared ignored")
            return

        props = dev.pluginProps
        if ("SupportsInfrared" not in props) or (not props["SupportsInfrared"]):
            self.generalLogger.info(u"LIFX device \"%s\" does not support infrared - request to Turn On infrared ignored" % (dev.name))
            return
            
        self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_COMMAND, 'INFRARED_ON', dev.id, None])
        self.generalLogger.info(u"sent \"%s\" turn on infrared" % (dev.name))
           

    def turnOffInfrared(self, pluginAction, dev):  # Dev is a LIFX Lamp
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        if dev is None:
            self.generalLogger.info(u"No LIFX device selected in Action - request to Turn Off infrared ignored")
            return

        props = dev.pluginProps
        if ("SupportsInfrared" not in props) or (not props["SupportsInfrared"]):
            self.generalLogger.info(u"LIFX device \"%s\" does not support infrared - request to Turn Off infrared ignored" % (dev.name))
            return
            
        self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_COMMAND, 'INFRARED_OFF', dev.id, None])
        self.generalLogger.info(u"sent \"%s\" turn off infrared" % (dev.name))


    def setInfraredBrightness(self, pluginAction, dev):  # Dev is a LIFX Lamp
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        if dev is None:
            self.generalLogger.info(u"No LIFX device selected in Action - request to set infrared brightness ignored")
            return

        props = dev.pluginProps
        if ("SupportsInfrared" not in props) or (not props["SupportsInfrared"]):
            self.generalLogger.info(u"LIFX device \"%s\" does not support infrared - request to set infrared brightness ignored" % (dev.name))
            return

        try:
            infraredBrightness = float(pluginAction.props.get('infraredBrightness', 100.0))
        except:
            errorInfraredBrightness = pluginAction.props.get('infraredBrightness', 'NOT SPECIFIED')
            self.generalLogger.error(u"Failed to set infrared maximum brightness for \"%s\" value '%s' is invalid." % (dev.name, errorInfraredBrightness))
            return

        self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_COMMAND, 'INFRARED_SET', dev.id, [infraredBrightness]])

        infraredBrightnessUi = '%s' % int(float(infraredBrightness))
        self.generalLogger.info(u"sent \"%s\" set infrared maximum brightness to %s" % (dev.name, infraredBrightnessUi))

    def setColorWhite(self, pluginAction, dev):  # Dev is a LIFX Lamp
        self.methodTracer.threaddebug(u"CLASS: Plugin")
            
        self.generalLogger.debug(u"LIFX 'setColorWhite' [%s] - PluginAction Props =\n%s" % (self.globals['lifx'][dev.id]['ipAddress'], pluginAction.props)) 

        actionType = str(pluginAction.props.get('actionType', 'INVALID'))  # 'Standard' or 'Waveform'

        if dev.states['connected'] == False or self.globals['lifx'][dev.id]['connected'] == False:
            self.generalLogger.info(u"Unable to apply action \"Set Color/White - %s\" to \"%s\" as device not connected" % (actionType, dev.name))
            return

        if (actionType != 'Standard') and (actionType != 'Waveform'):
            self.generalLogger.error(u"LIFX 'setColorWhite' for %s - Invalid message type '%s'" % (dev.name, actionType))
            return

        if actionType == 'Standard':
            hue = '-'  # Denotes value not set
            saturation = '-'
            brightness = '-'
            kelvin = '-'
            mode = str(pluginAction.props.get('modeStandard','White'))  # 'Color' or 'White' (Default)
            if mode == 'White':
                try:
                    kelvin = str(pluginAction.props.get('kelvinStandard', '-'))  # Denotes value not set
                except:
                    kelvin = '-'
            elif mode == 'Color':
                try:
                    hue = str(pluginAction.props.get('hueStandard', '-'))
                    saturation = pluginAction.props.get('saturationStandard', '-')  # Denotes value not set
                except:
                    hue = '-'
                    saturation = '-'
            else:
                self.generalLogger.error(u"LIFX 'setColorWhite' for %s - Invalid mode '%s'" % (dev.name, mode))
                return

            try:
                brightness = str(pluginAction.props.get('brightnessStandard', '-'))  # Denotes value not set
            except:
                brightness = '-'
            try:
                duration = str(pluginAction.props.get('durationStandard', '-'))
            except:
                duration = '-'
            try:
                turnOnIfOff = bool(pluginAction.props.get('turnOnIfOff', True))  # Default 'Turn On if Off' to True if missing
            except:
                turnOnIfOff = True  # Default 'Turn On if Off' to True if error


            self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_COMMAND, 'STANDARD', dev.id, [turnOnIfOff, mode, hue, saturation, brightness, kelvin, duration]])

            if mode == 'White':
                if kelvin == '-':
                    kelvinUi = 'existing'
                else:
                    kelvinUi = '%s' % int(kelvin)
                if brightness == '-':
                    brightnessUi = 'existing'
                else:
                    brightnessUi = '%s' % int(float(brightness))
                if duration == '-':
                    durationUi = 'default'
                else:
                    durationUi = str(duration)
                self.generalLogger.info(u"sent \"%s\" set White Level to \"%s\" and White Temperature to \"%s\" with duration of %s seconds" % (dev.name, int(brightnessUi), int(kelvinUi), durationUi))
            else:
                if hue == '-':
                    hueUi = 'existing'
                else:
                    hueUi = '%s' % int(float(hue))
                if saturation == '-':
                    saturationUi = 'existing'
                else:
                    saturationUi = '%s' % int(float(saturation))
                if brightness == '-':
                    brightnessUi = 'existing'
                else:
                    brightnessUi = '%s' % int(float(brightness))
                if duration == '-':
                    durationUi = 'default'
                else:
                    durationUi = str(duration)

                self.generalLogger.info(u"sent \"%s\" set Color Level to hue \"%s\", saturation \"%s\" and brightness \"%s\" with duration of %s seconds" % (dev.name, hueUi, saturationUi, brightnessUi, durationUi))


            return


        # Waveform    

        hue = 0  # Defaulted to avoid error (although not needed)
        saturation = 100  # Defaulted to avoid error (although not needed)
        kelvin = 0  # Defaulted to avoid error (although not needed)
        
        mode = str(pluginAction.props.get('modeWaveform','White'))  # 'Color' or 'White' (Default)
        if mode == 'White':
            try:
                kelvin = str(pluginAction.props.get('kelvinWaveform', '3500'))  # Default Kelvin to 3500 if missing
            except:
                kelvin = '3500'  # Default Kelvin to 3500 if error
        elif mode == 'Color':
            try:
                hue = str(pluginAction.props.get('hueWaveform', '0'))  # Default Hue to 0 (Red) if missing
                saturation = pluginAction.props.get('saturationWaveform', '100')  # Default Saturation to 100 if missing
            except:
                hue = '0'  # Default Hue to 0 (Red) if error
                saturation = '100'  # Default Saturation to 100 if error
        try:
            brightness = str(pluginAction.props.get('brightnessWaveform', '100'))  # Default Brightness to 100 if missing
        except:
            brightness = '100'  # Default Brightness to 100 if error
        try:
            transient = pluginAction.props.get('transientWaveform', True)  # Default Transient to '1' (Return color to original) if missing
        except:
            transient = True  # Default Transient to '1' (Return color to original) if error
        try:
            period = str(int(pluginAction.props.get('periodWaveform', 600)))  # Default Period to '500' (milliseconds) if missing
        except:
            period = str('700')  # Default Period to '500' (milliseconds) if error
        try:
            cycles = str(pluginAction.props.get('cyclesWaveform', '10'))  # Default Cycles to '10' if missing
        except:
            cycles = '10'  # Default Cycles to '10' if error
        try:
            dutyCycle = str(pluginAction.props.get('dutyCycleWaveform', '0'))  # Default Duty Cycle to '0' (Equal amount of time) if missing
        except:
            dutyCycle = '0'  # Default Duty Cycle to '0' (Equal amount of time) if error
        try:
            typeWaveform = str(pluginAction.props.get('typeWaveform', '0'))  # Default TYpe of Waveform to '0' (Saw) if missing
        except:
            typeWaveform = '0'  # Default TYpe of Waveform to '0' (Saw) if missing

        self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_WAVEFORM, 'WAVEFORM', dev.id, [mode, hue, saturation, brightness, kelvin, transient, period, cycles, dutyCycle, typeWaveform]])

        transientUi = ' Color will be returned to original.' if transient else ''
        periodUi = '%s' % int(period)
        cyclesUi = '%s' % int(cycles)
        if int(dutyCycle) == 0:
            dutyCycleUi = 'an equal amount of time is spent on the original color and the new color'
        elif int(dutyCycle) > 0:
            dutyCycleUi = 'more time is spent on the original color'
        else:
            dutyCycleUi = 'more time is spent on the new color'
        typeWaveformUi = LIFX_WAVEFORMS.get(typeWaveform,'0')

        brightnessUi = '%s' % int(float(brightness))

        if mode == 'White':
            kelvinUi = '%s' % int(float(kelvin))
            self.generalLogger.info(u"sent \"%s\" waveform \"%s\" with White Level to \"%s\" and White Temperature to \"%s\" ..." % (dev.name, typeWaveformUi, int(brightnessUi), int(kelvinUi)))
        else:
            hueUi = '%s' % int(float(hue))
            saturationUi = '%s' % int(float(saturation))
            self.generalLogger.info(u"sent \"%s\" waveform \"%s\" with hue \"%s\", saturation \"%s\" and brightness \"%s\" ..." % (dev.name, typeWaveformUi, hueUi, saturationUi, brightnessUi))
        self.generalLogger.info(u"  ... period is \"%s\" milliseconds for \"%s\" cycles and %s.%s" % (periodUi, cyclesUi, dutyCycleUi, transientUi))

    def processDiscoverDevices(self, pluginAction):
        self.methodTracer.threaddebug(u"CLASS: Plugin")
            
        self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_LOW, 'DISCOVERY', None, None])


    def processPresetApply(self, pluginAction, dev):  # Dev is a LIFX Device
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        self.preset = indigo.variables[int(pluginAction.props.get('PresetId'))]
 
        if dev.states['connected'] == False or self.globals['lifx'][dev.id]['connected'] == False:
            self.generalLogger.info(u"Unable to apply Preset \"%s\" to \"%s\" as device not connected" % (self.preset.name, dev.name))
            return

        self.generalLogger.debug(u"LIFX PLUGIN - processPresetApply [%s]: %s" % (pluginAction.props.get('PresetId'),self.preset.value)) 

        actionType, mode, turnOnIfOff, hue, saturation, brightness, kelvin, duration, transient, period, cycles, dutyCycle, typeWaveform  = self.decodePreset(self.preset.value)

        if actionType == 'Standard':
            if mode == 'White':
                if kelvin == '':
                    kelvin = '-'
                saturation = '0'
            elif mode == 'Color':
                if hue == '':
                    hue = '-'
                if saturation == '':
                    saturation = '-'
            else:
                self.generalLogger.error(u"LIFX Preset %s for %s hasn't been applied. %s" % (self.preset.name,dev.name, mode))
                return 
            if brightness == '':
                brightness = '-'
            if saturation == '':
                saturation = '-'
            if duration == '':
                duration = '-'
            if pluginAction.props.get('PresetDuration').rstrip() != '':
                try:
                    duration = str(int(pluginAction.props.get('PresetDuration')))
                except:
                    self.generalLogger.error(u"LIFX Preset %s for %s hasn't been applied. Duration[D] specified in preset is invalid: %s" % (self.preset.name, dev.name, duration))
                    return 

            if turnOnIfOff != '0' and turnOnIfOff != '1':
                self.generalLogger.error(u"LIFX Preset %s for %s hasn't been applied. Turn-On-If-Off[ON] specified in preset is invalid: %s" % (self.preset.name, dev.name, turnOnIfOff))
                return

            turnOnIfOff = False if (turnOnIfOff == '0') else True 

            self.generalLogger.debug(u'LIFX PRESET QUEUE_PRIORITY_COMMAND [STANDARD]; Target for %s: TOIF=%s, Mode=%s, Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s, Duration=%s' % (dev.name, turnOnIfOff, mode, hue, saturation, brightness, kelvin, duration))   


            self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_COMMAND, 'STANDARD', dev.id, [turnOnIfOff, mode, hue, saturation, brightness, kelvin, duration]])

            if mode == 'White':
                if kelvin == '-':
                    kelvinUi = 'existing'
                else:
                    kelvinUi = '%s' % int(float(kelvin))
                if brightness == '-':
                    brightnessUi = 'existing'
                else:
                    brightnessUi = '%s' % int(float(brightness))
                if duration == '-':
                    durationUi = 'default'
                else:
                    durationUi = str(duration)
                self.generalLogger.info(u"sent \"%s\" preset of set White Level to \"%s\" and White Temperature to \"%s\" with duration of %s seconds" % (dev.name, int(brightnessUi), int(kelvinUi), durationUi))
            else:
                if hue == '-':
                    hueUi = 'existing'
                else:
                    hueUi = '%s' % int(float(hue))
                if saturation == '-':
                    saturationUi = 'existing'
                else:
                    saturationUi = '%s' % int(float(saturation))
                if brightness == '-':
                    brightnessUi = 'existing'
                else:
                    brightnessUi = '%s' % int(float(brightness))
                if duration == '-':
                    durationUi = 'default'
                else:
                    durationUi = str(duration)

                self.generalLogger.info(u"sent \"%s\" set Color Level to hue \"%s\", saturation \"%s\" and brightness \"%s\" with duration of %s seconds" % (dev.name, hueUi, saturationUi, brightnessUi, durationUi))


        elif actionType == 'Waveform':
            if mode == 'White':
                valid = True
                if kelvin == '':
                    valid = False
                else:
                    try:
                        test = int(kelvin)
                    except ValueError:
                        valid = False
                if not valid:
                    self.generalLogger.error(u"LIFX Preset %s for %s hasn't been applied. Kelvin[K] value specified in preset is invalid: %s" % (self.preset.name, dev.name, kelvin))
                    return
            elif mode == 'Color':
                valid = True
                if hue == '':
                    valid = False
                else:
                    try:
                        test = float(hue)
                    except ValueError:
                        valid = False
                if not valid:
                    self.generalLogger.error(u"LIFX Preset %s for %s hasn't been applied. Hue[H] value specified in preset is invalid: %s" % (self.preset.name, dev.name, hue))
                    return
                if saturation == '':
                    valid = False
                else:
                    try:
                        test = float(saturation)
                    except ValueError:
                        valid = False
                if not valid:
                    self.generalLogger.error(u"LIFX Preset %s for %s hasn't been applied. Saturation[S] value specified in preset is invalid: %s" % (self.preset.name, dev.name, saturation))
                    return
            else:
                self.generalLogger.error(u"LIFX Preset %s for %s hasn't been applied. %s" % (self.preset.name, dev.name, mode))
                return 

            valid = True
            if brightness == '':
                valid = False
            else:
                try:
                    test = float(brightness)
                except ValueError:
                    valid = False
            if not valid:
                self.generalLogger.error(u"LIFX Preset %s for %s hasn't been applied. Brightness[B] value specified is preset is invalid: %s" % (self.preset.name, dev.name, brightness))
                return

            if transient != '0' and transient != '1':
                self.generalLogger.error(u"LIFX Preset %s for %s hasn't been applied. Transient[T] value specified in preset is invalid: %s" % (self.preset.name, dev.name, transient))
                return

            valid = True
            if period == '':
                valid = False
            else:
                try:
                    test = float(period)
                except ValueError:
                    valid = False
            if not valid:
                self.generalLogger.error(u"LIFX Preset %s for %s hasn't been applied. Period[P] value specified in preset is invalid: %s" % (self.preset.name, dev.name, period))
                return

            valid = True
            if cycles == '':
                valid = False
            else:
                try:
                    test = int(cycles)
                except ValueError:
                    valid = False
            if not valid:
                self.generalLogger.error(u"LIFX Preset %s for %s hasn't been applied. cycles[H] value specified in preset is invalid: %s" % (self.preset.name, dev.name, cycles))
                return

            valid = True
            if dutyCycle == '':
                valid = False
            else:
                try:
                    test = int(dutyCycle)
                except ValueError:
                    valid = False
            if not valid:
                self.generalLogger.error(u"LIFX Preset %s for %s hasn't been applied. Duty Cycle[DC] value specified is preset is invalid: %s" % (self.preset.name, dev.name, dutyCycle))
                return

            if typeWaveform != '0' and typeWaveform != '1' and typeWaveform != '2' and typeWaveform != '3' and typeWaveform != '4':
                self.generalLogger.error(u"LIFX Preset %s for %s hasn't been applied. Waveform[W] value specified in preset is invalid: %s" % (self.preset.name, dev.name, typeWaveform))
                return

            self.generalLogger.debug(u'LIFX PRESET QUEUE_PRIORITY_COMMAND [WAVEFORM]; Target for %s: Mode=%s, Hue=%s, Saturation=%s, Brightness=%s, Kelvin=%s, Transient=%s, Period=%s, Cycles=%s, Duty Cycle=%s, Waveform=%s' % (dev.name, mode, hue, saturation, brightness, kelvin, transient, period, cycles, dutyCycle, typeWaveform))   

            self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_WAVEFORM, 'WAVEFORM', dev.id, [mode, hue, saturation, brightness, kelvin, transient, period, cycles, dutyCycle, typeWaveform]])

            transientUi = ' Color will be returned to original.' if transient else ''
            periodUi = '%s' % int(period)
            cyclesUi = '%s' % int(cycles)
            if int(dutyCycle) == 0:
                dutyCycleUi = 'an equal amount of time is spent on the original color and the new color'
            elif int(dutyCycle) > 0:
                dutyCycleUi = 'more time is spent on the original color'
            else:
                dutyCycleUi = 'more time is spent on the new color'
            typeWaveformUi = LIFX_WAVEFORMS.get(typeWaveform,'0')

            brightnessUi = '%s' % int(float(brightness))

            if mode == 'White':
                kelvinUi = '%s' % int(float(kelvin))
                self.generalLogger.info(u"sent \"%s\" waveform \"%s\" with White Level to \"%s\" and White Temperature to \"%s\" ..." % (dev.name, typeWaveformUi, int(brightnessUi), int(kelvinUi)))
            else:
                hueUi = '%s' % int(float(hue))
                saturationUi = '%s' % int(float(saturation))
                self.generalLogger.info(u"sent \"%s\" preset of waveform \"%s\" with hue \"%s\", saturation \"%s\" and brightness \"%s\" ..." % (dev.name, typeWaveformUi, hueUi, saturationUi, brightnessUi))
            self.generalLogger.info(u"  ... period is \"%s\" milliseconds for \"%s\" cycles and %s.%s" % (periodUi, cyclesUi, dutyCycleUi, transientUi))

        else:
            self.generalLogger.error(u"LIFX Preset [%s] hasn't been applied. Action-Type[AT] specified in preset is invalid" % (dev.name)) 


    def decodePreset(self, preset):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        actionType = ''
        turnOnIfOff = ''
        mode= ''
        hue = ''
        saturation = ''
        brightness = ''
        kelvin = ''
        duration = ''
        transient = ''
        period = ''
        cycles = ''
        dutyCycle = ''
        waveform = ''

        presetItems = preset.split(",")
        self.generalLogger.debug(u"LIFX validatePreset-A [%s]" % (presetItems))

        for presetItem in presetItems:
            self.generalLogger.debug(u"LIFX validatePreset-B [%s]" % (presetItem))
            
            presetElement, presetValue = presetItem.split("=")
            if presetElement == 'AT':
                if presetValue == 'S':
                    actionType = 'Standard'
                elif presetValue == 'W':
                    actionType = 'Waveform'
                else:
                    actionType = 'Preset Invalid LIFX Action Type (AT) in PRESET'
            if presetElement == 'M':
                if presetValue == 'W':
                    mode = 'White'
                elif presetValue == 'C':
                    mode = 'Color'
                else:
                    mode = 'Preset Invalid LIFX Color/White Mode (M) in PRESET'
            if presetElement == 'ON':
                turnOnIfOff = str(presetValue)
            elif presetElement == 'H':
                hue = str(presetValue)
            elif presetElement == 'S':
                saturation = str(presetValue)
            elif presetElement == 'B':
                brightness = str(presetValue)
            elif presetElement == 'K':
                kelvin = str(presetValue)
            elif presetElement == 'D':
                duration = str(presetValue)
            elif presetElement == 'T':
                transient = str(presetValue)
            elif presetElement == 'P':
                period = str(presetValue)
            elif presetElement == 'C':
                cycles = str(presetValue)
            elif presetElement == 'DC':
                dutyCycle = str(presetValue)
            elif presetElement == 'W':
                waveform = str(presetValue)

        # handle presets from previous versions

        if (actionType == '') and (mode == ''):  # Might be from previous version of plugin?
            # check for waveform
            if (transient == 'False') or (transient == 'True'):
                # Is an old style Waveform preset, so adjust accordingly
                if transient == 'False':
                    transient = '0'
                else:
                    transient = '1'
                actionType = 'Waveform'
                if kelvin != '':
                    mode = 'White'
                else:
                    mode = 'Color'
                    if saturation == '':
                        saturation = '100'
            else:
                # Is probably old style Standard preset, so adjust accordingly
                actionType = 'Standard'
                if kelvin != '':
                    mode = 'White'
                else:
                    mode = 'Color'
                    if saturation == '':
                        saturation = '100'
        # Now check that turnOnIfOff, if not default to '1' = True
        if actionType == 'Standard':
            if turnOnIfOff == '':
                turnOnIfOff = '1'

        self.generalLogger.debug(u"LIFX Preset: Action Type=%s, Mode=%s, ON=%s, H=%s, K=%s, B=%s, D=%s, T=%s, P=%s, C=%s, DC=%s, W=%s" % (actionType, mode, turnOnIfOff, hue, kelvin, brightness, duration, transient, period, cycles, dutyCycle, waveform))

        return (actionType, mode, turnOnIfOff, hue, saturation, brightness, kelvin, duration, transient, period, cycles, dutyCycle, waveform) 


    def processPresetApplyDefineGenerator(self, filter="", valuesDict=None, typeId="", targetId=0):
        self.methodTracer.threaddebug(u"CLASS: Plugin")

        preset_dict = list()
        preset_dict.append(("SELECT_PRESET", "- Select Preset -"))

        for preset in indigo.variables.iter():
            if preset.folderId == self.globals['folders']['VariablesId']:
                preset_found = (str(preset.id), str(preset.name))
                preset_dict.append(preset_found)

        myArray = preset_dict
        return myArray