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
import time

from constants import *


class ThreadPolling(threading.Thread):

    def __init__(self, pluginGlobals, event):

        threading.Thread.__init__(self)

        self.globals = pluginGlobals
        self.pollStop = event

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
            self.pollingLogger.info(u"LIFX Polling thread now running")

            while True:
                self.pollStop.wait(self.globals['polling']['seconds'])

                if self.pollStop.isSet():
                    if self.globals['polling']['forceThreadEnd']:
                        break
                    else:
                        self.pollStop.clear()

                # Check if monitoring / debug options have changed and if so set accordingly
                if self.globals['debug']['previousDebugPolling'] != self.globals['debug']['debugPolling']:
                    self.globals['debug']['previousDebugPolling'] = self.globals['debug']['debugPolling']
                    self.pollingLogger.setLevel(self.globals['debug']['debugPolling'])
                if self.globals['debug']['previousDebugMethodTrace'] != self.globals['debug']['debugMethodTrace']:
                    self.globals['debug']['previousDebugMethodTrace'] = self.globals['debug']['debugMethodTrace']
                    self.pollingLogger.setLevel(self.globals['debug']['debugMethodTrace'])

                self.pollingLogger.debug(u"Start of While Loop ...")  # Message not quite at start as debug settings need to be checked first and also whether thread is being stopped.

                # Check if polling seconds interval has changed and if so set accordingly
                if self.globals['polling']['seconds'] != self.previousPollingSeconds:
                    self.pollingLogger.info(u"Changing to poll at %i second intervals (was %i seconds)" % (self.globals['polling']['seconds'], self.previousPollingSeconds))  
                    self.previousPollingSeconds = self.globals['polling']['seconds']


                self.pollingLogger.debug(u"Polling at %i second intervals" % (self.globals['polling']['seconds']))

                if not self.globals['polling']['quiesced']:

                    self.globals['polling']['count'] += 1  # Increment polling count

                    for dev in indigo.devices.iter("self"):
                        if dev.enabled:
                            self.globals['queues']['lifxlanHandler'].put([QUEUE_PRIORITY_STATUS_MEDIUM, CMD_STATUS, dev.id, None])
                                 

            self.pollingLogger.debug(u"Polling thread ending: pollStop.isSet={}, forceThreadEnd={}, newSeconds={}, previousSeconds={} ".format(self.pollStop.isSet(), self.globals['polling']['forceThreadEnd'], self.globals['polling']['seconds'], self.previousPollingSeconds))

        except StandardError, e:
            self.pollingLogger.error(u"StandardError detected during Polling. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))

        self.globals['polling']['threadActive'] = False
