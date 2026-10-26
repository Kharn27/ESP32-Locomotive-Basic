cmake_minimum_required(VERSION 3.16)
# Restrict the build graph to the probe and its declared transitive deps.
# With IDF v5.5, Wi-Fi Kconfig ESP_WIFI_ENABLED is an unprompted
# default-y symbol; removing the esp_wifi component prevents inclusion.
set(COMPONENTS main)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(loco_esp32_probe)
