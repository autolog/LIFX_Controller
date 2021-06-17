#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# LIFX V4 Controller - Constants © Autolog 2016
#

# plugin Constants

K_LOG_LEVEL_NOT_SET = 0
K_LOG_LEVEL_DETAILED_DEBUGGING = 5
K_LOG_LEVEL_DEBUGGING = 10
K_LOG_LEVEL_INFO = 20
K_LOG_LEVEL_WARNING = 30
K_LOG_LEVEL_ERROR = 40
K_LOG_LEVEL_CRITICAL = 50

K_LOG_LEVEL_TRANSLATION = {}
K_LOG_LEVEL_TRANSLATION[K_LOG_LEVEL_NOT_SET] = "Not Set"
K_LOG_LEVEL_TRANSLATION[K_LOG_LEVEL_DETAILED_DEBUGGING] = "Detailed debugging"
K_LOG_LEVEL_TRANSLATION[K_LOG_LEVEL_DEBUGGING] = "Debugging"
K_LOG_LEVEL_TRANSLATION[K_LOG_LEVEL_INFO] = "Info"
K_LOG_LEVEL_TRANSLATION[K_LOG_LEVEL_WARNING] = "Warning"
K_LOG_LEVEL_TRANSLATION[K_LOG_LEVEL_ERROR] = "Error"
K_LOG_LEVEL_TRANSLATION[K_LOG_LEVEL_CRITICAL] = "Critical"

LIFX_DEVICE_TYPEID = 'lifxDevice'  # See definition in Devices.xml

# Globals dictionary 'index' values

K_ACTIVE = 0
K_ADDRESS = 1
K_API_VERSION = 2
K_AUTO_CONNECT = 3
K_CONNECTED = 4
K_CONSTANT = 5
K_COUNT = 6
K_DEBUG = 7
K_DEBUG_FILTERED_IP_ADDRESSES = 8
K_DEBUG_FILTERED_IP_ADDRESSES_UI = 9
K_DEFAULT_DATE_TIME = 10
K_DEVICES_ID = 11
K_DEVICE_STARTED = 12
K_DEVICE_TIMERS = 13
K_DEV_ID = 14
K_DISCOVERED = 15
K_DISCOVERY = 16
K_DURATION_COLOR_WHITE = 17
K_DURATION_DIM_BRIGHTEN = 18
K_DURATION_OFF = 19
K_DURATION_ON = 20
K_ENABLED = 21
K_EVENT = 22
K_EVENT_LOG = 23
K_FOLDERS = 24
K_FORCE_THREAD_END = 25
K_HOST = 26
K_IGNORE_NO_ACK = 27
K_INITIALISED = 28
K_IP_ADDRESS = 29
K_LIFX = 30
K_LIFXLAN_DEVICE_INDEX = 31
K_LIFXLAN_HANDLER = 32
K_LIFX_COMMAND_CURRENT = 33
K_LIFX_COMMAND_PREVIOUS = 34
K_LOCK = 35
K_LOG_TO_EVENT_LOG = 36
K_LOG_TO_PLUGIN_LOG = 37
K_MAC_ADDRESS = 38
K_METHOD_TRACE = 39
K_MINUTES = 40
K_NO_ACK_STATE = 41
K_PATH = 42
K_PLUGIN_CONFIG_DEFAULT = 43
K_PLUGIN_DISPLAY_NAME = 44
K_PLUGIN_ID = 45
K_PLUGIN_INFO = 46
K_PLUGIN_VERSION = 47
K_POLLING = 48
K_PORT = 49
K_PREVIOUS_LOGGING = 50
K_PREVIOUS_METHOD_TRACE = 51
K_PREVIOUS_TP_HANDLER = 52
K_QUEUE = 53
K_QUEUES = 54
K_QUIESCED = 55
K_RECOVERY_INVOKED = 56
K_RUN_CONCURRENT_ACTIVE = 57
K_SECONDS = 58
K_SEND_TO_TP = 59
K_SHOW_MESSAGES = 60
K_SHOW_VARIABLE_VALUE = 61
K_SOCKETS = 62
K_SOCKET_RETRY_SECONDS = 63
K_SOCKET_RETRY_SILENT_AFTER = 64
K_STATUS = 65
K_STOP_REPEAT_BRIGHTEN = 66
K_STOP_REPEAT_DIM = 67
K_THREAD = 68
K_THREADS = 69
K_THREAD_ACTIVE = 70
K_TIMEOUT = 71
K_TP = 72
K_TP_SOCKET = 73
K_TRIGGER = 74
K_VARIABLES_ID = 75
K_LABEL = 76
K_CHANGED_INFO = 77
K_GROUP = 78
K_POWER_LEVEL = 79
K_HOST_FIRMWARE_BUILD_TIMESTAMP = 80
K_HOST_FIRMWARE_VERSION = 81
K_WIFI_FIRMWARE_BUILD_TIMESTAMP = 82
K_WIFI_FIRMWARE_VERSION = 83
K_VENDOR = 84
K_PRODUCT = 85
K_VERSION = 86
K_PRODUCT_NAME = 87
K_PRODUCT_FEATURES = 88
K_AUTO_CREATE_LIFX_DEVICES = 89
K_INDIGO_DEVICE_ID = 90
K_LIFX_DEVICE = 91
K_DELETING = 92
K_FIRMWARE_UI = 93
K_RECOVERY = 94
K_ATTEMPTS = 95
K_RECOVERY_TIMERS = 96
K_RECOVERY_ATTEMPTS_LIMIT = 97
K_RECOVERY_FREQUENCY = 98
K_HIDE_RECOVERY_MESSAGES = 99
K_INITIAL_DISCOVERY_COMPLETE = 100
K_LOCATION = 101

# Plugin Internal commands
CMD_BRIGHTEN = 1001
CMD_BRIGHTEN_BY_TIMER = 1002
CMD_BRIGHTNESS = 1003
CMD_COLOR = 1004
CMD_DIM = 1005
CMD_DIM_BY_TIMER = 1006
CMD_DISCOVERY = 1007
CMD_GET_GROUP = 1008
CMD_GET_HOST_INFO = 1009
CMD_GET_INFO = 1010
CMD_GET_LOCATION = 1011
CMD_GET_PORT = 1012
CMD_GET_WIFI_FIRMWARE = 1013
CMD_GET_WIFI_INFO = 1014
CMD_GET_HOST_FIRMWARE = 1015
CMD_GET_VERSION = 1016
CMD_IMMEDIATE_ON = 1017
CMD_INFRARED_OFF = 1018
CMD_INFRARED_ON = 1019
CMD_INFRARED_SET = 1020
CMD_OFF = 1021
CMD_ON = 1022
CMD_POLLING_STATUS = 1023
CMD_RECOVERY_STATUS = 1024
CMD_REPEAT_BRIGHTEN_BY_TIMER = 1025
CMD_REPEAT_DIM_BY_TIMER = 1026
CMD_SET_LABEL = 1027
CMD_STANDARD = 1028
CMD_STATUS = 1029
CMD_STOP_BRIGHTEN_DIM_BY_TIMER = 1030
CMD_STOP_THREAD = 1031
CMD_WAVEFORM = 1032
CMD_WAVEFORM_OFF = 1033
CMD_WHITE = 1034

# Plugin Internal commands (translation)
CMD_TRANSLATION = dict()
CMD_TRANSLATION[CMD_BRIGHTEN] = 'BRIGHTEN'
CMD_TRANSLATION[CMD_BRIGHTEN_BY_TIMER] = 'BRIGHTEN BY TIMER'
CMD_TRANSLATION[CMD_BRIGHTNESS] = 'BRIGHTNESS'
CMD_TRANSLATION[CMD_COLOR] = 'COLOR'
CMD_TRANSLATION[CMD_DIM] = 'DIM'
CMD_TRANSLATION[CMD_DIM_BY_TIMER] = 'DIM BY TIMER'
CMD_TRANSLATION[CMD_DISCOVERY] = 'DISCOVERY'
CMD_TRANSLATION[CMD_GET_GROUP] = 'GET GROUP'
CMD_TRANSLATION[CMD_GET_HOST_INFO] = 'GET HOST INFO'
CMD_TRANSLATION[CMD_GET_INFO] = 'GET INFO'
CMD_TRANSLATION[CMD_GET_LOCATION] = 'GET LOCATION'
CMD_TRANSLATION[CMD_GET_PORT] = 'GET PORT'
CMD_TRANSLATION[CMD_GET_WIFI_FIRMWARE] = 'GET WIFI FIRMWARE'
CMD_TRANSLATION[CMD_GET_WIFI_INFO] = 'GET WIFI INFO'
CMD_TRANSLATION[CMD_GET_HOST_FIRMWARE] = 'GET HOST FIRMWARE'
CMD_TRANSLATION[CMD_GET_VERSION] = 'GET VERSION'
CMD_TRANSLATION[CMD_IMMEDIATE_ON] = 'IMMEDIATE ON'
CMD_TRANSLATION[CMD_INFRARED_OFF] = 'INFRARED OFF'
CMD_TRANSLATION[CMD_INFRARED_ON] = 'INFRARED ON'
CMD_TRANSLATION[CMD_INFRARED_SET] = 'INFRARED SET'
CMD_TRANSLATION[CMD_OFF] = 'OFF'
CMD_TRANSLATION[CMD_ON] = 'ON'
CMD_TRANSLATION[CMD_POLLING_STATUS] = 'POLLING STATUS'
CMD_TRANSLATION[CMD_RECOVERY_STATUS] = 'RECOVERY STATUS'
CMD_TRANSLATION[CMD_REPEAT_BRIGHTEN_BY_TIMER] = 'REPEAT BRIGHTEN BY TIMER'
CMD_TRANSLATION[CMD_REPEAT_DIM_BY_TIMER] = 'REPEAT DIM BY TIMER'
CMD_TRANSLATION[CMD_SET_LABEL] = 'SET LABEL'
CMD_TRANSLATION[CMD_STANDARD] = 'STANDARD'
CMD_TRANSLATION[CMD_STATUS] = 'STATUS'
CMD_TRANSLATION[CMD_STOP_BRIGHTEN_DIM_BY_TIMER] = 'STOP BRIGHTEN DIM BY TIMER'
CMD_TRANSLATION[CMD_STOP_THREAD] = 'STOPTHREAD'
CMD_TRANSLATION[CMD_WAVEFORM] = 'WAVEFORM'
CMD_TRANSLATION[CMD_WAVEFORM_OFF] = 'WAVEFORM OFF'
CMD_TRANSLATION[CMD_WHITE] = 'WHITE'

# Number of discoveries to executed at start-up
START_UP_REQUIRED_DISCOVERY_COUNT = 10 

# QUEUE Priorities
QUEUE_PRIORITY_STOP_THREAD    = 0
QUEUE_PRIORITY_INIT_DISCOVERY = 50
QUEUE_PRIORITY_WAVEFORM       = 100
QUEUE_PRIORITY_COMMAND_HIGH   = 200
QUEUE_PRIORITY_COMMAND_MEDIUM = 300
QUEUE_PRIORITY_STATUS_HIGH    = 400
QUEUE_PRIORITY_STATUS_MEDIUM  = 500
QUEUE_PRIORITY_DISCOVERY      = 600
QUEUE_PRIORITY_POLLING        = 700
QUEUE_PRIORITY_LOW            = 800

# LIFX product constants
LIFX_PRODUCTS = dict()
#                    Color, Infrared, Multizone, Name
LIFX_PRODUCTS[1]  = (True,  False, False, 'Original 1000')
LIFX_PRODUCTS[3]  = (True,  False, False, 'Color 650')
LIFX_PRODUCTS[10] = (False, False, False, 'White 800 (Low Voltage)')
LIFX_PRODUCTS[11] = (False, False, False, 'White 800 (High Voltage)')
LIFX_PRODUCTS[18] = (False, False, False, 'White 900 BR30 (Low Voltage)')
LIFX_PRODUCTS[20] = (True,  False, False, 'Color 1000 BR30')
LIFX_PRODUCTS[22] = (True,  False, False, 'Color 1000')
LIFX_PRODUCTS[27] = (True,  False, False, 'LIFX A19')
LIFX_PRODUCTS[28] = (True,  False, False, 'LIFX BR30')
LIFX_PRODUCTS[29] = (True,  True,  False, 'LIFX + A19')
LIFX_PRODUCTS[30] = (True,  True,  False, 'LIFX + BR30')
LIFX_PRODUCTS[31] = (True,  False, True,  'LIFX Z')
LIFX_PRODUCTS[32] = (True,  False, True,  'LIFX Z 2')
LIFX_PRODUCTS[36] = (True,  False, False, 'LIFX Downlight')
LIFX_PRODUCTS[37] = (True,  False, False, 'LIFX Downlight')
LIFX_PRODUCTS[43] = (True,  False, False, 'LIFX A19')
LIFX_PRODUCTS[44] = (True,  False, False, 'LIFX BR30')
LIFX_PRODUCTS[45] = (True,  True,  False, 'LIFX+ A19')
LIFX_PRODUCTS[46] = (True,  True,  False, 'LIFX+ BR30')
LIFX_PRODUCTS[49] = (True,  False, False, 'LIFX Mini')
LIFX_PRODUCTS[50] = (False, False, False, 'LIFX Mini Warm to White')
LIFX_PRODUCTS[51] = (False, False, False, 'LIFX Mini Day and Dusk')
LIFX_PRODUCTS[52] = (True,  False, False, 'LIFX GU10')
LIFX_PRODUCTS[55] = (True,  False, False, 'LIFX Tile')
LIFX_PRODUCTS[57] = (True,  False, False, 'LIFX Candle')
LIFX_PRODUCTS[59] = (True,  False, False, 'LIFX Mini Color')
LIFX_PRODUCTS[60] = (False, False, False, 'LIFX Mini Warm to White')
LIFX_PRODUCTS[61] = (False, False, False, 'LIFX Mini White')
LIFX_PRODUCTS[62] = (True,  False, False, 'LIFX A19')
LIFX_PRODUCTS[63] = (True,  False, False, 'LIFX BR30')
LIFX_PRODUCTS[64] = (True,  True, False, 'LIFX+ A19')
LIFX_PRODUCTS[65] = (True,  True, False, 'LIFX+ BR30')
LIFX_PRODUCTS[68] = (True,  False, False, 'LIFX Candle')

LIFX_PRODUCT_SUPPORTS_COLOR = 0
LIFX_PRODUCT_SUPPORTS_INFRARED = 1
LIFX_PRODUCT_SUPPORTS_MULTIZONE = 2
LIFX_PRODUCT_NAME = 3

# LIFX Waveform Types
LIFX_WAVEFORMS = dict()
LIFX_WAVEFORMS['0'] = 'Saw'
LIFX_WAVEFORMS['1'] = 'Sine'
LIFX_WAVEFORMS['2'] = 'Half-Sine'
LIFX_WAVEFORMS['3'] = 'Triangle'
LIFX_WAVEFORMS['4'] = 'Pulse'

# LIFX Kelvin Descriptions (from iOS LIFX App)
LIFX_KELVINS = dict()
LIFX_KELVINS[2500] = ((246,221,184), '2500K Ultra Warm')
LIFX_KELVINS[2750] = ((246,224,184), '2750K Incandescent')
LIFX_KELVINS[3000] = ((248,227,195), '3000K Warm')
LIFX_KELVINS[3200] = ((247,228,198), '3200K Neutral Warm')
LIFX_KELVINS[3500] = ((246,228,201), '3500K Neutral')
LIFX_KELVINS[4000] = ((249,234,210), '4000K Cool')
LIFX_KELVINS[4500] = ((250,238,217), '4500K Cool Daylight')
LIFX_KELVINS[5000] = ((250,239,219), '5000K Soft Daylight')
LIFX_KELVINS[5500] = ((249,240,225), '5500K Daylight')
LIFX_KELVINS[6000] = ((247,241,230), '6000K Noon Daylight')
LIFX_KELVINS[6500] = ((245,242,234), '6500K Bright Daylight')
LIFX_KELVINS[7000] = ((241,240,236), '7000K Cloudy Daylight')
LIFX_KELVINS[7500] = ((236,236,238), '7500K Blue Daylight')
LIFX_KELVINS[8000] = ((237,240,246), '8000K Blue Overcast')
LIFX_KELVINS[8500] = ((236,241,249), '8500K Blue Water')
LIFX_KELVINS[9000] = ((237,243,252), '9000K Blue Ice')

# LIFX message type constants
DEV_GET_SERVICE         = 2    # Hex = 02
DEV_STATE_SERVICE       = 3    # Hex = 03
DEV_GET_HOST_INFO       = 12   # Hex = 0C
DEV_STATE_HOST_INFO     = 13   # Hex = 0D
DEV_GET_HOST_FIRMWARE   = 14   # Hex = 0E
DEV_STATE_HOST_FIRMWARE = 15   # Hex = 0F
DEV_GET_WIFI_INFO       = 16   # Hex = 10
DEV_STATE_WIFI_INFO     = 17   # Hex = 11
DEV_GET_WIFI_FIRMWARE   = 18   # Hex = 12
DEV_STATE_WIFI_FIRMWARE = 19   # Hex = 13
DEV_GET_POWER           = 20   # Hex = 14
DEV_SET_POWER           = 21   # Hex = 15
DEV_STATE_POWER         = 22   # Hex = 16
DEV_GET_LABEL           = 23   # Hex = 17
DEV_SET_LABEL           = 24   # Hex = 18
DEV_STATE_LABEL         = 25   # Hex = 19
DEV_GET_VERSION         = 32   # Hex = 20
DEV_STATE_VERSION       = 33   # Hex = 21
DEV_GET_INFO            = 34   # Hex = 22
DEV_STATE_INFO          = 35   # Hex = 23
DEV_ACKNOWLEDGEMENT     = 45   # Hex = 2D
DEV_GET_LOCATION        = 48   # Hex = 30
DEV_STATE_LOCATION      = 50   # Hex = 32
DEV_GET_GROUP           = 51   # Hex = 33
DEV_STATE_GROUP         = 53   # Hex = 35
DEV_ECHO_REQUEST        = 58   # Hex = 3A
DEV_ECHO_RESPONSE       = 59   # Hex = 3B
LIGHT_GET                = 101  # Hex = 65
LIGHT_SET_COLOR          = 102  # Hex = 66
LIGHT_SET_WAVEFORM       = 103  # Hex = 67 
LIGHT_STATE              = 107  # Hex = 6B
LIGHT_GET_POWER          = 116  # Hex = 74
LIGHT_SET_POWER          = 117  # Hex = 75
LIGHT_STATE_POWER        = 118  # Hex = 76
LIGHT_GET_INFRARED       = 120  # Hex = 78
LIGHT_STATE_INFRARED     = 121  # Hex = 79
LIGHT_SET_INFRARED       = 122  # Hex = 7A
MZ_SET_COLOR_ZONES      = 501  # Hex = 1F5
MZ_GET_COLOR_ZONES      = 502  # Hex = 1F6
MZ_STATE_ZONE           = 503  # Hex = 1F7 
MZ_STATE_MULTI_ZONE     = 506  # Hex = 1FA

# LIFX Message Format Dictionary 
messageTypeDict = dict()
messageTypeDict[DEV_GET_SERVICE]         = {'name':'GetService',        'payloadLength': 0,  'resRequired': '0'}
messageTypeDict[DEV_STATE_SERVICE]       = {'name':'StateService',      'payloadLength': 5,  'resRequired': '0'}
messageTypeDict[DEV_GET_HOST_INFO]       = {'name':'GetHostInfo',       'payloadLength': 0,  'resRequired': '0'}
messageTypeDict[DEV_STATE_HOST_INFO]     = {'name':'StateHostInfo',     'payloadLength': 14, 'resRequired': '0'}
messageTypeDict[DEV_GET_HOST_FIRMWARE]   = {'name':'GetHostFirmware',   'payloadLength': 0,  'resRequired': '0'}
messageTypeDict[DEV_STATE_HOST_FIRMWARE] = {'name':'StateHostFirmware', 'payloadLength': 20, 'resRequired': '0'}
messageTypeDict[DEV_GET_WIFI_INFO]       = {'name':'GetWifiInfo',       'payloadLength': 0,  'resRequired': '0'}
messageTypeDict[DEV_STATE_WIFI_INFO]     = {'name':'StateWifiInfo',     'payloadLength': 16, 'resRequired': '0'}
messageTypeDict[DEV_GET_WIFI_FIRMWARE]   = {'name':'GetWifiFirmware',   'payloadLength': 0,  'resRequired': '0'}
messageTypeDict[DEV_STATE_WIFI_FIRMWARE] = {'name':'StateWifiFirmware', 'payloadLength': 20, 'resRequired': '0'}
messageTypeDict[DEV_GET_POWER]           = {'name':'GetPower',          'payloadLength': 0,  'resRequired': '0'}
messageTypeDict[DEV_SET_POWER]           = {'name':'SetPower',          'payloadLength': 2,  'resRequired': '1'}
messageTypeDict[DEV_STATE_POWER]         = {'name':'StatePower',        'payloadLength': 2,  'resRequired': '0'}
messageTypeDict[DEV_GET_LABEL]           = {'name':'GetLabel',          'payloadLength': 0,  'resRequired': '0'}
messageTypeDict[DEV_SET_LABEL]           = {'name':'SetLabel',          'payloadLength': 4,  'resRequired': '1'}
messageTypeDict[DEV_STATE_LABEL]         = {'name':'StateLabel',        'payloadLength': 32, 'resRequired': '0'}
messageTypeDict[DEV_GET_VERSION]         = {'name':'GetVersion',        'payloadLength': 0,  'resRequired': '0'}
messageTypeDict[DEV_STATE_VERSION]       = {'name':'StateVersion',      'payloadLength': 12, 'resRequired': '0'}
messageTypeDict[DEV_GET_INFO]            = {'name':'GetInfo',           'payloadLength': 0,  'resRequired': '0'}
messageTypeDict[DEV_STATE_INFO]          = {'name':'StateInfo',         'payloadLength': 24, 'resRequired': '0'}
messageTypeDict[DEV_ACKNOWLEDGEMENT]     = {'name':'Acknowledgement',   'payloadLength': 0,  'resRequired': '0'}  # TODO: Is this correct 2016-Nov-19
messageTypeDict[DEV_GET_LOCATION]        = {'name':'GetLocation',       'payloadLength': 0,  'resRequired': '0'}
messageTypeDict[DEV_STATE_LOCATION]      = {'name':'StateLocatiom',     'payloadLength': 56, 'resRequired': '0'}
messageTypeDict[DEV_GET_GROUP]           = {'name':'GetGroup',          'payloadLength': 0,  'resRequired': '0'}
messageTypeDict[DEV_STATE_GROUP]         = {'name':'StateGroup',        'payloadLength': 56, 'resRequired': '0'}
messageTypeDict[DEV_ECHO_REQUEST]        = {'name':'EchoRequest',       'payloadLength': 64, 'resRequired': '0'}
messageTypeDict[DEV_ECHO_RESPONSE]       = {'name':'EchoResponse',      'payloadLength': 64, 'resRequired': '0'}
messageTypeDict[LIGHT_GET]               = {'name':'Get',               'payloadLength': 0,  'resRequired': '0'}
messageTypeDict[LIGHT_SET_COLOR]         = {'name':'SetColor',          'payloadLength': 13, 'resRequired': '1'}
messageTypeDict[LIGHT_SET_WAVEFORM]      = {'name':'SetWaveform',       'payloadLength': 0,  'resRequired': '1'}
messageTypeDict[LIGHT_STATE]             = {'name':'State',             'payloadLength': 20, 'resRequired': '0'}
messageTypeDict[LIGHT_GET_POWER]         = {'name':'GetPower',          'payloadLength': 0,  'resRequired': '0'}
messageTypeDict[LIGHT_SET_POWER]         = {'name':'SetPower',          'payloadLength': 6,  'resRequired': '1'}
messageTypeDict[LIGHT_STATE_POWER]       = {'name':'StatePower',        'payloadLength': 2,  'resRequired': '0'}
messageTypeDict[LIGHT_GET_INFRARED]      = {'name':'GetInfrared',       'payloadLength': 0,  'resRequired': '0'}
messageTypeDict[LIGHT_STATE_INFRARED]    = {'name':'StateInfrared',     'payloadLength': 2,  'resRequired': '0'}
messageTypeDict[LIGHT_SET_INFRARED]      = {'name':'SetInfrared',       'payloadLength': 2,  'resRequired': '1'}
messageTypeDict[MZ_SET_COLOR_ZONES]      = {'name':'SetColorZones',     'payloadLength': 15, 'resRequired': '1'}
messageTypeDict[MZ_GET_COLOR_ZONES]      = {'name':'GetColorZones',     'payloadLength': 2,  'resRequired': '0'}
messageTypeDict[MZ_STATE_ZONE]           = {'name':'StateZone',         'payloadLength': 10, 'resRequired': '0'}
messageTypeDict[MZ_STATE_MULTI_ZONE]     = {'name':'StateMultiZone',    'payloadLength': 66, 'resRequired': '0'}