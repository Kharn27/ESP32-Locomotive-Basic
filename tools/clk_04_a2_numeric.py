#!/usr/bin/env python3
"""CLK-04-A2: integer-only candidate for NONNEGATIVE uint32 to CPC REAL5.

Experimental hypothesis, NOT a production codec or evidence of CPC behaviour.
All operations are integer-only. Caller error policy is prototype-specific.
"""
UINT32_MAX = (1 << 32) - 1


def encode_uint32(value):
    if type(value) is not int:
        raise TypeError("A2_INPUT_NOT_PLAIN_INTEGER")
    if not 0 <= value <= UINT32_MAX:
        raise ValueError("A2_INPUT_OUTSIDE_UINT32")
    if value == 0:
        return bytes(5)
    exponent = value.bit_length() - 1
    # Exact shift for all uint32: exponent <= 31, no rounding.
    fraction = (value << (31 - exponent)) - (1 << 31)
    if not 0 <= fraction <= 0x7fffffff:
        raise ArithmeticError("A2_FRACTION_INVARIANT")
    return fraction.to_bytes(4, "little") + bytes((exponent + 0x81,))


def decode_nonnegative_integer(raw):
    """Inverse only for positive, EXACT integer REAL5 encodings."""
    if type(raw) is not bytes or len(raw) != 5:
        raise TypeError("A2_REAL5_EXPECTS_FIVE_BYTES")
    if raw == bytes(5):
        return 0
    if raw[3] & 0x80:
        raise ValueError("A2_REAL5_SIGN_NOT_SUPPORTED")
    exponent = raw[4] - 0x81
    if not 0 <= exponent <= 31:
        raise ValueError("A2_REAL5_EXPONENT_UNSUPPORTED")
    mantissa = (1 << 31) | int.from_bytes(raw[:4], "little")
    numerator = mantissa << exponent
    value, remainder = divmod(numerator, 1 << 31)
    if remainder or value > UINT32_MAX:
        raise ValueError("A2_REAL5_NOT_INTEGER_UINT32")
    return value


def self_test():
    fixed = {
        0: "00 00 00 00 00",
        1: "00 00 00 00 81",
        5256: "00 00 40 24 8D",
        50376: "00 00 C8 44 90",
        2147483647: "FE FF FF 7F 9F",
        2147483648: "00 00 00 00 A0",
        4294967295: "FF FF FF 7F A0",
    }
    for v, hx in fixed.items():
        raw = encode_uint32(v)
        if raw != bytes.fromhex(hx) or decode_nonnegative_integer(raw) != v:
            raise AssertionError("A2_MODEL_SELF_TEST")
    for n in (-1, UINT32_MAX + 1):
        try:
            encode_uint32(n)
        except ValueError:
            pass
        else:
            raise AssertionError("A2_MODEL_DOMAIN_REJECT")
    print("CLK-04-A2 MODEL_SELF_TEST_PASS (NOT CPC)")


if __name__ == "__main__":
    self_test()
