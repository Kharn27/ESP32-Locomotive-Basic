cmake_minimum_required(VERSION 3.13)
project(loco_cyd_basic_core C)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

option(BP_SANITIZERS "Enable address/undefined sanitizers on GCC/Clang" OFF)
if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
    add_compile_options(-Wall -Wextra -Wpedantic -Wconversion -Werror)
    if(BP_SANITIZERS)
        add_compile_options(-fsanitize=address,undefined -fno-omit-frame-pointer)
        add_link_options(-fsanitize=address,undefined)
    endif()
endif()

add_library(basic_program STATIC core/basic_program.c)
target_include_directories(basic_program PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/core)

add_library(basic_listing STATIC core/basic_listing.c)
target_include_directories(basic_listing PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/core)
target_link_libraries(basic_listing PUBLIC basic_program)

add_library(basic_tokenizer STATIC core/basic_tokenizer.c)
target_include_directories(basic_tokenizer PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/core)

add_library(basic_session STATIC core/basic_session.c)
target_include_directories(basic_session PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/core)
target_link_libraries(basic_session PUBLIC basic_tokenizer basic_listing basic_program)

include(CTest)
if(BUILD_TESTING)
    add_executable(test_basic_program tests/test_basic_program.c)
    target_link_libraries(test_basic_program PRIVATE basic_program)
    add_test(NAME basic_program COMMAND test_basic_program)

    add_executable(test_basic_tokenizer tests/test_basic_tokenizer.c)
    target_link_libraries(test_basic_tokenizer PRIVATE basic_tokenizer basic_program)
    add_test(NAME basic_tokenizer COMMAND test_basic_tokenizer)

    add_executable(test_basic_listing tests/test_basic_listing.c)
    target_link_libraries(test_basic_listing PRIVATE basic_listing basic_tokenizer)
    add_test(NAME basic_listing COMMAND test_basic_listing)

    add_executable(test_basic_session tests/test_basic_session.c)
    target_link_libraries(test_basic_session PRIVATE basic_session)
    add_test(NAME basic_session COMMAND test_basic_session)
endif()
