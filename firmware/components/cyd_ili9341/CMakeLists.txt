idf_component_register(SRCS "cyd_ili9341.c" INCLUDE_DIRS "include" REQUIRES esp_lcd esp_driver_spi esp_driver_gpio freertos heap)
if(NOT DEFINED HW3_LCD_BGR)
  set(HW3_LCD_BGR 0)
endif()
target_compile_definitions(${COMPONENT_LIB} PRIVATE LCD_BGR=${HW3_LCD_BGR})
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror -std=gnu17)

# C0: only the CONSOLE build increases its unique DMA buffer to 10240 bytes.
if(LOCO_CYD_PROFILE STREQUAL "CONSOLE")
  target_compile_definitions(${COMPONENT_LIB} PRIVATE CYD_LCD_DMA_CAPACITY_BYTES=10240U)
endif()
