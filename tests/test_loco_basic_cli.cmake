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
set(variable_missing "[cli:error] BSR_EXECUTOR_ERROR BS_OK BT_OK BP_OK BL_OK BE_VARIABLE_NOT_FOUND\n")

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

check_case("comments-rem-and-apostrophe"
    "10 PRINT \"BONJOUR\":REM PRINT \"INTERDIT\"\n20 ' : PRINT \"HIDDEN\"\n30 PRINT 42\nLIST\nRUN\n:step\n:step\n:step\n:step\n:quit\n"
    "10 PRINT \"BONJOUR\":REM PRINT \"INTERDIT\"\n20 ' : PRINT \"HIDDEN\"\n30 PRINT 42\nBONJOUR\n42\n"
    "${banner}${ok}${ok}${ok}${listed}${running}${step1}${step1}${step1}${ended}${byebye}"
)

# J0.11 END: numbered statement only, no new direct command.
check_case("end-program"
    "10 PRINT \"AVANT\"\n20 END\n30 PRINT \"INTERDIT\"\nLIST\nRUN\n:step\n:step\n:step\nLIST\n:quit\n"
    "10 PRINT \"AVANT\"\n20 END\n30 PRINT \"INTERDIT\"\nAVANT\n10 PRINT \"AVANT\"\n20 END\n30 PRINT \"INTERDIT\"\n"
    "${banner}${ok}${ok}${ok}${listed}${running}${step1}${step1}${ended}${listed}${byebye}"
)

check_case("end-colon-and-goto"
    "10 GOTO 30:END\n20 PRINT \"SKIP\"\n30 PRINT \"A\":END:PRINT \"B\"\n40 PRINT \"C\"\nRUN\n:step\n:step\n:step\n:quit\n"
    "A\n"
    "${banner}${ok}${ok}${ok}${ok}${running}${step1}${step1}${ended}${byebye}"
)

check_case("end-comments-and-direct-rejection"
    "END\n10 PRINT \"END\":REM END:PRINT \"HIDDEN\"\n20 ' END:PRINT \"HIDDEN\"\n30 END\n40 PRINT \"SKIP\"\nRUN\n:step\n:step\n:step\n:step\n:quit\n"
    "END\n"
    "${banner}${session_unsupported}${ok}${ok}${ok}${ok}${running}${step1}${step1}${step1}${ended}${byebye}"
)

# J0.16: CLI stores/lists CPC explicit variables, without running them.
check_case("explicit-variable-list-unsupported-run"
    "10 PRINT A%\n20 PRINT B!\n30 PRINT S$\n40 END\nLIST\nRUN\n:step\n:quit\n"
    "10 PRINT A%\n20 PRINT B!\n30 PRINT S$\n40 END\n"
    "${banner}${ok}${ok}${ok}${ok}${listed}${running}${variable_missing}${byebye}"
)


# J0.16-C1: ?A% and its sibling suffixes must survive the entire
# terminal -> numbered program -> LIST pipeline, without variable evaluation.
check_case("c1-alias-print-suffix-and-number"
    "10 ?A%\n20 ?B!\n30 ?S$\n40 PRINT A%\n50 ?A%:END\n60 ?5\n70 ?42\n80 ?\"Q\"\n90 END\nLIST\nRUN\n:step\n:quit\n"
    "10 PRINT A%\n20 PRINT B!\n30 PRINT S$\n40 PRINT A%\n50 PRINT A%:END\n60 PRINT 5\n70 PRINT 42\n80 PRINT\"Q\"\n90 END\n"
    "${banner}${ok}${ok}${ok}${ok}${ok}${ok}${ok}${ok}${ok}${listed}${running}${variable_missing}${byebye}"
)

check_case("c1-printa-is-not-a-keyword"
    "10 PRINTA%\nLIST\n:quit\n"
    ""
    "${banner}[cli:error] BSR_SESSION_ERROR BS_TOKENIZER_ERROR BT_UNSUPPORTED_CONSTRUCT BP_OK BL_OK BE_OK\n${listed}${byebye}"
)

# J0.19: the same first INTEGER assignment is now executable.
check_case("integer-assignment-list-unsupported-run"
    "10 A%=2\n20 LET B%=5\n30 A% = 10\n40 PRINT A%\n50 END\nLIST\nRUN\n:step\n:quit\n"
    "10 A%=2\n20 LET B%=5\n30 A% = 10\n40 PRINT A%\n50 END\n"
    "${banner}${ok}${ok}${ok}${ok}${ok}${listed}${running}${step1}${byebye}"
)

# J0.19 also exercises successful assignment steps below.

# J0.19: no BASIC-introspection extension; the host step protocol is enough.
check_case("integer-assignment-step"
    "10 A%=2\n20 LET B%=255\n30 END\nRUN\n:step\n:step\n:step\n:step\n:quit\n"
    ""
    "${banner}${ok}${ok}${ok}${running}${step1}${step1}${step1}${ended}${byebye}"
)

# J0.20: real CLI process, BASIC stdout and host diagnostics separated.
check_case("integer-variable-print"
    "10 A%=2\n20 PRINT A%\n30 END\nRUN\n:step\n:step\n:step\n:step\n:quit\n"
    "2\n"
    "${banner}${ok}${ok}${ok}${running}${step1}${step1}${step1}${ended}${byebye}"
)

check_case("integer-variable-alias"
    "10 A%=9\n20 ?A%\n30 END\nRUN\n:step 3\n:step\n:quit\n"
    "9\n"
    "${banner}${ok}${ok}${ok}${running}[cli] STEPPED 3\n${ended}${byebye}"
)

check_case("integer-variable-missing"
    "10 PRINT A%\nRUN\n:step\n:stop\n:quit\n"
    ""
    "${banner}${ok}${running}${variable_missing}${stopped}${byebye}"
)

message(STATUS "host_cli: twenty-two black-box scenarios passed")
