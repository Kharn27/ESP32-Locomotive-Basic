idf_component_register(SRCS "cyd_ili9341.c" INCLUDE_DIRS "include" REQUIRES esp_lcd esp_driver_spi esp_driver_gpio freertos heap esp_timer)
if(NOT DEFINED HW3_LCD_BGR)
  set(HW3_LCD_BGR 0)
endif()
# Requirements-only component discovery can lack root cache; retain safe 20MHz
# there. During the real configure, the root selector supplies the exact clock.
if(NOT DEFINED CYD_LCD_SPI_HZ)
  set(CYD_LCD_SPI_HZ "20000000")
endif()
if(NOT (CYD_LCD_SPI_HZ STREQUAL "20000000" OR
        CYD_LCD_SPI_HZ STREQUAL "40000000"))
  message(FATAL_ERROR "HW4-DISP-C3 invalid LCD clock")
endif()
if(DEFINED LOCO_CYD_PROFILE AND
   NOT LOCO_CYD_PROFILE STREQUAL "CONSOLE" AND
   CYD_LCD_SPI_HZ STREQUAL "40000000")
  message(FATAL_ERROR "HW4-DISP-C3 40MHz CONSOLE only")
endif()
target_compile_definitions(${COMPONENT_LIB} PRIVATE
  LCD_BGR=${HW3_LCD_BGR} LCD_CLOCK_HZ=${CYD_LCD_SPI_HZ}U)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wall -Wextra -Werror -std=gnu17)
