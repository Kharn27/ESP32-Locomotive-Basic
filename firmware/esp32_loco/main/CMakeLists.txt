# HW4-C1: one app_main, the existing native BASIC core and shared LCD driver.
idf_component_register(
    SRCS
        "main.c"
        "../../esp32_display_probe/main/cpc_font.c"
        "../../../video/cpc_video.c"
        "../../../video/cpc_palette.c"
        "../../../video/cpc_text.c"
    INCLUDE_DIRS
        "." "../../esp32_display_probe/main" "../../../video"
    REQUIRES loco_core cyd_ili9341 heap freertos esp_system esp_app_format
)
# ESP-IDF headers need GNU extensions; core/ and video/ stay portable C99.
target_compile_options(${COMPONENT_LIB} PRIVATE -std=gnu17 -Wall -Wextra -Werror)
