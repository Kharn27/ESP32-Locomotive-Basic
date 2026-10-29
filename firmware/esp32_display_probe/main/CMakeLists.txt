# ESP-IDF's component_get_requirements.cmake evaluates this file in a
# separate CMake process where ordinary project cache variables may be absent.
# For that requirements-only scan, CONSOLE supplies the complete dependency
# superset (UART + video + core + LCD). The real project() configuration gets
# the validated LOCO_CYD_PROFILE from ../profile_select.cmake and selects the
# actual single app_main below.
if(NOT DEFINED LOCO_CYD_PROFILE)
    set(LOCO_CYD_PROFILE CONSOLE)
endif()

# ARCH-HW4-U1-B: exactly one app_main per image; all sources are borrowed
# from their original locations or the relocated unmodified BASIC probe.
if(LOCO_CYD_PROFILE STREQUAL "CONSOLE")
    idf_component_register(
        SRCS
            "hw4_c2_console.c" "cpc_font.c"
            "../../../video/cpc_video.c" "../../../video/cpc_palette.c" "../../../video/cpc_boot.c"
            "../../../video/cpc_text.c" "../../../io/cpc_uart_console.c"
            "../../../io/uart_line.c" "../../../io/cpc_screen_nav.c"
            "../../../io/cpc_ready_policy.c" "../../../io/cpc_diag_policy.c"
        INCLUDE_DIRS "." "../../../video" "../../../io"
        REQUIRES loco_core cyd_ili9341 esp_driver_uart
                 freertos heap esp_system esp_app_format
    )
elseif(LOCO_CYD_PROFILE STREQUAL "HW3")
    idf_component_register(
        SRCS "main.c" "cpc_font.c"
             "../../../video/cpc_video.c" "../../../video/cpc_palette.c" "../../../video/cpc_boot.c"
        INCLUDE_DIRS "." "../../../video"
        REQUIRES loco_core cyd_ili9341 esp_driver_uart freertos heap esp_system esp_app_format
    )
elseif(LOCO_CYD_PROFILE STREQUAL "BASIC_PROBE")
    # Relocated J0.25/J1.2-HW2 source, unchanged ABI/NMIN/REAL5 behavior.
    idf_component_register(
        SRCS "basic_probe.c"
        INCLUDE_DIRS "."
        REQUIRES loco_core cyd_ili9341 heap freertos esp_system esp_app_format
    )
else()
    message(FATAL_ERROR "U1-A unknown profile in main component: ${LOCO_CYD_PROFILE}")
endif()

if(LOCO_CYD_PROFILE STREQUAL "BASIC_PROBE")
    # Same compiler dialect as the legacy standalone probe.
    target_compile_options(${COMPONENT_LIB} PRIVATE -std=gnu17)
else()
    # Original board-calibration flags remain available in CONSOLE and HW3.
    if(NOT DEFINED HW3_SWAP_XY)
        set(HW3_SWAP_XY 1)
    endif()
    if(NOT DEFINED HW3_LCD_BGR)
        set(HW3_LCD_BGR 0)
    endif()
    if(NOT DEFINED HW3_MIRROR_X)
        set(HW3_MIRROR_X 0)
    endif()
    if(NOT DEFINED HW3_MIRROR_Y)
        set(HW3_MIRROR_Y 1)
    endif()
    target_compile_definitions(${COMPONENT_LIB} PRIVATE
        HW3_SWAP_XY=${HW3_SWAP_XY}
        HW3_LCD_BGR=${HW3_LCD_BGR}
        HW3_MIRROR_X=${HW3_MIRROR_X}
        HW3_MIRROR_Y=${HW3_MIRROR_Y}
    )
    target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror -std=gnu17)
endif()
