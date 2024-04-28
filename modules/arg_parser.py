import ast

from typing import Any, Dict


def str_to_literal(value: str) -> Any:
    """
    Converts a string to its respective literal value. The function handles integers, floats, booleans,
    and evaluates complex data types like lists, dictionaries, etc., using 'ast.literal_eval'.

    Args:
        value (str): The string to be converted to a literal value.

    Returns:
        Any: The literal value represented by the string.
             - Returns an integer if the string is an integer literal.
             - Returns a float if the string is a float literal.
             - Returns a boolean if the string is 'true' or 'false'.
             - Attempts to evaluate the string as a complex data type using 'ast.literal_eval'.
             - Returns the original string if it does not represent any other literal types.
    """
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
    """
    Parses a string of arguments and converts them into a dictionary with key-value pairs.
    The arguments are expected to be in the format 'key=value'. It also merges with default
    values provided in the 'defaults' dictionary.

    Args:
        args_str (str): The string containing arguments to parse.
        defaults (Dict[str, Any], optional): A dictionary containing default values for keys. Defaults to None.

    Returns:
        Dict[str, Any]: A dictionary with keys and their corresponding parsed literal values.
                        If a default dictionary is provided, the parsed arguments will be merged with it,
                        with the parsed arguments taking precedence over any defaults.
    """
    args: Dict[str, Any] = {}
    for arg in args_str.split():
        key, _, value = arg.partition("=")
        if value:
            args[key.lower()] = str_to_literal(value)
    return {**defaults, **args} if defaults else args
