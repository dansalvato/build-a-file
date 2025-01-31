from __future__ import annotations
import re
import math
import inspect
from abc import ABC, abstractmethod
from collections.abc import Iterable
from types import UnionType
from typing import Optional, Any, Callable, Sequence, ClassVar
from pathlib import Path
from .errors import DataMissingError, ValidationError, BuildError

RESERVED_NAMES = [
    'offset',
    'global_offset',
    'offset_of',
    'child_level',
    'parent_prop_name',
    'size',
    'bit_size',
    'static_size',
    'to_bytes',
    'type_name',
    'root_path',
]


class DataType(ABC):
    '''The abstract base class of all BAF datatypes.'''

    parent: Optional[Block]

    def __init__(self, parent: Optional[Block]) -> None:
        self.parent = parent
        self._validate()

    def offset(self, parent_level: int = 0) -> int:
        '''Gets the offset (in bytes) of this data in the parent.

        The `parent_level` parameter can be used to get an offset relative
        to multiple parents up, but dependencies cannot be fully resolved for
        that situation, so it can fail if the parents are not yet fully
        built.'''

        offset = 0
        if parent_level > 0 and self.parent:
            offset = self.parent.offset(parent_level - 1)
        if isinstance(self.parent, Array):
            offset += self._offset_in_parent_array(self.parent)
        elif isinstance(self.parent, Block):
            offset += self._offset_in_parent_block(self.parent)
        return offset

    def _offset_in_parent_array(self, parent: Array) -> int:
        offset = 0
        for elem in parent:
            if elem is self:
                break
            offset += elem.size()
        return offset

    def _offset_in_parent_block(self, parent: Block) -> int:
        offset = 0
        for name, datatype in inspect.get_annotations(type(parent), eval_str=True).items():
            attr = getattr(parent, name, datatype)
            if attr is self:
                return offset
            if type(attr) is _Missing:
                attr = datatype
            offset += attr.size()
        raise DataMissingError("Could not find self in parent attributes")

    def global_offset(self) -> int:
        '''Gets the absolute offset from the very beginning of the data tree or
        file. This may fail if the parents are not yet fully built.'''

        return self.offset() + self.parent.global_offset() if self.parent else 0

    def child_level(self) -> int:
        '''Gets the depth of the current child from the root block.'''

        return self.parent.child_level() + 1 if self.parent else 0

    def parent_prop_name(self) -> str:
        '''Attempts to get the property name of this child as defined in the
        parent, or a string of the element number if the parent is an `Array`.
        Returns an empty string if not applicable or unable.'''

        parent = self.parent
        if not parent:
            return ''
        if isinstance(parent, Array):
            for i, elem in enumerate(parent):
                if elem is self:
                    return f'Element {i}'
        else:
            annotations = inspect.get_annotations(type(parent))
            items = [(name, getattr(parent, name)) for name in annotations]
            for name, item in items:
                if item is self:
                    return name
        return ''

    @abstractmethod
    def _get_data(self) -> Any:
        ...

    @classmethod
    @abstractmethod
    def size(cls) -> int:
        '''Gets the size (in bytes) of the data in this datatype. Usable as
        either a class method or an instance method.'''
        ...

    @abstractmethod
    def to_bytes(self) -> bytes:
        '''Gets the raw bytes of the data in this datatype.'''
        ...

    @abstractmethod
    def _validate(self) -> None:
        ...

    def type_name(self) -> str:
        '''Gets the type name of the current datatype.

        If an `Array`, attempts to return `"Array[type]"` if the array type can
        be determined by the parent. If not, returns `"Array"`.'''

        datatype = type(self)
        if datatype.__name__ == 'Array' and self.parent:
            annotations = inspect.get_annotations(type(self.parent))
            for name, type_name in annotations.items():
                if getattr(self.parent, name) is self:
                    array_type = re.match(r'.*\[.*\.(.*)\]', str(type_name))
                    if array_type:
                        return f'Array[{array_type.group(1)}]'
        return datatype.__name__


class _Primitive(DataType, int):
    '''The base class of primitive integer-based datatypes like `U8`, `U16`,
    and `U32`.'''

    bit_size: ClassVar[int]
    _data: int

    def __new__(cls, _: Optional[Block], data: int):
        valid = False
        try:
            int(data)
            valid = True
        except ValueError:
            pass
        if not valid:
            type_name = type(data).__name__
            raise ValidationError(f"Expected int type, received {type_name}")
        return super(_Primitive, cls).__new__(cls, data)

    def __init__(self, parent: Optional[Block], data: int) -> None:
        self._data = data
        super().__init__(parent)

    def _get_data(self) -> int:
        return self._data

    @classmethod
    def size(cls) -> int:
        return cls.bit_size // 8

    @classmethod
    def static_size(cls) -> int:
        return cls.bit_size // 8

    def to_bytes(self) -> bytes:
        return self._data.to_bytes(self.size(), signed=self._data < 0)

    def _validate(self) -> None:
        range_min = -int(math.pow(2, self.bit_size - 1))
        range_max = int(math.pow(2, self.bit_size) - 1)
        if self._data < range_min or self._data > range_max:
            raise ValidationError(f"Value {self._data} outside of range, must be {range_min} to {range_max}")

    def __repr__(self) -> str:
        return f'{self._get_data()} ({hex(self._get_data())})'


class U8(_Primitive):
    '''The datatype representing an 8-bit integer. If a signed value is
    provided, the two's compliment is generated.'''
    bit_size: ClassVar[int] = 8


class U16(_Primitive):
    '''The datatype representing a 16-bit integer. If a signed value is
    provided, the two's compliment is generated.'''
    bit_size: ClassVar[int] = 16


class U32(_Primitive):
    '''The datatype representing a 32-bit integer. If a signed value is
    provided, the two's compliment is generated.'''
    bit_size: ClassVar[int] = 32


class Bytes(DataType):
    '''A sequence of raw bytes.'''

    _data: bytes

    def __init__(self, parent: Optional[Block], data: bytes = bytes(0)) -> None:
        self.size = self._size
        if isinstance(data, str):
            data = data.encode('utf-8')
        self._data = data
        super().__init__(parent)

    def _get_data(self) -> bytes:
        return self._data

    @classmethod
    def size(cls) -> int:
        raise DataMissingError("Attempted to get size of a Bytes object before it was initialized")

    def _size(self) -> int:
        return len(self._data)

    def to_bytes(self) -> bytes:
        return self._data

    def _validate(self) -> None:
        if not isinstance(self._data, (bytes, bytearray)):
            type_name = type(self._data).__name__
            raise ValidationError(f"Expected bytes type, received {type_name}")


class File(Bytes):
    '''A datatype that extends `Bytes` to accept a file path that is either
    absolute or relative to the location of your root file.

    The file is read and inserted as raw bytes.'''

    def __init__(self, parent: Optional[Block], path: str) -> None:
        file_path = Path(path)
        if not file_path.is_absolute() and parent and parent.root_path:
            file_path = parent.root_path/file_path
        try:
            with open(file_path, 'rb') as f:
                data = f.read()
        except Exception as e:
            raise BuildError(f"File read error: {file_path}") from e
        super().__init__(parent, data)


class Empty(DataType):
    '''A datatype of size 0 that never generates any bytes in the output.

    This can sometimes be useful in lieu of `None`, because BAF can parse
    it.'''

    def __init__(self, parent: Optional[Block]) -> None:
        super().__init__(parent)

    def _get_data(self) -> Any:
        return None

    @classmethod
    def size(cls) -> int:
        return 0

    @classmethod
    def static_size(cls) -> int:
        return 0

    def to_bytes(self) -> bytes:
        return bytes(0)

    def _validate(self) -> None:
        pass

    def __bool__(self) -> bool:
        return False


class _Missing(DataType):

    def _get_data(self) -> Any:
        raise DataMissingError("Attempted to get data of an uninitialized object")

    @classmethod
    def size(cls) -> int:
        raise DataMissingError("Attempted to get size of an uninitialized object")

    def to_bytes(self) -> bytes:
        raise DataMissingError("Attempted to get bytes of an uninitialized object")

    def _validate(self) -> None:
        pass

    def __bool__(self) -> bool:
        return False


class Align[T: _Primitive](Bytes):
    '''The data alignment datatype.

    Properties of type `Align` cannot be set directly via setter method or
    data. Instead, an `Align` datatype will produce the amount of padding bytes
    needed for the data structure to reach the desired byte alignment. For
    example, `Align[U32]` will align the data to the next 4-byte boundary.'''

    def __init__(self, parent: Optional[Block], pad_amount: int) -> None:
        super().__init__(parent, bytes(pad_amount))


class Block(DataType):
    '''The base class of custom datatypes and the foundational building block
    of BAF.

    Custom datatypes deriving from `Block` can specify their data using member
    variable annotations, which are then automatically set using data from the
    `dict` provided in instantiation. Setter methods can also be used instead
    of populating data directly from the `dict`.'''

    _current_item: _BlockItem
    root_path: Optional[Path]

    def __init__(self, parent: Optional[Block], data: Optional[Any] = None) -> None:
        self.size = self._size
        self.offset_of = self._offset_of
        self.root_path = None
        if data and '_root_path' in data:
            self.root_path = data['_root_path']
        elif parent is not None and hasattr(parent, 'root_path'):
            self.root_path = parent.root_path
        super().__init__(parent)
        try:
            self._build(data)
        except BuildError as e:
            if hasattr(self, '_current_item'):
                type_name = self.type_name()
                prop_name = self._current_item.name
                prop_type = self._current_item.datatype.__name__
                if prop_name:
                    prop_name = f' -> {prop_name}: {prop_type}'
                e.add_note(f'{type_name}{prop_name}')
            if self.parent is not None:
                raise
            raise

    def _build(self, data: Optional[Any]) -> None:
        annotations = inspect.get_annotations(type(self), eval_str=True)
        blockitems: dict[str, _BlockItem] = {}
        for name, datatype in annotations.items():
            if name in RESERVED_NAMES:
                raise BuildError(f"Name '{name}' is reserved and cannot be used as a property name")
            value = getattr(self, name, None)
            if value is None:
                setattr(self, name, _Missing(self))
            blockitem = _BlockItem(self, name, datatype, value)
            blockitems[name] = blockitem
        for item in blockitems.values():
            item.set_dependencies(blockitems)
        while any(not item.done for item in blockitems.values()):
            success = False
            for name, item in blockitems.items():
                if item.done:
                    continue
                if any(not d.done for d in item.dependencies):
                    continue
                self._current_item = item
                item.build(data)
                success = True
                setattr(self, item.name, item.value)
            if not success:
                failed = [item.name for item in blockitems.values() if not item.done]
                raise BuildError(("Couldn't build all items. Check for circular "
                "dependencies in these properties of "
                f"{type(self).__name__}:\n{failed}"))

    def _get_data(self) -> Sequence[DataType]:
        data = []
        for name in inspect.get_annotations(type(self), eval_str=True):
            data.append(getattr(self, name))
        return data

    @classmethod
    def size(cls) -> int:
        return sum(datatype.size() for datatype in inspect.get_annotations(cls, eval_str=True).values())

    def _size(self) -> int:
        size = 0
        for name, datatype in inspect.get_annotations(type(self), eval_str=True).items():
            attr = getattr(self, name, datatype)
            if type(attr) is _Missing:
                attr = datatype
            size += attr.size()
        return size

    def to_bytes(self) -> bytes:
        return b''.join(d.to_bytes() for d in self._get_data())

    def _validate(self) -> None:
        pass

    def _offset_of(self, prop_name: str) -> int:
        offset = 0
        annotations = inspect.get_annotations(type(self), eval_str=True)
        if not prop_name in annotations:
            raise BuildError(f"Property name '{prop_name}' does not exist in {type(self).__name__}")
        for name, datatype in annotations.items():
            if name == prop_name:
                return offset
            attr = getattr(self, name, datatype)
            if type(attr) is _Missing:
                attr = datatype
            offset += attr.size()
        raise ValueError(f"Property name {prop_name} does not exist in {self.type_name()}")

    @classmethod
    def offset_of(cls, prop_name: str) -> int:
        '''Gets the offset (in bytes) of the given property name. This works as
        both a class method (for statically-known offsets) and as an instance
        method, as long as all preceding properties have a statically-known
        size or have already been populated with their data.

        It's preferable to directly call `offset()` on the child object,
        especially in a setter method, because BAF can figure out the
        dependencies needed before the offset is calculated. However, this
        method can be useful in edge cases where `offset()` doesn't work.'''

        offset = 0
        annotations = inspect.get_annotations(cls, eval_str=True)
        if not prop_name in annotations:
            raise BuildError(f"Property name '{prop_name}' does not exist in {cls.__name__}")
        for name, datatype in annotations.items():
            if name == prop_name:
                return offset
            offset += datatype.size()
        return offset


class _BlockItem:
    done: bool = False
    owner: Block
    offset: Optional[int] = None
    name: str
    datatype: type
    argtype: Optional[type] = None
    value: DataType
    setter: Optional[Callable]
    dependencies: list[_BlockItem]

    def __init__(self, owner: Block, name: str, datatype: type, value: Optional[DataType]) -> None:
        self.owner = owner
        self.name = name
        if value is not None:
            self.value = value
            self.done = True
        if hasattr(datatype, '__name__') and datatype.__name__ in ['Align', 'Array']:
            self.datatype = datatype.__origin__
            self.argtype = datatype.__args__[0]
        else:
            self.datatype = datatype
        self.setter = getattr(self.owner, 'set_' + name, None)

    def set_dependencies(self, items: dict[str, _BlockItem]) -> None:
        '''Populates self.dependencies with all of the BlockItems this one
        depends on in order to successfully build.'''

        if self.datatype is Align:
            self.dependencies = self._get_align_dependencies(items)
            return
        if self.setter is None:
            self.dependencies = []
            return
        deps = []
        closures = inspect.getclosurevars(self.setter).unbound
        if 'offset' in closures or 'offset_of' in closures:
            deps += self._get_offset_dependencies(self.setter, items)
        dep_names = [c for c in closures if c in items]
        for name in items:
            if name in dep_names and not items[name] in deps:
                deps.append(items[name])
        # Check if self-dependency is just offset()
        if self in deps and self.setter:
            source = inspect.getsource(self.setter)
            offset_hits = source.count(f'self.{self.name}.offset()')
            total_hits = source.count(f'self.{self.name}')
            if offset_hits == total_hits:
                deps.remove(self)
            else:
                raise Exception(f"Setter {self.setter.__name__} in {type(self.owner).__name__} is trying to access itself")
        self.dependencies = deps

    def build(self, data: Optional[dict]) -> None:
        if self.setter:
            value = self.setter(data)
        elif data and self.name in data:
            value = data[self.name]
        elif self.datatype is Align and self.argtype:
            if not hasattr(self.argtype, 'static_size'):
                raise BuildError(f"Align argument must be a primitive type with a statically-known size")
            alignment = self.argtype.static_size()
            offset_mod = (self.owner.offset_of(self.name) - 1) % alignment + 1
            pad_needed = alignment - offset_mod
            value = Align(self.owner, pad_needed)
        else:
            raise DataMissingError(f"No setter or dict value found for {self.name}")
        self.value = self._ensure_value_wrapped(value)
        self.done = True

    def _get_align_dependencies(self, items: dict[str, _BlockItem]) -> list[_BlockItem]:
        deps = []
        owner_props = list(inspect.get_annotations(type(self.owner)))
        for prop in owner_props:
            if prop == self.name:
                break
            if not hasattr(items[prop].datatype, 'static_size'):
                deps.append(items[prop])
        return deps


    def _get_offset_dependencies(self, setter: Callable, items: dict[str, _BlockItem]) -> list[_BlockItem]:
        source = inspect.getsource(setter)
        dep_names = []
        called_props = re.findall(r'self\.(.+?).offset\(\)', source)
        called_props += re.findall(r'self\.offset_of\([\'|"](.+?)[\'|"]\)', source)
        owner_props = list(inspect.get_annotations(type(self.owner)))
        for prop in called_props:
            prop_index = owner_props.index(prop)
            dep_names += owner_props[0:prop_index]
        return [items[dep] for dep in set(dep_names) if not hasattr(items[dep].datatype, 'static_size')]

    def _ensure_value_wrapped(self, value: Any) -> DataType:
        if type(value) is self.datatype:
            return value
        if type(self.datatype) is UnionType:
            if type(value) in self.datatype.__args__:
                return value
            else:
                raise TypeError("Can't implicity wrap value into a Union type")
        if self.datatype is Array:
            return self.datatype(self.owner, self.argtype, value)
        return self.datatype(self.owner, value)


class Array[T: DataType](Block, list[T]):
    '''A raw array of items in the specified type.'''

    def __init__(self, parent: Optional[Block], datatype: Optional[type] = None, data: list = []) -> None:
        self.size = self._size
        self._data = data
        super().__init__(parent)
        if datatype:
            for item in data:
                try:
                    self.append(datatype(self, item))
                except BuildError as e:
                    prop_name = f'Array[{datatype.__name__}]'
                    prop_name += f' -> (element {len(self)})'
                    e.add_note(prop_name)
                    raise

    def _get_data(self) -> Sequence[DataType]:
        return self

    @classmethod
    def size(cls) -> int:
        raise DataMissingError("Attempted to get size of an Array before it was initialized")

    def _size(self) -> int:
        return sum(d.size() for d in self)

    def to_bytes(self) -> bytes:
        return b''.join(d.to_bytes() for d in self)

    def _validate(self) -> None:
        if not isinstance(self._data, Iterable):
            type_name = type(self._data).__name__
            raise ValidationError(f"Expected iterable type, received {type_name}")

    # Although this extends list, it should absolutely not return False
    # if empty, because Array is much more Blocky than listy
    def __bool__(self) -> bool:
        return True
