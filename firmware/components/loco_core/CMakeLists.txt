# J0.25: the ONE native C99 core; no source copies or host/fixture binaries.
set(LOCO_CORE_DIR "${CMAKE_CURRENT_LIST_DIR}/../../../core")
idf_component_register(
    SRCS
        "${LOCO_CORE_DIR}/basic_program.c"
        "${LOCO_CORE_DIR}/basic_listing.c"
        "${LOCO_CORE_DIR}/basic_tokenizer.c"
        "${LOCO_CORE_DIR}/basic_executor.c"
        "${LOCO_CORE_DIR}/basic_session.c"
        "${LOCO_CORE_DIR}/basic_session_runtime.c"
        "${LOCO_CORE_DIR}/basic_variable_ref.c"
        "${LOCO_CORE_DIR}/basic_variable_types.c"
        "${LOCO_CORE_DIR}/basic_variable_store.c"
        "${LOCO_CORE_DIR}/basic_variable_binding.c"
    INCLUDE_DIRS "${LOCO_CORE_DIR}"
)
# Explicit C99, even if the ESP-IDF application default is a different C dialect.
target_compile_options(${COMPONENT_LIB} PRIVATE -std=c99)
