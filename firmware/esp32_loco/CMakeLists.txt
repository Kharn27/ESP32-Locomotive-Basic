cmake_minimum_required(VERSION 3.16)
# HW4-C1 is a third standalone image. Keep the original two test benches.
set(EXTRA_COMPONENT_DIRS
    "${CMAKE_CURRENT_LIST_DIR}/../components"
    "${CMAKE_CURRENT_LIST_DIR}/../esp32_probe/components/loco_core")
set(COMPONENTS main loco_core cyd_ili9341)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(loco_esp32_loco)
