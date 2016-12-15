#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# LIFX V4 Controller - Polling © Autolog 2016
#

try:
    import indigo
except:
    pass
import logging
import sys
import threading

from constants import *

class ThreadPolling(threading.Thread):

    def __init__(self, globalsAndEvent):

        threading.Thread.__init__(self)

        self.globals, self.pollStop = globalsAndEvent

        self.previousPollingSeconds = self.globals['polling']['seconds']

        self.globals['polling']['threadActive'] = True

        self.pollingLogger = logging.getLogger("Plugin.polling")
        self.pollingLogger.setLevel(self.globals['debug']['debugPolling'])

        self.methodTracer = logging.getLogger("Plugin.method")  
        self.methodTracer.setLevel(self.globals['debug']['debugMethodTrace'])

        self.pollingLogger.info(u"Initialising to poll at %i second intervals" % (self.globals['polling']['seconds']))  
        self.pollingLogger.debug(u"debugPolling = %s [%s], debugMethodTrace = %s [%s]" % (self.globals['debug']['debugPolling'], 
            type(self.globals['debug']['debugPolling']), 
            self.globals['debug']['debugMethodTrace'], 
            type(self.globals['debug']['debugMethodTrace'])))  

    def run(self):
        try:  
            self.methodTracer.threaddebug(u"ThreadPolling")

            self.pollingLogger.debug(u"Polling thread running")  

            #self.globals['queues']['messageToSend'].put([QUEUE_PRIORITY_POLLING, 'STATUSPOLLING', 0])  # 1st time

            while not self.pollStop.wait(self.globals['polling']['seconds']):

                # Check if monitoring / debug options have changed and if so set accordingly
                if self.globals['debug']['previousDebugPolling'] != self.globals['debug']['debugPolling']:
                    self.globals['debug']['previousDebugPolling'] = self.globals['debug']['debugPolling']
                    self.pollingLogger.setLevel(self.globals['debug']['debugPolling'])
                if self.globals['debug']['previousDebugMethodTrace'] !=self.globals['debug']['debugMethodTrace']:
                    self.globals['debug']['previousDebugMethodTrace'] = self.globals['debug']['debugMethodTrace']
                    self.pollingLogger.setLevel(self.globals['debug']['debugMethodTrace'])

                # Check if polling seconds interval has changed and if so set accordingly
                if self.globals['polling']['seconds'] != self.previousPollingSeconds:
                    self.pollingLogger.info(u"Changing to poll at %i second intervals (was %i seconds)" % (self.globals['polling']['seconds'], self.previousPollingSeconds))  
                    self.previousPollingSeconds = self.globals['polling']['seconds']

                self.pollingLogger.debug(u"Start of While Loop ...")
                if self.pollStop.isSet():
                    if self.globals['polling']['forceThreadEnd'] == True:
                        break
                    else:
                        self.pollStop.clear()
                self.pollingLogger.debug(u"Now polling at %i second intervals" % (self.globals['polling']['seconds']))
                if self.globals['polling']['quiesced'] == False:

                    self.globals['polling']['count'] += 1  # Increment polling count

                    # Check if LIFX Lamps are responding to polls
                    noAck = False  # Assume all lights responding
                    for devId in self.globals['lifx']:
                        dev_poll_check = self.globals['lifx'][devId]['lastResponseToPollCount'] + self.globals['polling']['missedLimit']
                        self.pollingLogger.debug(u"Dev = '%s', Count = %s, LIFX LastResponse = %s, Missed Limit = %s, Check = %s" % (indigo.devices[devId].name, self.globals['polling']['count'], self.globals['lifx'][devId]['lastResponseToPollCount'], self.globals['polling']['missedLimit'], dev_poll_check))
                        dev = indigo.devices[devId]
                        if (dev_poll_check < self.globals['polling']['count']) or (not self.globals['lifx'][devId]['started']):
                            self.pollingLogger.debug(u"dev_poll_check < self.globals['polling']['count']")
                            indigo.devices[devId].setErrorStateOnServer(u"no ack")
                            dev.updateStateOnServer(key='connected', value='false', clearErrorState=False)
                            noAck = True  #  Indicate at least one light "not acknowledging" 
                        # else:
                        #     if not dev.states['connected']:
                        #         dev.updateStateOnServer(key='connected', value='true')
                    if noAck:
                        self.globals['queues']['messageToSend'].put([QUEUE_PRIORITY_DISCOVERY, 'DISCOVERY', 0])  # Discover devices before polling LIFX devices for status updates


                    self.globals['queues']['messageToSend'].put([QUEUE_PRIORITY_POLLING, 'STATUSPOLLING', 0])  # Poll LIFX devices for status updates

            self.pollingLogger.debug(u"Polling thread ending")

        except StandardError, e:
            self.pollingLogger.error(u"StandardError detected during Polling. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))

        self.globals['polling']['threadActive'] = False
