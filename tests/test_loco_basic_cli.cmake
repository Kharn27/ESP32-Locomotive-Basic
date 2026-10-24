cmake_minimum_required(VERSION 3.13)

# J0.9 black-box integration: launch the real CLI with scripted stdin.
if(NOT DEFINED CLI OR NOT EXISTS "${CLI}")
    message(FATAL_ERROR "CLI executable missing: ${CLI}")
endif()
if(NOT DEFINED TEST_TEMP_DIR)
    message(FATAL_ERROR "TEST_TEMP_DIR is required")
endif()

function(check_case name script_input expected_out expected_err)
    set(path "${TEST_TEMP_DIR}/host-cli-${name}.input")
    file(WRITE "${path}" "${script_input}")
    execute_process(
        COMMAND "${CLI}"
        INPUT_FILE "${path}"
        OUTPUT_VARIABLE actual_out
        ERROR_VARIABLE actual_err
        RESULT_VARIABLE result
        TIMEOUT 10
    )
    if(NOT "${result}" STREQUAL "0")
        message(FATAL_ERROR "${name}: failed or timed out (${result})\n${actual_err}")
    endif()
    if(NOT "${actual_out}" STREQUAL "${expected_out}")
        message(FATAL_ERROR "${name}: stdout mismatch\nExpected:\n[${expected_out}]\nActual:\n[${actual_out}]")
    endif()
    if(NOT "${actual_err}" STREQUAL "${expected_err}")
        message(FATAL_ERROR "${name}: stderr mismatch\nExpected:\n[${expected_err}]\nActual:\n[${actual_err}]")
    endif()
    file(REMOVE "${path}")
endfunction()

set(banner "[cli] J0.9 host CLI (:help)\n")
set(ok "[cli] OK\n")
set(step1 "[cli] STEPPED 1\n")
set(running "[cli] RUNNING\n")
set(ended "[cli] END\n")
set(byebye "[cli] BYE\n")
set(stopped "[cli] STOPPED\n")
set(listed "[cli] LIST\n")
set(eof "[cli] EOF\n")
set(session_unsupported "[cli:error] BSR_SESSION_ERROR BS_UNSUPPORTED_DIRECT BT_OK BP_OK BL_OK BE_OK\n")
set(session_multiple "[cli:error] BSR_SESSION_ERROR BS_MULTIPLE_DIRECT BT_OK BP_OK BL_OK BE_OK\n")
set(executor_missing "[cli:error] BSR_EXECUTOR_ERROR BS_OK BT_OK BP_OK BL_OK BE_MISSING_TARGET\n")

check_case("run-list-end"
    "20 PRINT 42\n10 PRINT \"HELLO\"\nLIST\nRUN\n:step\n:step\n:step\n:quit\n"
    "10 PRINT \"HELLO\"\n20 PRINT 42\nHELLO\n42\n"
    "${banner}${ok}${ok}${listed}${running}${step1}${step1}${ended}${byebye}"
)

check_case("loop-stop-new"
    "10 GOTO 10\nRUN\n:step 100\n:stop\nNEW\nLIST\n:quit\n"
    ""
    "${banner}${ok}${running}[cli] STEPPED 100\n${stopped}${ok}${listed}${byebye}"
)

check_case("edit-new-restart"
    "10 PRINT 1\n10 PRINT 2\nRUN\n:step\n:step\nNEW\n10 PRINT 3\nRUN\n:step\n:step\n:quit\n"
    "2\n3\n"
    "${banner}${ok}${ok}${running}${step1}${ended}${ok}${ok}${running}${step1}${ended}${byebye}"
)

set(invalid "[cli:error] INVALID_STEP (expected 1..100)\n")
check_case("invalid-step-arguments"
    ":step 0\n:step 101\n:step abc\n:step 9999999999999999999999999999\n:step\n:quit\n"
    ""
    "${banner}${invalid}${invalid}${invalid}${invalid}[cli:error] BSR_NOT_RUNNING BS_OK BT_OK BP_OK BL_OK BE_OK\n${byebye}"
)

check_case("unsupported-direct"
    "PRINT 1\nRUN 10\nLIST:RUN\n:unknown\n:quit\n"
    ""
    "${banner}${session_unsupported}${session_unsupported}${session_multiple}[cli:error] UNKNOWN_META\n${byebye}"
)

set(long_line "10 PRINT \"BAD\"")
foreach(n RANGE 1 600)
    string(APPEND long_line "X")
endforeach()
check_case("long-line-resync"
    "${long_line}\n20 PRINT \"OK\"\nLIST\nRUN\n:step\n:step\n:quit\n"
    "20 PRINT \"OK\"\nOK\n"
    "${banner}[cli:error] INPUT_TOO_LONG\n${ok}${listed}${running}${step1}${ended}${byebye}"
)

check_case("executor-error-and-eof"
    "10 PRINT 9\n20 GOTO 999\nRUN\n:step\n:step\n:step\n:stop\nRUN\n:step\n:step\n:stop\n"
    "9\n9\n"
    "${banner}${ok}${ok}${running}${step1}${executor_missing}${executor_missing}${stopped}${running}${step1}${executor_missing}${stopped}${eof}"
)

check_case("busy-list"
    "10 PRINT 1\nRUN\n10 PRINT 2\nLIST\n:stop\n:quit\n"
    "10 PRINT 1\n"
    "${banner}${ok}${running}[cli:error] BSR_BUSY BS_OK BT_OK BP_OK BL_OK BE_OK\n${listed}${stopped}${byebye}"
)

check_case("help"
    ":help\n:quit\n"
    ""
    "${banner}[cli] :help :step [N=1..100] :stop :quit\n[cli] BASIC: numbered lines, LIST, NEW, RUN\n[cli] stdout=BASIC bytes; stderr=host messages\n${byebye}"
)

check_case("crlf-unterminated"
    "10 PRINT 5\r\nRUN\r\n:step\r\n:quit"
    "5\n"
    "${banner}${ok}${running}${step1}${byebye}"
)

message(STATUS "host_cli: ten black-box scenarios passed")
