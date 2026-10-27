idf_component_register(
    SRCS "main.c" "cpc_font.c"
    INCLUDE_DIRS "."
    REQUIRES esp_lcd esp_driver_spi esp_driver_gpio freertos heap esp_system
)

# Board variations: -DHW3_SWAP_XY=1 -DHW3_MIRROR_X=0 -DHW3_MIRROR_Y=1 (landscape candidate).
# CMake options are genuinely forwarded to the C preprocessor below.
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
