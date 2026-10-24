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

add_library(basic_executor STATIC core/basic_executor.c)
target_include_directories(basic_executor PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/core)
target_link_libraries(basic_executor PUBLIC basic_program)

add_library(basic_session_runtime STATIC core/basic_session_runtime.c)
target_include_directories(basic_session_runtime PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/core)
target_link_libraries(basic_session_runtime PUBLIC basic_session basic_executor)

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

    add_executable(test_basic_executor tests/test_basic_executor.c)
    target_link_libraries(test_basic_executor PRIVATE basic_executor basic_tokenizer)
    add_test(NAME basic_executor COMMAND test_basic_executor)

    add_executable(test_basic_session_runtime tests/test_basic_session_runtime.c)
    target_link_libraries(test_basic_session_runtime PRIVATE basic_session_runtime)
    add_test(NAME basic_session_runtime COMMAND test_basic_session_runtime)

    add_executable(test_basic_session tests/test_basic_session.c)
    target_link_libraries(test_basic_session PRIVATE basic_session)
    add_test(NAME basic_session COMMAND test_basic_session)
endif()

# J0.9 Linux host adapter. The core libraries remain platform-independent.
add_executable(loco_basic_cli host/loco_basic_cli.c)
target_link_libraries(loco_basic_cli PRIVATE basic_session_runtime)

if(BUILD_TESTING)
    # One seventh CTest suite, with ten real-process interaction scenarios.
    add_test(NAME host_cli COMMAND ${CMAKE_COMMAND}
        "-DCLI=$<TARGET_FILE:loco_basic_cli>"
        "-DTEST_TEMP_DIR=${CMAKE_CURRENT_BINARY_DIR}"
        -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/test_loco_basic_cli.cmake")
endif()
