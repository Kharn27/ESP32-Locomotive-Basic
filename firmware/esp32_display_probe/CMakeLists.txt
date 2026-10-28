cmake_minimum_required(VERSION 3.16)
# U1-B: the only ESP-IDF project remains the existing PO/VS Code path.
# Selection is deliberately resolved before project() / component discovery.
include("${CMAKE_CURRENT_LIST_DIR}/profile_select.cmake")
set(EXTRA_COMPONENT_DIRS
    "${CMAKE_CURRENT_LIST_DIR}/../components")
set(COMPONENTS main loco_core cyd_ili9341)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(loco_esp32_display_probe)
