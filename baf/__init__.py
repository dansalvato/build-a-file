import inspect
import json
import tomllib
from pathlib import Path
from .datatypes import Array, Block, _Primitive, DataType


def build_json(path: Path | str, root_type: type[Block]) -> Block:
    '''Builds a JSON file into a Block of the provided type.'''
    with open(path) as f:
        data = json.loads(f.read())
    data['_root_path'] = Path(path).parent.absolute()
    return root_type(None, data)


def build_toml(path: Path | str, root_type: type[Block]) -> Block:
    '''Builds a TOML file into a Block of the provided type.'''
    with open(path) as f:
        data = tomllib.loads(f.read())
    data['_root_path'] = Path(path).parent.absolute()
    return root_type(None, data)


def build_dict(data: dict, root_type: type[Block]) -> Block:
    '''Builds a dict into a Block of the provided type.'''
    return root_type(None, data)


def visualize(block: Block) -> str:
    '''Generates a string containing a visual tree of the data structure
    hierarchy in a Block.'''
    return _visualize(block)


def _visualize(block: Block, indent: int = 0, offset: int = 0) -> str:
    out_string = ''
    if isinstance(block, Array):
        items = [('', elem) for elem in block]
    else:
        annotations = inspect.get_annotations(type(block))
        items = [(name, getattr(block, name)) for name in annotations]
    for name, item in items:
        if not item:
            continue
        out_string += _print_item(item, name, indent, offset)
        if isinstance(item, Array) or isinstance(item, Block):
            out_string += _visualize(item, indent + 1, item.offset() + offset)
    return out_string


def _print_item(item: DataType, name: str, indent: int, offset: int) -> str:
    type_name = item.type_name()
    if isinstance(item, Array):
        type_name += f" ({len(item)})"
    if name:
        type_name = f"{name}: {type_name}"
    f_indent = ' ' * indent * 4
    f_global_offset = hex(item.offset() + offset)
    f_local_offset = hex(item.offset())
    out_string = ''
    # If drawing an array of primitives, collapse into '...'
    if isinstance(item, _Primitive) and isinstance(item.parent, Array):
        if item.parent[0] is item:
            out_string = f"{f_indent}{hex(item.offset() + offset)} ..."
    else:
        out_string = f"{f_indent}{f_global_offset} ({f_local_offset}) {type_name}"
    if out_string:
        out_string += '\n'
    return out_string
