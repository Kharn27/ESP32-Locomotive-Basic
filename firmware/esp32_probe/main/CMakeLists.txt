idf_component_register(
    SRCS "main.c"
    INCLUDE_DIRS "."
    REQUIRES loco_core cyd_ili9341 heap freertos esp_system esp_app_format
)
# ESP-IDF esp_app_desc.h uses C11 static_assert, and Xtensa/FreeRTOS
# headers require GNU inline 'asm'. Only this HAL probe uses gnu17.
# The portable loco_core component remains strict C99.
target_compile_options(${COMPONENT_LIB} PRIVATE -std=gnu17)
