import ast

from typing import Any, Dict


def str_to_literal(value: str) -> Any:
    if value.isdigit():
        return int(value)
    elif value.lower() in ("true", "false"):
        return value.lower() == "true"
    elif value.replace('.', '', 1).isdigit() and '.' in value:
        return float(value)
    else:
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            return value


def parse_args(args_str: str, defaults: Dict[str, Any] = None) -> Dict[str, Any]:
    args: Dict[str, Any] = {}
    for arg in args_str.split():
        key, _, value = arg.partition("=")
        if value:
            args[key.lower()] = str_to_literal(value)
    return {**defaults, **args} if defaults else args
