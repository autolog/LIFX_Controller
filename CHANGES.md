# Release Notes

## Version 4.0.5

* **Bug Fix**

Fix error with not enough parameters being passed to info message when
setting brightness value.

## Version 4.0.4

Enhanced in V4.0.4 (1st January 2017)

* **Infrared Support**

    Infrared LIFX lamps can have their infrared state controlled by Indigo. New infrared states added. Uses an updated version of a forked lifxlan library by Meghan Clark.

* **Turn ON IF OFF**

    Sets an optional default for a LIFX device to turn it on if it is off before applying change

* **Update Checker**

    Update checker (by JHeddings) added with new associated plugin config and plugin menu options.

Corrected in V4.0.4 (1st January 2017)

* **Product Models**

    LIFX Lamp product models now correctly identified and White only Lamps will now not show RGB controls

* **Preset Processing**

    Minor bug fixes and the ability to handle presets from earlier versions of the plugin

* **Bug Fixes**

    Minor bug fixes and code tidying.


## Version 4.0.2 (Version 4.0 Initial Release)

Enhanced in V4.0.2 (15th December 2016):

* **Indigo Controls**

    LIFX bulbs can now be controlled using Indigo 7's built-in RGBW UI controls.

* **LIFXLAN**

    The plugin has been extensively restructured and now uses a modified version of the very powerful lifxlan library (available on Github) by Megan Clarke.

* **Set Color / White**

    The set Color / White action has been extensively rewritten and now provides a powerful way to use actions to control LIFX lamps; standard and waveform (flashing) options are available.

* **Enhanced Error Checking**

    Handles communication errors more eefctively than previously

* **Event Log Messages**

    These messages are now more descriptive; indicating color, waveform parameters and duration of the requested command
