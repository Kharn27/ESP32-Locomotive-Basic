cmake_minimum_required(VERSION 3.16)

# HW3 is a standalone hardware/display probe. Do not pull in the BASIC core.
set(EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_LIST_DIR}/../components")
set(COMPONENTS main cyd_ili9341)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(loco_esp32_display_probe)
