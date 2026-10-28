# ARCH-HW4-U1-A: exactly one app_main per image; all sources are borrowed
# from their original locations. The old esp32_probe project remains buildable.
if(LOCO_CYD_PROFILE STREQUAL "CONSOLE")
    idf_component_register(
        SRCS
            "hw4_c2_console.c" "cpc_font.c"
            "../../../video/cpc_video.c" "../../../video/cpc_palette.c" "../../../video/cpc_boot.c"
            "../../../video/cpc_text.c" "../../../io/cpc_uart_console.c"
            "../../../io/uart_line.c"
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
    # Reuse the precise J0.25/J1.2-HW2 implementation, including its ABI table
    # and NMIN/REAL5 checks; do not copy it into this component.
    idf_component_register(
        SRCS "../../esp32_probe/main/main.c"
        INCLUDE_DIRS "." "../../esp32_probe/main"
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
