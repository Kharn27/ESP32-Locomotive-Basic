# Both variants share this EXISTING ESP-IDF project and LCD driver.
# Exactly ONE of the following sources provides app_main.
if(HW4_C2_CONSOLE)
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
else()
    # Original HW3-C5/HW4 display probe, unchanged source main.c.
    idf_component_register(
        SRCS "main.c" "cpc_font.c"
             "../../../video/cpc_video.c" "../../../video/cpc_palette.c" "../../../video/cpc_boot.c"
        INCLUDE_DIRS "." "../../../video"
        REQUIRES loco_core cyd_ili9341 esp_driver_uart freertos heap esp_system esp_app_format
    )
endif()
# Original board-calibration flags remain available for the probe variant.
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
