#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# LIFX V7 Controller © Autolog 2020-2022

# noinspection PyUnresolvedReferences
# ============================== Native Imports ===============================
import logging
import sys
import threading
import traceback
import time

# ============================== Custom Imports ===============================
try:
    import indigo
except ImportError:
    pass

# ============================== Plugin Imports ===============================
from constants import *


class ThreadPolling(threading.Thread):

    def __init__(self, pluginGlobals, event):

        threading.Thread.__init__(self)

        self.globals = pluginGlobals
        self.poll_stop = event

        self.previous_polling_seconds = self.globals[K_POLLING][K_SECONDS]

        self.globals[K_POLLING][K_THREAD_ACTIVE] = True

        self.p_logger = logging.getLogger("Plugin.POLLING")
        self.p_logger.debug(u"Debugging Polling Thread")

        self.p_logger.info(u"Initialising to poll at {0} second intervals".format(self.globals[K_POLLING][K_SECONDS]))

    def exception_handler(self, exception_error_message, log_failing_statement):
        filename, line_number, method, statement = traceback.extract_tb(sys.exc_info()[2])[-1]
        module = filename.split('/')
        log_message = u"'{0}' in module '{1}', method '{2}'".format(exception_error_message, module[-1], method)
        if log_failing_statement:
            log_message = log_message + u"\n   Failing statement [line {0}]: '{1}'".format(line_number, statement)
        else:
            log_message = log_message + u" at line {0}".format(line_number)
        self.p_logger.error(log_message)

    def run(self):
        try:  
            self.p_logger.debug(u"LIFX Polling thread now running")

            while True:
                self.poll_stop.wait(self.globals[K_POLLING][K_SECONDS])

                if self.poll_stop.isSet():
                    if self.globals[K_POLLING][K_FORCE_THREAD_END]:
                        break
                    else:
                        self.poll_stop.clear()

                # Message not quite at start as debug settings need to be checked first and also whether thread is being stopped.
                self.p_logger.debug(u"Start of While Loop ...")

                # Check if polling seconds interval has changed and if so set accordingly
                if self.globals[K_POLLING][K_SECONDS] != self.previous_polling_seconds:
                    self.p_logger.info(u"Changing to poll at {0} second intervals (was {1} seconds)"
                                       .format(self.globals[K_POLLING][K_SECONDS], self.previous_polling_seconds))
                    self.previous_polling_seconds = self.globals[K_POLLING][K_SECONDS]

                self.p_logger.debug(u"Polling at {0} second intervals".format(self.globals[K_POLLING][K_SECONDS]))

                if not self.globals[K_POLLING][K_QUIESCED]:

                    # self.globals[K_POLLING][K_COUNT] += 1  # Increment polling count

                    for dev in indigo.devices.iter("self"):
                        if dev.enabled:
                            self.globals[K_QUEUES][K_LIFXLAN_HANDLER][K_QUEUE].put([QUEUE_PRIORITY_STATUS_MEDIUM, CMD_POLLING_STATUS, dev.id, None])
                            time.sleep(1.0)  # delay each status request in order to not overload the system

            self.p_logger.debug(u"Polling thread ending: pollStop.isSet={0}, forceThreadEnd={1}, newSeconds={2}, previousSeconds={3}"
                                .format(self.poll_stop.isSet(), self.globals[K_POLLING][K_FORCE_THREAD_END],
                                        self.globals[K_POLLING][K_SECONDS], self.previous_polling_seconds))


        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

        self.globals[K_POLLING][K_THREAD_ACTIVE] = False
