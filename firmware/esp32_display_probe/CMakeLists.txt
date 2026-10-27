cmake_minimum_required(VERSION 3.16)

# HW3 is a standalone hardware/display probe. Do not pull in the BASIC core.
set(COMPONENTS main)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(loco_esp32_display_probe)
