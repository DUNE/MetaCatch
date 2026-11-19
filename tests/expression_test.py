"""Tests for the metacatch.merge module"""
#pylint: disable=line-too-long

import itertools
import pytest
from metacatch import expression

@pytest.mark.parametrize("value", [
    7,
    3.14,
    -42,
    -123.456,
    "Hello World",
    True,
    False,
    None,
    [1, 2, 3],
    ["a", "b", "c"],
    [True, False, True],
])
def test_constants(value):
    """Test that constant expressions evaluate to the expected value"""
    func = expression.parse(repr(value))
    if errors := func.errors({}):
        raise ValueError(f"Expression ({repr(value)}) has errors: {errors}")
    result = func({})
    assert result == value, f"Constant expression ({repr(value)}) == {result}"

@pytest.mark.parametrize("variables", [
    ["x"],
    ["y"],
    ["x", "y"],
    ["a", "b", "c"],
    ["x", "y", "z", "x.y", "x.z", "y.x", "y.z", "z.x", "z.y", "x.y.z", "x.z.y", "y.x.z", "z.x.y"],
])
def test_variables(variables):
    """Test that variable expressions evaluate to the expected value"""
    var_dict = {v: i for i, v in enumerate(variables)}
    for var in variables:
        func = expression.parse(var)
        if errors := func.errors(var_dict):
            raise ValueError(f"Expression ({var}) has errors: {errors}")
        result = func(var_dict)
        expected = var_dict[var]
        assert result == expected, f"Variable expression ({var}) == {result}, expected {expected}"

@pytest.mark.parametrize("expr, expected, args", [
    ("a and b",             lambda a, b:    a and b,            2),
    ("a or b",              lambda a, b:    a or b,             2),
    ("not a",               lambda a:       not a,              1),
    ("a and not b",         lambda a, b:    a and not b,        2),
    ("a or not b",          lambda a, b:    a or not b,         2),
    ("a and b and c",       lambda a, b, c: a and b and c,      3),
    ("a or b or c",         lambda a, b, c: a or b or c,        3),
    ("not a and b",         lambda a, b:    not a and b,        2),
    ("not a or b",          lambda a, b:    not a or b,         2),
    ("not (a or b)",        lambda a, b:    not (a or b),       2),
    ("not (a and b)",       lambda a, b:    not (a and b),      2),
    ("a and (b or c)",      lambda a, b, c: a and (b or c),     3),
    ("a or (b and c)",      lambda a, b, c: a or (b and c),     3),
    ("(a and b) or c",      lambda a, b, c: (a and b) or c,     3),
    ("(a or b) and c",      lambda a, b, c: (a or b) and c,     3),
    ("(a and not b) or c",  lambda a, b, c: (a and not b) or c, 3),
    ("(a or not b) and c",  lambda a, b, c: (a or not b) and c, 3),
])
def test_boolean_logic(expr, expected, args):
    """Test that boolean expressions evaluate to the expected outputs"""
    var_names = [chr(ord('a') + i) for i in range(args)]
    val_opts = [True, False, None, 0, 1, 7, "", "Hello", [], [1, 2, 3]]
    func = expression.parse(expr)
    if errors := func.errors({v: 0 for v in var_names}):
        raise ValueError(f"Expression ({expr}) has errors: {errors}")
    for vals in itertools.product(val_opts, repeat=args):
        result = func(dict(zip(var_names, vals)))
        comp = expected(*(bool(v) for v in vals))
        assert result == comp, f"({expr}) == {result}, expected {comp} for inputs {vals}"

COMPARISON_OPS = {
    "<":  lambda x, y: x < y,
    "<=": lambda x, y: x <= y,
    "==": lambda x, y: x == y,
    "!=": lambda x, y: x != y,
    ">=": lambda x, y: x >= y,
    ">":  lambda x, y: x > y,
}

def test_binary_comparisons():
    """Test that comparison expressions evaluate to the expected outputs"""
    for op, comp in COMPARISON_OPS.items():
        expr = f"x {op} y"
        func = expression.parse(expr)
        if errors := func.errors({"x": 0, "y": 0}):
            raise ValueError(f"Expression ({expr}) has errors: {errors}")
        x = 5
        for y in [3, 5, 7]:
            result = func({"x": x, "y": y})
            expected = comp(x, y)
            assert result == expected, f"({expr}) == {result}, expected {expected} for inputs [{x}, {y}]"

def test_trinary_comparisons():
    """Test that chained comparison expressions evaluate to the expected outputs"""
    for op1, comp1 in COMPARISON_OPS.items():
        for op2, comp2 in COMPARISON_OPS.items():
            expr = f"x {op1} y {op2} z"
            func = expression.parse(expr)
            if errors := func.errors({"x": 0, "y": 0, "z": 0}):
                raise ValueError(f"Expression ({expr}) has errors: {errors}")
            y = 5
            for x in [3, 5, 7]:
                for z in [3, 5, 7]:
                    result = func({"x": x, "y": y, "z": z})
                    expected = comp1(x, y) and comp2(y, z)
                    assert result == expected, f"({expr}) == {result}, expected {expected} for inputs [{x}, {y}, {z}]"

@pytest.mark.parametrize("expr, expected, args", [
    ("a + b",               lambda a, b:    a + b,            2),
    ("a - b",               lambda a, b:    a - b,            2),
    ("a * b",               lambda a, b:    a * b,            2),
    ("a / b",               lambda a, b:    a / b,            2),
    ("a % b",               lambda a, b:    a % b,            2),
    ("a ** b",              lambda a, b:    a ** b,           2),
    ("a + b + c",           lambda a, b, c: a + b + c,        3),
    ("a - b - c",           lambda a, b, c: a - b - c,        3),
    ("a * b * c",           lambda a, b, c: a * b * c,        3),
    ("a / b / c",           lambda a, b, c: a / b / c,        3),
    ("a % b % c",           lambda a, b, c: a % b % c,        3),
    ("a ** b ** c",         lambda a, b, c: a ** b ** c,      3),
    ("a / (b + c)",         lambda a, b, c: a / (b + c),      3),
    ("(a + b) / c",         lambda a, b, c: (a + b) / c,      3),
    ("(a - b) * c",         lambda a, b, c: (a - b) * c,      3),
    ("(a * b) - c",         lambda a, b, c: (a * b) - c,      3),
    ("(a % b) + c",         lambda a, b, c: (a % b) + c,      3),
    ("(a ** b) / c",        lambda a, b, c: (a ** b) / c,     3),
    ("(a + b) ** c",        lambda a, b, c: (a + b) ** c,     3),
    ("(a - b) ** (c)",      lambda a, b, c: (a - b) ** c,     3),
    ("(a * b) ** (c)",      lambda a, b, c: (a * b) ** c,     3),
])
def test_arithmetic(expr, expected, args):
    """Test that arithmetic expressions evaluate to the expected outputs"""
    var_names = [chr(ord('a') + i) for i in range(args)]
    val_opts = [0, 1, 2, 3, -1, -2, 0.5, 3.14, -3.14]
    func = expression.parse(expr)
    if errors := func.errors({v: 0 for v in var_names}):
        raise ValueError(f"Expression ({expr}) has errors: {errors}")
    for vals in itertools.product(val_opts, repeat=args):
        try:
            result = func(dict(zip(var_names, vals)))
        except ZeroDivisionError:
            result = "ZeroDivisionError"
        try:
            comp = expected(*vals)
        except ZeroDivisionError:
            comp = "ZeroDivisionError"
        assert result == comp, f"({expr}) == {result}, expected {comp} for inputs {vals}"

@pytest.mark.parametrize("expr, expected, args", [
    ("a is None",           lambda a:       a is None,          1),
    ("a is not None",       lambda a:       a is not None,      1),
    ("a is b",              lambda a, b:    a is b,             2),
    ("a is not b",          lambda a, b:    a is not b,         2),
])
def test_identity(expr, expected, args):
    """Test that identity expressions evaluate to the expected outputs"""
    var_names = [chr(ord('a') + i) for i in range(args)]
    val_opts = [0, 7, 8, 7.0, "7", [7], [], None]
    func = expression.parse(expr)
    if errors := func.errors({v: 0 for v in var_names}):
        raise ValueError(f"Expression ({expr}) has errors: {errors}")
    for vals in itertools.product(val_opts, repeat=args):
        result = func(dict(zip(var_names, vals)))
        comp = expected(*vals)
        assert result == comp, f"({expr}) == {result}, expected {comp} for inputs {vals}"

def test_inclusion():
    """Test that inclusion expressions evaluate to the expected outputs"""
    func_in = expression.parse("val in vals")
    func_out = expression.parse("val not in vals")
    if errors := func_in.errors({"val": 0, "vals": []}):
        raise ValueError(f"Expression (val in vals) has errors: {errors}")
    if errors := func_out.errors({"val": 0, "vals": []}):
        raise ValueError(f"Expression (val not in vals) has errors: {errors}")
    vals = [0, 3, 5, 7, 3.14, "Hello", "World", [1, 2], [], None]
    subsets = itertools.chain(
        (vals[:i] for i in range(len(vals))),
        (vals[i:] for i in range(len(vals)))
    )
    for subset in subsets:
        for val in vals:
            result_in = func_in({"val": val, "vals": subset})
            expected_in = val in subset
            assert result_in == expected_in, f"(val in vals) == {result_in}, expected {expected_in} for val={val}, vals={subset}"
            result_out = func_out({"val": val, "vals": subset})
            expected_out = val not in subset
            assert result_out == expected_out, f"(val not in vals) == {result_out}, expected {expected_out} for val={val}, vals={subset}"

@pytest.mark.parametrize("expr, inputs, output", [
    # String arithmetic
    ("x + y",               {"x": "Hello ", "y": "World"},          "Hello World"),
    ("x * y",               {"x": "abc", "y": 3},                   "abcabcabc"),
])
def test_expression(expr, inputs, output):
    """Test that an arbitrary expression evaluates to the expected output"""
    func = expression.parse(expr)
    if errors := func.errors(inputs):
        raise ValueError(f"Expression ({expr}) has errors: {errors}")
    result = func(inputs)
    assert result == output, f"({expr}) == {result}, expected {output} for inputs {inputs}"
