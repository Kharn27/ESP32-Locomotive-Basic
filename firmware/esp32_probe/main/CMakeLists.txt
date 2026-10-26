idf_component_register(
    SRCS "main.c"
    INCLUDE_DIRS "."
    REQUIRES loco_core heap freertos esp_system
)
# ESP-IDF Xtensa/FreeRTOS headers use GNU inline 'asm'. Keep the portable
# loco_core component in strict C99; only the HAL-facing adapter is gnu99.
target_compile_options(${COMPONENT_LIB} PRIVATE -std=gnu99)
