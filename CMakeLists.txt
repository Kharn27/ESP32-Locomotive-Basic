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
target_link_libraries(basic_listing PUBLIC basic_program basic_variable_ref)

add_library(basic_tokenizer STATIC core/basic_tokenizer.c)
target_include_directories(basic_tokenizer PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/core)
target_link_libraries(basic_tokenizer PUBLIC basic_variable_ref)

add_library(basic_executor STATIC core/basic_executor.c)
target_include_directories(basic_executor PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/core)
target_link_libraries(basic_executor PUBLIC basic_program basic_variable_binding)

add_library(basic_session_runtime STATIC core/basic_session_runtime.c)
target_include_directories(basic_session_runtime PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/core)
target_link_libraries(basic_session_runtime PUBLIC basic_session basic_executor)

add_library(basic_session STATIC core/basic_session.c)
target_include_directories(basic_session PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/core)
target_link_libraries(basic_session PUBLIC basic_tokenizer basic_listing basic_program)

include(CTest)
# Labels are scheduled after the complete CMakeLists has registered all tests.
if(BUILD_TESTING)
    include(cmake/CTestLabels.cmake)
endif()
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

# J0.11: program termination integrated through tokenizer, listing and executor.
if(BUILD_TESTING)
    add_executable(test_basic_termination tests/test_basic_termination.c)
    target_link_libraries(test_basic_termination PRIVATE basic_session_runtime)
    add_test(NAME termination COMMAND test_basic_termination)
endif()

# J0.10: end-to-end numbered comments on the existing native stack.
if(BUILD_TESTING)
    add_executable(test_basic_comments tests/test_basic_comments.c)
    target_link_libraries(test_basic_comments PRIVATE basic_session_runtime)
    add_test(NAME comments COMMAND test_basic_comments)
endif()

# J0.13: isolated, reusable decoder of CPC scalar variable references.
add_library(basic_variable_ref STATIC core/basic_variable_ref.c)
target_include_directories(basic_variable_ref PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/core)

if(BUILD_TESTING)
    add_executable(test_basic_variable_ref tests/test_basic_variable_ref.c)
    target_link_libraries(test_basic_variable_ref PRIVATE basic_variable_ref)
    add_test(NAME basic_variable_ref COMMAND test_basic_variable_ref)
endif()

# J0.14: independent implicit type table and typed canonical variable names.
add_library(basic_variable_types STATIC core/basic_variable_types.c)
target_include_directories(basic_variable_types PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/core)
target_link_libraries(basic_variable_types PUBLIC basic_variable_ref)

if(BUILD_TESTING)
    add_executable(test_basic_variable_types tests/test_basic_variable_types.c)
    target_link_libraries(test_basic_variable_types PRIVATE basic_variable_types)
    add_test(NAME basic_variable_types COMMAND test_basic_variable_types)
endif()

# J0.15: bounded scalar store, separate from the BASIC runtime.
add_library(basic_variable_store STATIC core/basic_variable_store.c)
target_include_directories(basic_variable_store PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/core)
target_link_libraries(basic_variable_store PUBLIC basic_variable_types)

if(BUILD_TESTING)
    add_executable(test_basic_variable_store tests/test_basic_variable_store.c)
    target_link_libraries(test_basic_variable_store PRIVATE basic_variable_store)
    add_test(NAME basic_variable_store COMMAND test_basic_variable_store)
endif()


# J0.16: thirteenth suite, explicit scalar references in PRINT/LIST only.
if(BUILD_TESTING)
    add_executable(test_basic_explicit_variable_tokens tests/test_basic_explicit_variable_tokens.c)
    target_link_libraries(test_basic_explicit_variable_tokens PRIVATE
                          basic_variable_ref basic_session_runtime)
    add_test(NAME explicit_variable_tokens COMMAND test_basic_explicit_variable_tokens)
endif()


# J0.17: native, side-effect-free explicit scalar reference to store binding.
add_library(basic_variable_binding STATIC core/basic_variable_binding.c)
target_include_directories(basic_variable_binding PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/core)
target_link_libraries(basic_variable_binding PUBLIC basic_variable_ref
                      basic_variable_types basic_variable_store)

if(BUILD_TESTING)
    add_executable(test_basic_variable_binding tests/test_basic_variable_binding.c)
    target_link_libraries(test_basic_variable_binding PRIVATE basic_variable_binding)
    add_test(NAME basic_variable_binding COMMAND test_basic_variable_binding)
endif()

# J0.18: fifteenth CTest suite, CPC INTEGER assignment token representations.
if(BUILD_TESTING)
    add_executable(test_basic_integer_assignment_tokens
                   tests/test_basic_integer_assignment_tokens.c)
    target_link_libraries(test_basic_integer_assignment_tokens PRIVATE
                          basic_variable_store basic_session_runtime)
    add_test(NAME integer_assignment_tokens COMMAND test_basic_integer_assignment_tokens)
endif()

# J0.19: sixteenth suite, execution of standalone INTEGER assignments.
if(BUILD_TESTING)
    add_executable(test_basic_integer_assignment_runtime
                   tests/test_basic_integer_assignment_runtime.c)
    target_link_libraries(test_basic_integer_assignment_runtime PRIVATE
                          basic_session_runtime basic_variable_binding)
    add_test(NAME integer_assignment_runtime COMMAND test_basic_integer_assignment_runtime)
endif()

# J0.20: seventeenth suite, read-only PRINT of explicit CPC INTEGER scalars.
if(BUILD_TESTING)
    add_executable(test_basic_integer_variable_print
                   tests/test_basic_integer_variable_print.c)
    target_link_libraries(test_basic_integer_variable_print PRIVATE
                          basic_session_runtime basic_variable_binding)
    add_test(NAME integer_variable_print COMMAND test_basic_integer_variable_print)
endif()

# J0.21: eighteenth CTest suite, token-only INTEGER source-reference addition.
if(BUILD_TESTING)
    add_executable(test_basic_integer_expression_tokens
                   tests/test_basic_integer_expression_tokens.c)
    target_link_libraries(test_basic_integer_expression_tokens PRIVATE
                          basic_session_runtime basic_variable_binding)
    add_test(NAME integer_expression_tokens COMMAND test_basic_integer_expression_tokens)
endif()

# J0.22: nineteenth CTest suite, bounded native INTEGER addition.
if(BUILD_TESTING)
    add_executable(test_basic_integer_expression_runtime
                   tests/test_basic_integer_expression_runtime.c)
    target_link_libraries(test_basic_integer_expression_runtime PRIVATE
                          basic_session_runtime basic_variable_binding)
    add_test(NAME integer_expression_runtime COMMAND test_basic_integer_expression_runtime)
endif()

# J0.23: architecture-native ABI inventory; no ESP32 HAL or core mutation.
add_executable(basic_memory_budget tools/basic_memory_budget.c)
target_include_directories(basic_memory_budget PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/core)
if(BUILD_TESTING)
    add_test(NAME memory_budget COMMAND basic_memory_budget)
endif()

# J0.24: independent historical fixtures when present; no emulator or ROM in CI.
add_executable(basic_program_image_cli tools/basic_program_image_cli.c)
target_link_libraries(basic_program_image_cli PRIVATE basic_session)
if(BUILD_TESTING)
    find_package(Python3 COMPONENTS Interpreter REQUIRED)
    add_test(NAME cpc_differential_infrastructure COMMAND
        ${Python3_EXECUTABLE} "${CMAKE_CURRENT_SOURCE_DIR}/tools/cpc_diff.py"
        --manifest "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/cpc6128/manifest.json"
        --cli "$<TARGET_FILE:loco_basic_cli>"
        --image-cli "$<TARGET_FILE:basic_program_image_cli>" --ci)
endif()

# J0.24-C2: permanently versioned CPC evidence; no Caprice32/ROM needed.
# The previous 21 suites remain unchanged; this is an additional integrity gate.
if(BUILD_TESTING)
    add_test(NAME cpc_persistent_evidence COMMAND
        ${Python3_EXECUTABLE} "${CMAKE_CURRENT_SOURCE_DIR}/tools/cpc_evidence.py"
        --self-test)
endif()

# J0.24-C3: verify genuine CPC program-only fixtures and SHA provenance.
# All 22 previous portable C99 test suites remain unchanged.
if(BUILD_TESTING)
    add_test(NAME cpc_token_permanent_evidence COMMAND
        ${Python3_EXECUTABLE} "${CMAKE_CURRENT_SOURCE_DIR}/tools/cpc_token_evidence.py"
        --permanent --self-test)
endif()

# J0.24-C6: twenty-fourth CTest suite, immutable CPC RUN/printer oracle.
# The C99 core and twenty-three preceding suites are unchanged.
if(BUILD_TESTING)
    add_test(NAME cpc_run_behavior_permanent_evidence COMMAND
        ${Python3_EXECUTABLE} "${CMAKE_CURRENT_SOURCE_DIR}/tests/oracles/cpc_run_evidence.py"
        --evidence "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/cpc6128/run_behavior"
        --permanent --self-test)
endif()

# J0.24-C7: twenty-fifth portable CTest suite, immutable CPC LIST printer
# evidence and coordinated-tamper negative probes. No emulator needed locally.
if(BUILD_TESTING)
    add_test(NAME cpc_list_printer_permanent_evidence COMMAND
        ${Python3_EXECUTABLE} "${CMAKE_CURRENT_SOURCE_DIR}/tests/oracles/cpc_list_evidence.py"
        --evidence "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/cpc6128/list_printer"
        --permanent --self-test)
endif()

# J0.24-C8: twenty-sixth portable CTest suite. Genuine CPC screen PNGs
# are visual evidence only; this test verifies SHA/provenance, not text bytes.
# The 25 previous CTest suites are preserved unchanged.
if(BUILD_TESTING)
    add_test(NAME cpc_list_screen_permanent_evidence COMMAND
        ${Python3_EXECUTABLE} "${CMAKE_CURRENT_SOURCE_DIR}/tests/oracles/cpc_screen_evidence.py"
        --evidence "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/cpc6128/list_screen"
        --permanent --self-test)
endif()

# J0.26: exit evidence audit is NOT an automatic phase transition.
# Check real archived bytes, approved validators and deliberate negative mutations.
if(BUILD_TESTING)
    add_test(NAME j0_exit_evidence_audit COMMAND
        ${Python3_EXECUTABLE} "${CMAKE_CURRENT_SOURCE_DIR}/tools/j0_exit_audit.py"
        --self-test)
endif()


# J0.27-A: the oracle evidence is permanent, independently approved, and
# required. CTest fails closed if a source/PNG/printer byte/manifest is absent.
if(BUILD_TESTING)
    find_package(Python3 COMPONENTS Interpreter REQUIRED)
    add_test(NAME numeric_print_provenance
        COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_SOURCE_DIR}/tests/oracles/numeric_print_evidence.py"
            --evidence "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/cpc6128/numeric_print"
            --permanent --self-test)
endif()

# J0.27-B2: approved historical six-case printer bytes sealed in Git.
# Portable on Linux with/without sanitizers; no ROM/emulator required.
if(BUILD_TESTING)
    add_test(NAME cpc_signed_print_permanent_evidence COMMAND
        ${Python3_EXECUTABLE}
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/oracles/signed_print_evidence.py"
        --evidence "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/cpc6128/signed_print"
        --permanent --self-test)
endif()

# J0.28: live CLI token/LIST/RUN and post-C1 INTEGER presentation audit.
# Does not change historical classifications or authorize J0/J1 transition.
if(BUILD_TESTING)
    add_test(NAME j0_post_c1_gate_audit COMMAND
        ${Python3_EXECUTABLE} "${CMAKE_CURRENT_SOURCE_DIR}/tools/j0_post_c1_audit.py"
        --cli "$<TARGET_FILE:loco_basic_cli>"
        --image-cli "$<TARGET_FILE:basic_program_image_cli>" --self-test)
endif()

# J1.1: historical CPC RAM oracle for signed INTEGER assignments, independent
# of the host tokenizer; each binary fixture is pinned by explicit SHA-256.
if(BUILD_TESTING)
    add_test(NAME j1_signed_assignment_differential COMMAND
        ${Python3_EXECUTABLE} "${CMAKE_CURRENT_SOURCE_DIR}/tools/j1_signed_assignment_audit.py"
        --cli "$<TARGET_FILE:loco_basic_cli>"
        --image-cli "$<TARGET_FILE:basic_program_image_cli>" --self-test)
endif()

# J1.2-B: separate current/native capability and regression suite.
# Historical J1.2-A sealed proof and its original statuses remain untouched.
if(BUILD_TESTING)
    add_executable(test_basic_integer16 tests/test_basic_integer16.c)
    target_link_libraries(test_basic_integer16 PRIVATE basic_session_runtime
                          basic_variable_binding)
    add_test(NAME integer16_literals COMMAND test_basic_integer16)
    add_test(NAME j1_2_b_native_cpc_differential
        COMMAND ${Python3_EXECUTABLE} "${CMAKE_CURRENT_SOURCE_DIR}/tools/j1_2_b_native_verify.py"
        --cli "$<TARGET_FILE:loco_basic_cli>"
        --image-cli "$<TARGET_FILE:basic_program_image_cli>" --self-test)
    add_test(NAME j1_2_a_historical_boundary_seal
        COMMAND ${Python3_EXECUTABLE} "${CMAKE_CURRENT_SOURCE_DIR}/tools/j1_2_boundary_verify.py"
        --permanent --self-test)
endif()

# J1.2-C: NMIN REAL5 INTEGER boundary; archive remains immutable.
if(BUILD_TESTING)
    add_executable(test_basic_integer_min tests/test_basic_integer_min.c)
    target_link_libraries(test_basic_integer_min PRIVATE basic_session_runtime
                          basic_variable_binding)
    add_test(NAME integer_min_real5 COMMAND test_basic_integer_min)
    add_test(NAME j1_2_c_nmin_cpc_differential
        COMMAND ${Python3_EXECUTABLE} "${CMAKE_CURRENT_SOURCE_DIR}/tools/j1_2_c_native_verify.py"
        --cli "$<TARGET_FILE:loco_basic_cli>"
        --image-cli "$<TARGET_FILE:basic_program_image_cli>" --self-test)
endif()

# J1.3-B: live native INTEGER subtraction; CPC J1.3-A archives are READ ONLY.
if(BUILD_TESTING)
    add_executable(test_basic_integer_subtraction
                   tests/test_basic_integer_subtraction.c)
    target_link_libraries(test_basic_integer_subtraction PRIVATE
                          basic_session_runtime basic_variable_binding)
    add_test(NAME integer_subtraction_f5 COMMAND test_basic_integer_subtraction)
    add_test(NAME j1_3_b_native_cpc_differential
        COMMAND ${Python3_EXECUTABLE}
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/j1_3_b_native_verify.py"
        --cli "$<TARGET_FILE:loco_basic_cli>"
        --image-cli "$<TARGET_FILE:basic_program_image_cli>" --self-test)
endif()

# J1.4-B: bounded native F6 multiplication; historical J1.4-A stays immutable.
if(BUILD_TESTING)
    add_executable(test_basic_integer_multiplication
                   tests/test_basic_integer_multiplication.c)
    target_link_libraries(test_basic_integer_multiplication PRIVATE
                          basic_session_runtime basic_variable_binding)
    add_test(NAME integer_multiplication_f6 COMMAND test_basic_integer_multiplication)
    add_test(NAME j1_4_b_native_cpc_differential COMMAND
        ${Python3_EXECUTABLE}
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/j1_4_b_native_verify.py"
        --cli "$<TARGET_FILE:loco_basic_cli>"
        --image-cli "$<TARGET_FILE:basic_program_image_cli>" --self-test)
endif()

# J1.5-B: native F9 INTEGER division, immutable J1.5-A ROM acquisition.
# Existing 40 suites remain unchanged; archive and historical classification read-only.
if(BUILD_TESTING)
    add_executable(test_basic_integer_division
                   tests/test_basic_integer_division.c)
    target_link_libraries(test_basic_integer_division PRIVATE
                          basic_session_runtime basic_variable_binding)
    add_test(NAME integer_division_f9 COMMAND test_basic_integer_division)
    add_test(NAME j1_5_b_native_cpc_differential COMMAND
        ${Python3_EXECUTABLE}
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/j1_5_b_native_verify.py"
        --cli "$<TARGET_FILE:loco_basic_cli>"
        --image-cli "$<TARGET_FILE:basic_program_image_cli>" --self-test)
endif()

# HW4-A: isolated portable CPC video contract, independent of BASIC.
add_library(cpc_video STATIC video/cpc_video.c video/cpc_palette.c)
target_include_directories(cpc_video PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/video)
add_executable(test_cpc_video tests/test_cpc_video.c)
target_link_libraries(test_cpc_video PRIVATE cpc_video)
add_executable(cpc_video_ppm tools/cpc_video_ppm.c)
target_link_libraries(cpc_video_ppm PRIVATE cpc_video)
if(BUILD_TESTING)
    add_test(NAME cpc_video COMMAND test_cpc_video)
    add_test(NAME cpc_video_ppm_determinism COMMAND
        ${Python3_EXECUTABLE}
        "${CMAKE_CURRENT_SOURCE_DIR}/tests/test_cpc_video_ppm.py"
        "$<TARGET_FILE:cpc_video_ppm>"
        "${CMAKE_CURRENT_BINARY_DIR}/hw4_preview_verified")
endif()

# J1.6-B: CPC FB MOD INTEGER, immutable J1.6-A original evidence only.
# Two new portable suites, preserving all 42 previous regressions unchanged.
if(BUILD_TESTING)
    add_executable(test_basic_integer_mod tests/test_basic_integer_mod.c)
    target_link_libraries(test_basic_integer_mod PRIVATE
                          basic_session_runtime basic_variable_binding)
    add_test(NAME integer_mod_fb COMMAND test_basic_integer_mod)
    add_test(NAME j1_6_b_native_cpc_differential COMMAND
        ${Python3_EXECUTABLE}
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/j1_6_b_native_verify.py"
        --cli "$<TARGET_FILE:loco_basic_cli>"
        --image-cli "$<TARGET_FILE:basic_program_image_cli>" --self-test)
endif()


# HW4-C1: native BASIC output bytes -> portable MODE 1 text adapter -> VRAM.
# Independent Linux verification, no ROM, TFT transport, heap or fixture edits.
add_library(cpc_text STATIC video/cpc_text.c)
target_include_directories(cpc_text PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/video)
target_link_libraries(cpc_text PUBLIC cpc_video)
if(BUILD_TESTING)
    add_executable(test_cpc_text tests/test_cpc_text.c)
    target_link_libraries(test_cpc_text PRIVATE cpc_text)
    add_test(NAME hw4_c1_text_boundaries COMMAND test_cpc_text)

    add_executable(test_hw4_c1_integration tests/test_hw4_c1_integration.c)
    target_link_libraries(test_hw4_c1_integration PRIVATE
                          cpc_text basic_session_runtime)
    add_test(NAME hw4_c1_native_runtime_tft_bytes COMMAND test_hw4_c1_integration)
endif()

# J1.7-B: F4 explicit INTEGER+INTEGER. Original J1.7-A captures are READ ONLY.
# Two portable suites added to 48 main suites, including HW4-C1.
if(BUILD_TESTING)
    add_executable(test_basic_integer_add_vars tests/test_basic_integer_add_vars.c)
    target_link_libraries(test_basic_integer_add_vars PRIVATE
                          basic_session_runtime basic_variable_binding)
    add_test(NAME integer_add_vars_f4 COMMAND test_basic_integer_add_vars)
    add_test(NAME j1_7_b_native_cpc_differential COMMAND
        ${Python3_EXECUTABLE}
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/j1_7_b_native_verify.py"
        --cli "$<TARGET_FILE:loco_basic_cli>"
        --image-cli "$<TARGET_FILE:basic_program_image_cli>" --self-test)
endif()

# J1.8-B: F5 subtraction between two explicit INTEGER references, two gates.
if(BUILD_TESTING)
    add_executable(test_basic_integer_sub_vars tests/test_basic_integer_sub_vars.c)
    target_link_libraries(test_basic_integer_sub_vars PRIVATE
                          basic_session_runtime basic_variable_binding)
    add_test(NAME integer_sub_vars_f5 COMMAND test_basic_integer_sub_vars)
    add_test(NAME j1_8_b_native_cpc_differential COMMAND
        ${Python3_EXECUTABLE}
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/j1_8_b_native_verify.py"
        --cli "$<TARGET_FILE:loco_basic_cli>"
        --image-cli "$<TARGET_FILE:basic_program_image_cli>" --self-test)
endif()

# HW4-C2: independent portable UART collection and screen echo/paging.
add_library(uart_line STATIC io/uart_line.c)
target_include_directories(uart_line PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/io)
add_library(cpc_uart_console STATIC io/cpc_uart_console.c)
target_include_directories(cpc_uart_console PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/io)
target_link_libraries(cpc_uart_console PUBLIC cpc_text)
if(BUILD_TESTING)
    add_executable(test_uart_line tests/test_uart_line.c)
    target_link_libraries(test_uart_line PRIVATE uart_line)
    add_test(NAME hw4_c2_uart_line_boundaries COMMAND test_uart_line)

    add_executable(test_cpc_uart_console tests/test_cpc_uart_console.c)
    target_link_libraries(test_cpc_uart_console PRIVATE cpc_uart_console uart_line)
    add_test(NAME hw4_c2_screen_paging COMMAND test_cpc_uart_console)

    add_executable(test_hw4_c2_integration tests/test_hw4_c2_integration.c)
    target_link_libraries(test_hw4_c2_integration PRIVATE
                          uart_line cpc_uart_console basic_session_runtime)
    add_test(NAME hw4_c2_native_uart_runtime_tft COMMAND test_hw4_c2_integration)
endif()


# J1.9-B: grouped F6/F9/FB, two CTest gates, immutable original archives.
if(BUILD_TESTING)
    add_executable(test_basic_integer_binary_family
                   tests/test_basic_integer_binary_family.c)
    target_link_libraries(test_basic_integer_binary_family PRIVATE
                          basic_session_runtime basic_variable_binding)
    add_test(NAME integer_binary_family_f6_f9_fb
             COMMAND test_basic_integer_binary_family)
    add_test(NAME j1_9_b_native_cpc_differential COMMAND
        ${Python3_EXECUTABLE}
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/j1_9_b_native_verify.py"
        --cli "$<TARGET_FILE:loco_basic_cli>"
        --image-cli "$<TARGET_FILE:basic_program_image_cli>" --self-test)
endif()


# J1.10-A: independent CPC6128 IF/THEN oracle only. No native flow code.
# Fail closed on any changed original RAM, printer, source, manifest, or SHA.
if(BUILD_TESTING)
    add_test(NAME j1_10_a_if_then_cpc_permanent COMMAND
        ${Python3_EXECUTABLE}
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/j1_10_if_then_verify.py"
        --permanent --self-test)
endif()

# HW4-C3-A: shared HW3 boot layout -> native CPC VRAM.
add_library(cpc_boot STATIC video/cpc_boot.c)
target_include_directories(cpc_boot PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/video)
target_link_libraries(cpc_boot PUBLIC cpc_text)
if(BUILD_TESTING)
    add_executable(test_hw4_c3_boot tests/test_hw4_c3_boot.c
                   firmware/esp32_display_probe/main/cpc_font.c)
    target_include_directories(test_hw4_c3_boot PRIVATE
              ${CMAKE_CURRENT_SOURCE_DIR}/firmware/esp32_display_probe/main)
    target_link_libraries(test_hw4_c3_boot PRIVATE cpc_boot cpc_uart_console)
    add_test(NAME hw4_c3_boot_screen COMMAND test_hw4_c3_boot)
endif()

# J1.10-B: native autonomous IF INTEGER THEN line. CPC oracle stays read-only.
if(BUILD_TESTING)
    add_executable(test_basic_if_then_integer
                   tests/test_basic_if_then_integer.c)
    target_link_libraries(test_basic_if_then_integer PRIVATE
                          basic_session_runtime basic_variable_binding)
    add_test(NAME j1_10_b_if_then_integer_native
             COMMAND test_basic_if_then_integer)
    add_test(NAME j1_10_b_if_then_cpc_differential COMMAND
        ${Python3_EXECUTABLE}
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/j1_10_b_native_verify.py"
        --cli "$<TARGET_FILE:loco_basic_cli>"
        --image-cli "$<TARGET_FILE:basic_program_image_cli>" --self-test)
endif()


# J1.11-A: independent CPC6128 GOSUB/RETURN oracle, strictly pre-native.
# Missing/unsealed archives fail closed until independent GHCR acquisition.
if(BUILD_TESTING)
    add_test(NAME j1_11_a_gosub_return_cpc_permanent COMMAND
        ${Python3_EXECUTABLE}
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/j1_11_gosub_return_verify.py"
        --permanent --self-test)
endif()

# J1.11-B: native bounded GOSUB/RETURN, independent post-B differential.
# The 16 J1.11-A archives and pre-B UNSUPPORTED classifications stay immutable.
if(BUILD_TESTING)
    add_executable(test_basic_gosub_return tests/test_basic_gosub_return.c)
    target_link_libraries(test_basic_gosub_return PRIVATE
                          basic_session_runtime basic_listing basic_tokenizer)
    add_test(NAME j1_11_b_gosub_return_native COMMAND test_basic_gosub_return)
    add_test(NAME j1_11_b_gosub_return_cpc_differential COMMAND
        ${Python3_EXECUTABLE}
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/j1_11_b_native_verify.py"
        --cli "$<TARGET_FILE:loco_basic_cli>"
        --image-cli "$<TARGET_FILE:basic_program_image_cli>" --self-test)
endif()

# HW4-C3-B2: native MODE1 scroll, bounded dirty retention under injected
# transport errors. The host retry proves transport-conditional resumption only.
if(BUILD_TESTING)
    add_executable(test_hw4_c3_b2_scroll tests/test_hw4_c3_b2_scroll.c)
    target_link_libraries(test_hw4_c3_b2_scroll PRIVATE cpc_uart_console)
    add_test(NAME hw4_c3_b2_mode1_scroll_dma_retry
             COMMAND test_hw4_c3_b2_scroll)

    # C1: same 53-byte fixture, frame-by-frame and coalesced screen comparison.
    add_executable(test_hw4_c3_b2_c1_batch tests/test_hw4_c3_b2_c1_batch.c)
    target_link_libraries(test_hw4_c3_b2_c1_batch PRIVATE cpc_uart_console)
    add_test(NAME hw4_c3_b2_c1_lcd_batch_fail_stop
             COMMAND test_hw4_c3_b2_c1_batch)
endif()

# J1.12-A: independent CPC6128 FOR/NEXT INTEGER oracle only.
# Fail closed before authentic acquisition and independent digest sealing.
if(BUILD_TESTING)
    add_test(NAME j1_12_a_for_next_cpc_permanent COMMAND
        ${Python3_EXECUTABLE}
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/j1_12_for_next_verify.py"
        --permanent --self-test)
endif()

# J1.12-B1: CPC FOR/NEXT INTEGER encoding and LIST only; B2 runtime blocked.
# Compare *only* sealed FOR/NEXT control records, not PRINT #8 program RAM.
if(BUILD_TESTING)
    add_executable(test_basic_for_next_b1 tests/test_basic_for_next_b1.c)
    target_link_libraries(test_basic_for_next_b1 PRIVATE
                          basic_session_runtime basic_tokenizer basic_listing
                          basic_variable_store)
    add_test(NAME j1_12_b1_for_next_tokens_list
             COMMAND test_basic_for_next_b1)
    add_test(NAME j1_12_b1_for_next_cpc_differential COMMAND
        ${Python3_EXECUTABLE}
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/j1_12_b1_native_verify.py"
        --image-cli "$<TARGET_FILE:basic_program_image_cli>"
        --cli "$<TARGET_FILE:loco_basic_cli>" --self-test)
endif()

# HW4-FONT-A: font-only HOST gate, no CPC ROM and no ESP-IDF runtime.
# Link the actual shared HW3 font, real MODE1 video/console and native BASIC
# session to test 95/95 ASCII through UART echo, source and LIST pixels.
if(BUILD_TESTING)
    add_executable(test_hw4_font_ascii
        tests/test_hw4_font_ascii.c
        firmware/esp32_display_probe/main/cpc_font.c)
    target_include_directories(test_hw4_font_ascii PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/firmware/esp32_display_probe/main)
    target_link_libraries(test_hw4_font_ascii PRIVATE
        cpc_uart_console uart_line basic_session_runtime basic_variable_binding)
    add_test(NAME hw4_font_a_ascii95_canonical_mode1
             COMMAND test_hw4_font_ascii)
endif()

# J1.12-B2: bounded native FOR/NEXT INTEGER execution + sealed CPC traces.
# B1's token/LIST differential remains independently active.
if(BUILD_TESTING)
    add_executable(test_basic_for_next_b2 tests/test_basic_for_next_b2.c)
    target_link_libraries(test_basic_for_next_b2 PRIVATE
                          basic_session_runtime basic_tokenizer basic_listing
                          basic_variable_store)
    add_test(NAME j1_12_b2_for_next_native
             COMMAND test_basic_for_next_b2)
    add_test(NAME j1_12_b2_for_next_cpc_differential COMMAND
        ${Python3_EXECUTABLE}
        "${CMAKE_CURRENT_SOURCE_DIR}/tools/j1_12_b2_native_verify.py"
        --cli "$<TARGET_FILE:loco_basic_cli>" --self-test)
endif()
