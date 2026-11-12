# HW4-DISP-PROFILE-A-C3 / B1-C2: strict build-time target, never runtime retuning.
# Included after profile_select.cmake, before ESP-IDF project(). Testable by cmake -P.
if(NOT DEFINED LOCO_CYD_PROFILE)
  message(FATAL_ERROR "HW4-DISP-C3 missing LOCO_CYD_PROFILE")
endif()

# CYD_LCD_SPI_HZ is an output (the effective HAL clock request), NOT an opt-in.
# An old CONSOLE build/CMakeCache.txt can retain SPI20 after switching branches.
# Use a separate, unambiguous switch for an intentional CONSOLE SPI20 fallback.
set(CYD_LCD_SPI20_OPT_IN OFF CACHE BOOL
    "Explicit CONSOLE fallback to LCD SPI20 (OFF: standard CONSOLE SPI40)")
if(NOT (CYD_LCD_SPI20_OPT_IN STREQUAL "ON" OR
        CYD_LCD_SPI20_OPT_IN STREQUAL "OFF"))
  message(FATAL_ERROR "HW4-DISP-C3 INVALID_SPI20_OPT_IN '${CYD_LCD_SPI20_OPT_IN}': expected ON or OFF")
endif()

# Refuse invalid old or command-line requests, including 55MHz; never mask them
# by normalizing the effective clock. The valid cached 20/40 are not evidence
# of an intentional fallback, since CMake does not record their provenance.
if(DEFINED CYD_LCD_SPI_HZ AND
   NOT (CYD_LCD_SPI_HZ STREQUAL "20000000" OR
        CYD_LCD_SPI_HZ STREQUAL "40000000"))
  message(FATAL_ERROR "HW4-DISP-C3 INVALID_SPI_HZ '${CYD_LCD_SPI_HZ}': only 20000000 or 40000000")
endif()
if(LOCO_CYD_PROFILE STREQUAL "CONSOLE")
  if(CYD_LCD_SPI20_OPT_IN STREQUAL "ON")
    set(_loco_spi_effective "20000000")
  else()
    set(_loco_spi_effective "40000000")
  endif()
else()
  if(CYD_LCD_SPI20_OPT_IN STREQUAL "ON")
    message(FATAL_ERROR "HW4-DISP-C3 SPI20_OPT_IN_CONSOLE_ONLY: ${LOCO_CYD_PROFILE} already requires SPI20")
  endif()
  if(DEFINED CYD_LCD_SPI_HZ AND CYD_LCD_SPI_HZ STREQUAL "40000000")
    message(FATAL_ERROR "HW4-DISP-C3 CONSOLE_ONLY: ${LOCO_CYD_PROFILE} must use SPI20")
  endif()
  set(_loco_spi_effective "20000000")
endif()

if(DEFINED CYD_LCD_SPI_HZ AND NOT CYD_LCD_SPI_HZ STREQUAL _loco_spi_effective)
  message(STATUS "HW4-DISP-C3 STALE_SPI_CACHE=${CYD_LCD_SPI_HZ} OVERRIDE=${_loco_spi_effective} SPI20_OPT_IN=${CYD_LCD_SPI20_OPT_IN}")
endif()
# FORCE is needed: set(... CACHE ...) without it preserves the stale SPI20.
set(CYD_LCD_SPI_HZ "${_loco_spi_effective}" CACHE STRING
    "LCD SPI clock requested (CONSOLE default 40MHz; HW3/BASIC_PROBE 20MHz)" FORCE)
set_property(CACHE CYD_LCD_SPI_HZ PROPERTY STRINGS 20000000 40000000)
message(STATUS "HW4-DISP-C3 BUILD_PROFILE=${LOCO_CYD_PROFILE} REQUESTED_SPI_HZ=${CYD_LCD_SPI_HZ} SPI20_OPT_IN=${CYD_LCD_SPI20_OPT_IN} ELECTRICAL_SPI_HZ=UNMEASURED")
