# LIFX Controller

Plugin for the Indigo Home Automation system.

The LIFX Controller plugin enables you to control LIFX devices directly from Indigo. It provides local LAN control of LIFX Devices without having to use an internet connection. It is implemented using an Indigo Dimmer device to control the LIFX device and fully supports the built-in RGBW controls in Indigo 2022.1. In addition to the standard controls, the plugin provides a comprehensive action (Set Color/White) to control all aspects of the LIFX device and a number of additional actions.

| Requirement            |                     |   |
|------------------------|---------------------|---|
| Minimum Indigo Version | 2022.1              |   |
| Python Library (API)   | Third Party | LIFXLAN [see note below]  |
| Requires Local Network | Yes                 |   |
| Requires Internet      | No            	   |   |
| Hardware Interface     | None                |   |

## Quick Start

1. Install Plugin
2. Let plugin discover and create LIFX devices

Note: The plugin makes extensive use of the [lifxlan library][2] by Meghan Clark for which much thanks are due :)

[1]: https://www.lifx.com
[2]: https://github.com/mclarkk/lifxlan



**PluginID**: com.autologplugin.indigoplugin.lifxcontroller