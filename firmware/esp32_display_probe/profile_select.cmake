# ARCH-HW4-U1-A: select exactly one app_main before ESP-IDF loads components.
# Fresh build:
#   no flags                -> CONSOLE
#   -DHW4_C2_CONSOLE=ON/OFF  -> CONSOLE/HW3 (historical alias)
#   -DLOCO_CYD_PROFILE=...   -> CONSOLE/HW3/BASIC_PROBE
# An existing cache carries both selectors; contradictory requests fail closed.
# The BASIC_PROBE profile has no HW4_C2_CONSOLE counterpart.
if(DEFINED HW4_C2_CONSOLE)
    string(TOUPPER "${HW4_C2_CONSOLE}" _loco_legacy)
    set(_loco_true ON TRUE YES Y 1)
    set(_loco_false OFF FALSE NO N 0)
    # list(FIND) works in both normal ESP-IDF configure and cmake -P probes.
    list(FIND _loco_true "${_loco_legacy}" _loco_true_index)
    list(FIND _loco_false "${_loco_legacy}" _loco_false_index)
    if(NOT _loco_true_index EQUAL -1)
        set(_loco_legacy_profile CONSOLE)
    elseif(NOT _loco_false_index EQUAL -1)
        set(_loco_legacy_profile HW3)
    else()
        message(FATAL_ERROR "U1-A invalid HW4_C2_CONSOLE='${HW4_C2_CONSOLE}' (expected ON/OFF)")
    endif()
endif()

if(NOT DEFINED LOCO_CYD_PROFILE)
    if(DEFINED _loco_legacy_profile)
        set(LOCO_CYD_PROFILE "${_loco_legacy_profile}")
    else()
        set(LOCO_CYD_PROFILE CONSOLE)
    endif()
endif()
set(LOCO_CYD_PROFILE "${LOCO_CYD_PROFILE}" CACHE STRING
    "LOCO-CYD firmware profile: CONSOLE (default), HW3, BASIC_PROBE")
set_property(CACHE LOCO_CYD_PROFILE PROPERTY STRINGS CONSOLE HW3 BASIC_PROBE)

if(NOT LOCO_CYD_PROFILE STREQUAL "CONSOLE" AND
   NOT LOCO_CYD_PROFILE STREQUAL "HW3" AND
   NOT LOCO_CYD_PROFILE STREQUAL "BASIC_PROBE")
    message(FATAL_ERROR "U1-A invalid LOCO_CYD_PROFILE='${LOCO_CYD_PROFILE}' (expected CONSOLE, HW3 or BASIC_PROBE)")
endif()

if(DEFINED _loco_legacy_profile)
    if(LOCO_CYD_PROFILE STREQUAL "BASIC_PROBE" OR
       NOT LOCO_CYD_PROFILE STREQUAL _loco_legacy_profile)
        message(FATAL_ERROR
            "U1-A conflicting selectors: LOCO_CYD_PROFILE=${LOCO_CYD_PROFILE} "
            "and HW4_C2_CONSOLE=${HW4_C2_CONSOLE}; use an isolated profile build "
            "or specify matching CONSOLE/ON or HW3/OFF")
    endif()
elseif(LOCO_CYD_PROFILE STREQUAL "CONSOLE")
    set(HW4_C2_CONSOLE ON CACHE BOOL "Legacy HW4-C2 ON=CONSOLE, OFF=HW3")
elseif(LOCO_CYD_PROFILE STREQUAL "HW3")
    set(HW4_C2_CONSOLE OFF CACHE BOOL "Legacy HW4-C2 ON=CONSOLE, OFF=HW3")
endif()

if(DEFINED HW4_C2_CONSOLE)
    message(STATUS "LOCO_CYD_SELECTED=${LOCO_CYD_PROFILE} LEGACY_HW4_C2_CONSOLE=${HW4_C2_CONSOLE}")
else()
    message(STATUS "LOCO_CYD_SELECTED=${LOCO_CYD_PROFILE} LEGACY_HW4_C2_CONSOLE=UNSET")
endif()
