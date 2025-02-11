import json
import tomllib
from pathlib import Path
from .datatypes import *
from .datatypes import _Primitive

root_path: Path
"""The root directory of the data file used to build the current tree. This is
   safe to access from setter methods to get additional files in the relative
   path."""


def build_json(root_type: type[Block], path: Path | str) -> Block:
    """Builds a JSON file into a Block of the provided type."""
    global root_path
    root_path = Path(path).parent.absolute()
    with open(path, 'rb') as f:
        data = json.load(f)
    return build(root_type, data)


def build_toml(root_type: type[Block], path: Path | str) -> Block:
    """Builds a TOML file into a Block of the provided type."""
    global root_path
    root_path = Path(path).parent.absolute()
    with open(path, 'rb') as f:
        data = tomllib.load(f)
    return build(root_type, data)


def build(root_type: type[Block], data: dict) -> Block:
    """Builds a dict into a Block of the provided type."""
    root_item = root_type().instantiate(None)
    root_item.build(data)
    return root_item


def visualize(block: Block) -> str:
    """Generates a string containing a visual tree of the data structure
       hierarchy in a Block."""
    return _visualize(block)


def _visualize(block: Array | Block, indent: int = 0, offset: int = 0) -> str:
    out_string = ''
    if isinstance(block, Array):
        items = [('', elem) for elem in block.get_items()]
    else:
        items = zip([name for name in block._fields()], [item for item in block.get_items()])
    for name, item in items:
        if not item:
            continue
        out_string += _print_item(item, name, indent, offset)
        if isinstance(item, Array) or isinstance(item, Block):
            out_string += _visualize(item, indent + 1, item.offset() + offset)
    return out_string


def _print_item(item: DatatypeBase, name: str, indent: int, offset: int) -> str:
    type_name = type(item).__name__
    if isinstance(item, Array):
        type_name += f"[{type(item._model).__name__}] ({len(item)})"
    elif isinstance(item, Optional):
        type_name += f"[{type(item.model).__name__}]"
    if name:
        type_name = f"{name}: {type_name}"
    f_indent = ' ' * indent * 2
    f_global_offset = hex(item.offset() + offset)
    f_size = hex(item.size())
    out_string = ''
    # If drawing an array of primitives, collapse into '...'
    if isinstance(item, _Primitive) and isinstance(item.parent, Array):
        if item.parent.get_items()[0] is item:
            out_string = f"{f_indent}{f_global_offset} ..."
    else:
        out_string = f"{f_indent}{f_global_offset} ({f_size}) {type_name}"
    if out_string:
        out_string += '\n'
    return out_string
