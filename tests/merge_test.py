"""Tests for the metacatch.merge module"""
#pylint: disable=line-too-long

import pytest
from metacatch import merge
from metacatch.config import EF

def run_merge(mode, func, inputs, output, errors):
    """Run a merge function and check the output and errors"""
    result, flags = func(i for i in inputs)
    exp_err = errors.name if errors else "NONE"
    got_err = flags.name if flags else "NONE"
    assert result == output, f"Expected {output}, got {result} for inputs {inputs} with mode {mode}"
    assert flags == errors, f"Expected {exp_err}, got {got_err} for inputs {inputs} with mode {mode}"

@pytest.mark.parametrize("inputs, mode, output, errors", [
    # Boolean values
    ([True, False, True],                           "any",         [True],                      EF.MRG_MODIFIED),
    ([True, True, True],                            "any",         [True],                      EF.NONE),
    ([False, False],                                "any",         [False],                     EF.NONE),
    ([True, True, False],                           "all",         [False],                     EF.MRG_MODIFIED),
    ([True, True],                                  "all",         [True],                      EF.NONE),
    ([False, False],                                "all",         [False],                     EF.NONE),
    # Numeric values
    ([1, 2, 3],                                     "sum",         [6],                         EF.MRG_MODIFIED),
    ([1, 2, 3],                                     "min",         [1],                         EF.MRG_MODIFIED),
    ([1, 2, 3],                                     "max",         [3],                         EF.MRG_MODIFIED),
    ([1.5, 2.5, 3.5],                               "sum",         [7.5],                       EF.MRG_MODIFIED),
    ([1.5, 2.5, 3.5],                               "min",         [1.5],                       EF.MRG_MODIFIED),
    ([1.5, 2.5, 3.5],                               "max",         [3.5],                       EF.MRG_MODIFIED),
    # String values
    (["a", "b", "c"],                               "append",      ["abc"],                     EF.MRG_ORDERED|EF.MRG_MODIFIED),
    (["z", "y", "x"],                               "append",      ["zyx"],                     EF.MRG_ORDERED|EF.MRG_MODIFIED),
    (["a", "b", "c"],                               "append(, )",  ["a, b, c"],                 EF.MRG_ORDERED|EF.MRG_MODIFIED),
    (["z", "y", "x"],                               "append(>)",   ["z>y>x"],                   EF.MRG_ORDERED|EF.MRG_MODIFIED),
    (["a", "b", "c"],                               "sorted",      ["abc"],                     EF.MRG_MODIFIED),
    (["z", "y", "x"],                               "sorted",      ["xyz"],                     EF.MRG_MODIFIED),
    (["a", "b", "c"],                               "sorted(|)",   ["a|b|c"],                   EF.MRG_MODIFIED),
    (["z", "y", "x"],                               "sorted(<)",   ["x<y<z"],                   EF.MRG_MODIFIED),
    (["a", "a", "a"],                               "sorted",      ["a"],                       EF.NONE),
    (["a", "b", "a"],                               "sorted( )",   ["a b"],                     EF.MRG_MODIFIED),
    # List values
    ([[3], [2], [1]],                               "append",      [[3,2,1]],                   EF.MRG_ORDERED|EF.MRG_MODIFIED),
    ([[1,2], [3,4], [5,6]],                         "append",      [[1,2,3,4,5,6]],             EF.MRG_ORDERED|EF.MRG_MODIFIED),
    # Set values
    ([{1}, {2}, {3}],                               "union",       [{1,2,3}],                   EF.MRG_MODIFIED),
    ([{1,2,3}, {2,3,4}, {3,4,5}],                   "union",       [{1,2,3,4,5}],               EF.MRG_MODIFIED),
    ([{1,2,3}, {1,2,3}, {1,2,3}],                   "union",       [{1,2,3}],                   EF.NONE),
    ([{1}, {2}, {3}],                               "intersect",   [set(),{1,2,3}],             EF.MRG_SUBSET|EF.MRG_MODIFIED),
    ([{1,2,3}, {2,3,4}, {3,4,5}],                   "intersect",   [{3},{1,2,4,5}],             EF.MRG_SUBSET|EF.MRG_MODIFIED),
    ([{1,2,3}, {1,2,3}, {1,2,3}],                   "intersect",   [{1,2,3}],                   EF.NONE),
    # Dict values
    ([{"a":1}, {"b":2}, {"c":3}],                   "union",       [{"a":1,"b":2,"c":3}],       EF.MRG_MODIFIED),
    ([{"a":1,"b":2}, {"a":1,"b":2}, {"a":1,"b":2}], "union",       [{"a":1,"b":2}],             EF.NONE),
    ([{"a":1,"b":2}, {"b":2,"c":3}, {"a":1,"b":2}], "union",       [{"a":1,"b":2,"c":3}],       EF.MRG_MODIFIED),
    ([{"a":1,"b":2}, {"a":0,"b":2}, {"a":3,"b":2}], "union",       [{"b":2},{"a":[0,1,3]}],     EF.MRG_CONFLICT|EF.MRG_SUBSET|EF.MRG_MODIFIED),
    ([{"a":1}, {"b":2}, {"c":3}],                   "intersect",   [{},{"a":[1],"b":[2],"c":[3]}], EF.MRG_SUBSET|EF.MRG_MODIFIED),
    ([{"a":1,"b":2}, {"a":1,"b":2}, {"a":1,"b":2}], "intersect",   [{"a":1,"b":2}],             EF.NONE),
    ([{"a":1,"b":2}, {"b":2,"c":3}, {"a":1,"b":2}], "intersect",   [{"b":2},{"a":[1],"c":[3]}], EF.MRG_SUBSET|EF.MRG_MODIFIED),
    ([{"a":1,"b":2}, {"a":1,"b":0}, {"a":1,"b":1}], "intersect",   [{"a":1},{"b":[0,1,2]}],     EF.MRG_SUBSET|EF.MRG_MODIFIED),
])
def test_merge_method(inputs, mode, output, errors):
    """Test the merge method for various types and modes"""
    # Get the appropriate merge function
    func = merge.method(type(inputs[0]), mode)
    # Test the merge function with the inputs as-is
    run_merge(mode, func, inputs, output, errors)
    # Test the merge function with extra None values inserted
    run_merge(mode, func, [None] + inputs, output, errors | EF.MRG_MISSING)
    run_merge(mode, func, inputs + [None], output, errors | EF.MRG_MISSING)
    run_merge(mode, func, inputs[:1] + [None] + inputs[1:], output, errors | EF.MRG_MISSING)
    # Test the merge function without any good values
    run_merge(mode, func, [], [], EF.MRG_MISSING)
    run_merge(mode, func, [None] * len(inputs), [], EF.MRG_MISSING)

@pytest.mark.parametrize("inputs, output, errors", [
    ([True, False, True],                           [False, True],                  EF.MRG_CONFLICT),
    ([True, True, True],                            [True],                         EF.NONE),
    ([False, False],                                [False],                        EF.NONE),
    ([1, 1, 1],                                     [1],                            EF.NONE),
    ([1, 2, 3],                                     [1, 2, 3],                      EF.MRG_CONFLICT),
    ([1, 1.0, 1],                                   [1],                            EF.NONE),
    (["a", "a", "a"],                               ["a"],                          EF.NONE),
    (["a", "b", "c"],                               ["a", "b", "c"],                EF.MRG_CONFLICT),
    ([[1], [2], [3]],                               [[1], [2], [3]],                EF.MRG_CONFLICT),
    ([[1,2], [1,2], [1,2]],                         [[1,2]],                        EF.NONE),
    ([{1,2}, {1,2}, {1,2}],                         [{1,2}],                        EF.NONE),
    ([{1,2}, {2,3}, {3,4}],                         [{1,2}, {2,3}, {3,4}],          EF.MRG_CONFLICT),
    ([{"a":1,"b":2}, {"a":1,"b":2}, {"a":1,"b":2}], [{"a":1,"b":2}],                EF.NONE),
    ([{"a":1,"b":2}, {"a":1,"b":2}, {"a":1,"b":3}], [{"a":1,"b":2}, {"a":1,"b":3}], EF.MRG_CONFLICT),
    ([{"a":1,"b":2}, {"a":1,"c":2}, {"a":1,"b":2}], [{"a":1,"b":2}, {"a":1,"c":2}], EF.MRG_CONFLICT),
])
def test_strict_merge(inputs, output, errors):
    """Test the strict merge function"""
    # We should get the same behavior for type in (type, None) and mode in (mode, None)
    funcs = [
        ("strict",  merge.method(type(inputs[0]), "strict")),
        (None,      merge.method(type(inputs[0]), None)),
        ("strict",  merge.method(None, "strict")),
        (None,      merge.method(None, None)),
    ]
    for mode, func in funcs:
        # Test the strict merge function with the inputs as-is
        run_merge(mode, func, inputs, output, errors)
        # Adding None values should trigger a MRG_CONFLICT error for a strict merge
        err_missing = EF.MRG_CONFLICT | EF.MRG_MISSING
        run_merge(mode, func, [None] + inputs, output, err_missing)
        run_merge(mode, func, inputs + [None], output, err_missing)
        run_merge(mode, func, inputs[:1] + [None] + inputs[1:], output, err_missing)
        # Test the merge function without any good values
        run_merge(mode, func, [], [], EF.MRG_MISSING)
        run_merge(mode, func, [None] * len(inputs), [], EF.MRG_MISSING)

@pytest.mark.parametrize("inputs, output, errors", [
    ([True, False, True],                           [],                     EF.MRG_DELETED),
    ([True, True, True],                            [True],                 EF.NONE),
    ([False, False],                                [False],                EF.NONE),
    ([1, 1, 1],                                     [1],                    EF.NONE),
    ([1, 2, 3],                                     [],                     EF.MRG_DELETED),
    ([1, 1.0, 1],                                   [1],                    EF.NONE),
    (["a", "a", "a"],                               ["a"],                  EF.NONE),
    (["a", "b", "c"],                               [],                     EF.MRG_DELETED),
    ([[1], [2], [3]],                               [],                     EF.MRG_DELETED),
    ([[1,2], [1,2], [1,2]],                         [[1,2]],                EF.NONE),
    ([{1,2}, {1,2}, {1,2}],                         [{1,2}],                EF.NONE),
    ([{1,2}, {2,3}, {3,4}],                         [],                     EF.MRG_DELETED),
    ([{"a":1,"b":2}, {"a":1,"b":2}, {"a":1,"b":2}], [{"a":1,"b":2}],        EF.NONE),
    ([{"a":1,"b":2}, {"a":1,"b":2}, {"a":1,"b":3}], [],                     EF.MRG_DELETED),
    ([{"a":1,"b":2}, {"a":1,"c":2}, {"a":1,"b":2}], [],                     EF.MRG_DELETED),
])
def test_equal_merge(inputs, output, errors):
    """Test the equal merge function"""
    # We should get the same behavior for type in (type, None) and mode in (mode, None)
    funcs = [merge.method(type(inputs[0]), "equal"), merge.method(None, "equal")]
    for func in funcs:
        # Test the equal merge function with the inputs as-is
        run_merge("equal", func, inputs, output, errors)
        # Adding None values should trigger a MRG_MISSING error for a strict merge
        run_merge("equal", func, [None] + inputs, output, errors | EF.MRG_MISSING)
        run_merge("equal", func, inputs + [None], output, errors | EF.MRG_MISSING)
        run_merge("equal", func, inputs[:1] + [None] + inputs[1:], output, errors | EF.MRG_MISSING)
        # Test the merge function without any good values
        run_merge("equal", func, [], [], EF.MRG_MISSING)
        run_merge("equal", func, [None] * len(inputs), [], EF.MRG_MISSING)

@pytest.mark.parametrize("inputs", [
    [True, False, True],
    [1, 2, 3],
    ["a", "b", "c"],
])
def test_delete_merge(inputs):
    """Test the delete merge function"""
    funcs = [merge.method(type(inputs[0]), "delete"), merge.method(None, "delete")]
    for func in funcs:
        # Test the delete merge function with the inputs as-is
        run_merge("delete", func, inputs, [], EF.MRG_DELETED)
        # None values shouldn't change the output
        run_merge("delete", func, [None] + inputs, [], EF.MRG_DELETED)
        run_merge("delete", func, inputs + [None], [], EF.MRG_DELETED)
        run_merge("delete", func, inputs[:1] + [None] + inputs[1:], [], EF.MRG_DELETED)
        # With no good values, we should still get MRG_DELETED
        run_merge("delete", func, [], [], EF.MRG_DELETED)
        run_merge("delete", func, [None] * len(inputs), [], EF.MRG_DELETED)
