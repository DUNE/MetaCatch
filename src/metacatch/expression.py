"""Functions and classes for parsing and evaluating metadata expressions."""

import ast
import operator
from collections.abc import Mapping
from abc import ABC, abstractmethod
from typing import Any

ALLOWED_OPERATORS = {
    # Unary operators
    ast.Not:    operator.not_,              # not
    ast.USub:   operator.neg,               # negative numbers
    # Binary operators
    ast.Add:    operator.add,               # +
    ast.Sub:    operator.sub,               # -
    ast.Mult:   operator.mul,               # *
    ast.Div:    operator.truediv,           # /
    ast.Mod:    operator.mod,               # %
    ast.Pow:    operator.pow,               # **
    # Bitwise operators
    ast.BitAnd: operator.and_,              # &
    ast.BitOr:  operator.or_,               # |
    ast.BitXor: operator.xor,               # ^
    # Boolean operators
    ast.And:    all,                        # and
    ast.Or:     any,                        # or
    # Comparison operators
    ast.Eq:     operator.eq,                # ==
    ast.NotEq:  operator.ne,                # !=
    ast.Lt:     operator.lt,                # <
    ast.LtE:    operator.le,                # <=
    ast.Gt:     operator.gt,                # >
    ast.GtE:    operator.ge,                # >=
    ast.Is:     operator.is_,               # is
    ast.IsNot:  operator.is_not,            # is not
    ast.In:     lambda x, y: x in y,        # in
    ast.NotIn:  lambda x, y: x not in y,    # not in
}

ALLOWED_FUNCTIONS = {
    # Standard built-in functions
    "len": len,
    "sum": sum,
    "min": min,
    "max": max,
    "any": any,
    "all": all,
    "abs": abs,
    "round": round,
    "sorted": sorted,
    "zip": zip,
    # Basic type conversions
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "set": set,
    # Method callers (avoids confusion with "category.subcategory.parameter" key names)
    "keys": lambda arg: arg.keys()
}

ALLOWED_METHODS = {
    # String methods
    "lower",
    "upper",
    "strip",
    "startswith",
    "endswith",
    "replace",
    "split",
    "join",
    # List methods
    "index",
    "count",
    # Dict methods
    "get",
    "keys",
    "values",
    "items",
}

def op_name(op):
    """Return the type name of the operator"""
    return type(op).__name__

def check_op(op, category = None):
    """Check if the operator is allowed"""
    if op in ALLOWED_OPERATORS:
        return []
    if category is None:
        return [f"Unsupported operator: {op.__name__}"]
    return [f"Unsupported {category} operator: {op.__name__}"]

class Expression(ABC):
    """Base class for expressions"""

    @abstractmethod
    def errors(self, keys: Mapping) -> list[str]:
        """Validate the expression, returning a list of errors if any"""
        return ["Abstract base class Expression should not be instantiated directly"]

    @abstractmethod
    def __call__(self, metadata: dict) -> Any:
        """Evaluate the expression with the given metadata"""
        raise NotImplementedError("Abstract base class Expression should not be instantiated")

    def __str__(self) -> str:
        """Return a string representation of the expression"""
        return "Expression"

class ExprKey(Expression):
    """Class to represent a metadata key in an expression"""
    def __init__(self, node):
        self.parse_errors = []
        self.key = self.parse(node)

    def parse(self, node):
        """Parse the name of the metadata key"""
        if isinstance(node, ast.Attribute):
            name = self.parse(node.value) + "." + node.attr
        elif isinstance(node, ast.Name):
            name = node.id
        else:
            self.parse_errors.append(f"Unexpected node type in key name: {op_name(node)}")
            return ''
        if not isinstance(node.ctx, ast.Load):
            self.parse_errors.append(f"Unsupported {op_name(node.ctx)} operation on key {name}")
        return name

    def errors(self, keys):
        """Validate the metadata key, returning a list of errors if any"""
        if self.parse_errors:       # Return any errors encountered during parsing
            return self.parse_errors[:]
        if self.key not in keys:    # Make sure the key exists
            return [f"Unknown metadata key: {self.key}"]
        return []

    def __call__(self, metadata):
        """Return the value of the metadata key from the given metadata dictionary"""
        return metadata.get(self.key, None)

    def __str__(self):
        return f"{{{self.key}}}"

class ExprConst(Expression):
    """Class to represent a constant value in an expression"""
    def __init__(self, node):
        self.value = node.value

    def errors(self, keys):
        """Constant values are always valid, so return an empty list of errors"""
        return []

    def __call__(self, metadata):
        """Return the constant value"""
        return self.value

    def __str__(self):
        return repr(self.value)

class ExprList(Expression):
    """Class to represent a list in an expression"""
    def __init__(self, node):
        self.parse_errors = []
        if not isinstance(node.ctx, ast.Load):
            self.parse_errors.append(f"Unsupported {op_name(node.ctx)} operation on list")
        self.contents = [parse_node(value) for value in node.elts]

    def errors(self, keys):
        """Validate the list and its contents, returning a list of errors if any"""
        errs = self.parse_errors[:]
        for cond in self.contents:
            errs.extend(cond.errors(keys))
        return errs

    def __call__(self, metadata):
        """Return a list of the evaluated expressions"""
        return [cond(metadata) for cond in self.contents]

    def __str__(self):
        return '[' + ", ".join(str(cond) for cond in self.contents) + ']'

class ExprUnaryOp(Expression):
    """Class to represent a unary operation in an expression"""
    def __init__(self, node):
        self.op = type(node.op)
        self.operand = parse_node(node.operand)

    def errors(self, keys):
        """Validate the unary operation and its operand, returning a list of errors if any"""
        errs = check_op(self.op, category="unary")
        errs.extend(self.operand.errors(keys))
        return errs

    def __call__(self, metadata):
        """Return the result of the unary operation"""
        return ALLOWED_OPERATORS[self.op](self.operand(metadata))

    def __str__(self):
        return f"{self.op.__name__}({self.operand})"

class ExprBinaryOp(Expression):
    """Class to represent a binary operation in an expression"""
    def __init__(self, node):
        self.op = type(node.op)
        self.left = parse_node(node.left)
        self.right = parse_node(node.right)

    def errors(self, keys):
        """Validate the binary operation and its operands, returning a list of errors if any"""
        errs = self.left.errors(keys)
        errs.extend(check_op(self.op, category="binary"))
        errs.extend(self.right.errors(keys))
        return errs

    def __call__(self, metadata):
        """Return the result of the binary operation"""
        return ALLOWED_OPERATORS[self.op](self.left(metadata), self.right(metadata))

    def __str__(self):
        return f"({self.left} {self.op.__name__} {self.right})"

class ExprBoolOp(Expression):
    """Class to represent a boolean operation in an expression"""
    def __init__(self, node):
        self.op = type(node.op)
        self.values = [parse_node(value) for value in node.values]

    def errors(self, keys):
        """Validate the boolean operation and its values, returning a list of errors if any"""
        errs = check_op(self.op, category="boolean")
        for value in self.values:
            errs.extend(value.errors(keys))
        return errs

    def __call__(self, metadata):
        """Return the result of the boolean operation"""
        return ALLOWED_OPERATORS[self.op](cond(metadata) for cond in self.values)

    def __str__(self):
        return '(' + f" {self.op.__name__} ".join(str(value) for value in self.values) + ')'

class ExprComparison(Expression):
    """Class to represent a comparison operation in an expression"""
    def __init__(self, node):
        self.ops = [type(op) for op in node.ops]
        self.left = parse_node(node.left)
        self.operands = [parse_node(operand) for operand in node.comparators]

    def errors(self, keys):
        """Validate the comparison operation and its operands, returning a list of errors if any"""
        errs = self.left.errors(keys)
        for op, operand in zip(self.ops, self.operands):
            errs.extend(check_op(op, category="comparison"))
            errs.extend(operand.errors(keys))
        return errs

    def __call__(self, metadata):
        """Return the result of the comparison operation"""
        left = self.left(metadata)
        result = True
        for op, operand in zip(self.ops, self.operands):
            right = operand(metadata)
            result = result and ALLOWED_OPERATORS[op](left, right)
            left = right
        return result

    def __str__(self):
        cmps = [f"{op.__name__} {operand}" for op, operand in zip(self.ops, self.operands)]
        return f"({self.left} " + " ".join(cmps) + ")"

class ExprFunc(Expression):
    """Class to represent a function call in an expression"""
    def __init__(self, node):
        self.parse_errors = []
        self.func = None
        self.object = None
        # Standalone functions
        if isinstance(node.func, ast.Name):
            self.func = node.func.id
        # Object methods (e.g., "name.method()")
        elif isinstance(node.func, ast.Attribute):
            self.func = node.func.attr
            self.object = parse_node(node.func.value)
        # Something else?
        else:
            self.parse_errors.append(f"Unsupported function type: {op_name(node.func)}")
        # Check context of the function call (should be a load operation)
        if not isinstance(node.func.ctx, ast.Load):
            self.parse_errors.append(
                f"Unsupported {op_name(node.func.ctx)} operation on function {self.func}"
            )
        # Parse the arguments
        self.args = [parse_node(arg) for arg in node.args]
        if len(node.keywords) > 0:
            self.parse_errors.append("Function keyword arguments are not supported")

    def errors(self, keys):
        """Validate the function call and its arguments, returning a list of errors if any"""
        errs = self.parse_errors[:]
        if self.object:
            errs.extend(self.object.errors(keys))
            if self.func not in ALLOWED_METHODS:
                errs.append(f"Unsupported method call: {self.func}")
        elif self.func and self.func not in ALLOWED_FUNCTIONS:
            errs.append(f"Unsupported function call: {self.func}")
        for arg in self.args:
            errs.extend(arg.errors(keys))
        return errs

    def __call__(self, metadata):
        """Return the result of the function call"""
        if self.func is None:
            raise ValueError("Function name is not set")
        if self.object:
            obj = self.object(metadata)
            if not hasattr(obj, self.func):
                raise ValueError(f"Object {obj} has no method {self.func}")
            func = getattr(obj, self.func)
        else:
            func = ALLOWED_FUNCTIONS[self.func]
        args = [arg(metadata) for arg in self.args]
        return func(*args)

    def __str__(self):
        return f"{self.func}(" + ", ".join(str(arg) for arg in self.args) + ")"

class ExprBadNode(Expression):
    """Class to represent an unsupported node in an expression"""
    def __init__(self, node):
        self.name = op_name(node)

    def errors(self, keys):
        """Return an error indicating that the node is unsupported"""
        return [f"Unsupported operation: {self.name}"]

    def __call__(self, metadata):
        """Raise an error indicating that the node is unsupported"""
        raise NotImplementedError(f"Unsupported operation: {self.name}")

    def __str__(self):
        return self.name

ALLOWED_NODES = {
    ast.Name:       ExprKey,
    ast.Attribute:  ExprKey,
    ast.Constant:   ExprConst,
    ast.List:       ExprList,
    ast.UnaryOp:    ExprUnaryOp,
    ast.BinOp:      ExprBinaryOp,
    ast.BoolOp:     ExprBoolOp,
    ast.Compare:    ExprComparison,
    ast.Call:       ExprFunc
}

def parse_node(node):
    """Parse an expression from the config file and return a callable function"""
    if type(node) in ALLOWED_NODES:
        return ALLOWED_NODES[type(node)](node)
    return ExprBadNode(node)

def parse(cond: str, debug=False) -> Expression:
    """Parse an expression from the config file and return a callable function"""
    try:
        tree = ast.parse(cond, mode='eval')
    except SyntaxError as e:
        err = cond[e.offset-1:e.end_offset-1] if e.offset and e.end_offset else ""
        msg = f"Syntax error in expression '{cond}'"
        if err.count('=') == 1:
            msg = f"{msg}: '{err}' (assignment not allowed)"
        elif err:
            msg = f"{msg}: '{err}'"
        raise SyntaxError(msg) from e
    expr = parse_node(tree.body)
    if debug:
        print(f"Parsed expression '{cond}':\n  {str(expr)}")
    return expr
