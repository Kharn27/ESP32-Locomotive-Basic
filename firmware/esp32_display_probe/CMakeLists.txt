cmake_minimum_required(VERSION 3.16)
# HW4-C2 lives in the EXISTING display probe project and workspace.
# Default: native BASIC console; optional -DHW4_C2_CONSOLE=OFF builds the
# unchanged HW3/HW4 hardware calibration probe via its original main.c.
option(HW4_C2_CONSOLE "HW4-C2 interactive UART BASIC within display probe" ON)
set(EXTRA_COMPONENT_DIRS
    "${CMAKE_CURRENT_LIST_DIR}/../components"
    "${CMAKE_CURRENT_LIST_DIR}/../esp32_probe/components/loco_core")
set(COMPONENTS main loco_core cyd_ili9341)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(loco_esp32_display_probe)
