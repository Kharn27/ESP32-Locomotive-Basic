idf_component_register(
    SRCS "main.c"
    INCLUDE_DIRS "."
    REQUIRES loco_core heap freertos esp_system
)
target_compile_options(${COMPONENT_LIB} PRIVATE -std=c99)
