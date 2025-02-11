from __future__ import annotations
import typing
from typing import Any, ClassVar, Self, Sequence, TypeVar
from collections.abc import Callable
from abc import ABC, abstractmethod
from dataclasses import dataclass
import copy
from pathlib import Path
import baf
from .errors import *

class DatatypeBase[T: DatatypeBase](ABC):
    """The abstract base class of all BAF datatypes."""

    parent: Container | None = None
    """The parent datum of this datum."""
    _is_instance: bool = False
    """Whether this is an instantiated datum (if not, it is a model)."""
    _is_built: bool = False
    """Whether this datum has been built."""
    _generic_type: T | None = None

    @property
    def root_datum(self) -> DatatypeBase:
        """Gets the root datum of the tree this datum belongs to."""

        if (parent := self.parent) is None:
            return self
        while parent.parent is not None:
            parent = parent.parent
        return parent

    def build(self, data: Any, /) -> None:
        """Builds this datum with the provided data."""

        if not self._is_instance:
            raise BuildError("Attempted to build a non-instantiated model")
        if self._is_built:
            raise BuildError("Attempted to build an already-built datum")
        self._is_built = True
        self._build(data)

    @abstractmethod
    def _build(self, data: Any, /) -> None:
        ...

    def get_bytes(self) -> bytes:
        """Outputs this datum in its final form of raw bytes."""
        if not self._is_instance:
            raise BuildError("Attempted to get bytes from a non-instantiated model")
        if not self._is_built:
            raise BuildError("Attempted to get bytes from a datum that has not yet been built")
        return self._get_bytes()

    @abstractmethod
    def _get_bytes(self) -> bytes:
        ...

    @abstractmethod
    def size(self) -> int:
        """Gets the total size, in bytes, of this datum."""
        ...

    def offset(self) -> int:
        """Gets the offset, in bytes, of this datum, relative to its parent. If
           the parent is None (i.e. this is the root), the offset is 0."""

        if self.parent is None:
            return 0
        return self.parent.offset_of(self)

    def instantiate(self, parent: Container | None) -> Self:
        """Instantiates a datum from this model."""

        if self._is_built:
            raise BuildError("Attempted to instantiate from a datum that is building or already built")
        datum = copy.copy(self)
        if orig := getattr(datum, '__orig_class__', None):
            datum._generic_type = typing.get_args(orig)[0]
        # If type argument is TypeVar (T), we're inheriting from a generic
        # parent, so get that type instead
        if type(datum._generic_type) is TypeVar:
            if parent is None:
                raise InternalError("Datum with TypeVar does not have a parent")
            datum._generic_type = parent._generic_type
        datum.parent = parent
        datum._is_instance = True
        return datum


class Datatype[T](DatatypeBase, ABC):
    """The base class for standard datatypes that are built from input data."""

    _default_value: T | None = None

    def __init__(self, *, default: T | None = None) -> None:
        self._default_value = default

    @abstractmethod
    def _process(self, data: Any) -> None:
        ...

    def _build(self, data: Any) -> None:
        data = self.preprocess(data)
        data = self._preprocess(data)
        self._process(data)

    def _preprocess(self, data: Any) -> Any:
        return data

    def preprocess(self, data: Any) -> Any:
        return data


class GenDatatype(DatatypeBase, ABC):
    """The base class for datatypes that generate their own data when built,
       without the need for input data."""

    def _build(self, _: None = None) -> None:
        self.preprocess()
        self._preprocess()
        self._process()

    def _preprocess(self) -> None:
        pass

    def preprocess(self) -> None:
        pass

    def _process(self) -> None:
        pass


class Container[T](Datatype, ABC):
    """The base class for datatypes that hold a collection of other datatypes.
       Their output is the combined output of all datums in their
       collection."""

    def __init__(self, *, default: T | None = None) -> None:
        super().__init__(default=default)

    @abstractmethod
    def get_items(self, default_if_missing: bool = False) -> Sequence[DatatypeBase]:
        """Gets all the datums, in order, in this container. If
           default_if_missing is False, this will fail if the Container is not
           yet fully built. If default_if_missing is True, the output will
           include default instantiated datums for any models that have not yet
           been instantiated (allowing you to retrieve statically-known
           information about the models)."""
        ...

    def size(self) -> int:
        return sum(item.size() for item in self.get_items(True))

    def offset_of(self, target: DatatypeBase) -> int:
        offset = 0
        for item in self.get_items(True):
            if item is target:
                return offset
            offset += item.size()
        raise InternalError("Could not find self in parent")

    def _get_bytes(self) -> bytes:
        return b''.join([item.get_bytes() for item in self.get_items()])

    def _unpack_type(self, model: DatatypeBase, data: Any) -> tuple[DatatypeBase, Any]:
        """The user can declare a field as a more generic type (e.g. Block) and
           then submit the data as a tuple to resolve the final type of the
           data. This checks for that tuple and updates the model if needed."""
        if not self._is_packed_type(data):
            return model, data
        new_model = data[0]
        # Ensure proposed datatype is a subclass of original model
        if not isinstance(new_model, type(model)):
            raise BuildError(f"Dynamically-resolved Datatype {type(new_model).__name__} is not a child of {type(model).__name__}")
        return new_model, data[1]

    def _is_packed_type(self, data) -> bool:
        # Looking for (SomeType, data)
        if not isinstance(data, tuple) or len(data) != 2:
            return False
        proposed_model = data[0]
        # Ensure our 2-item sequence is a proposed dynamic datatype
        if not isinstance(proposed_model, DatatypeBase):
            return False
        return True


class _Primitive(Datatype[int], ABC):
    """The base class of all primitive integer datatypes."""

    _bit_size: ClassVar[int]
    _min: ClassVar[int]
    _max: ClassVar[int]
    _data: int | None = None

    def _process(self, data: int) -> None:
        self._data = data

    def _preprocess(self, data) -> int:
        if type(data) is not int:
            raise ValidationError(f"Expected int, received {type(data).__name__}")
        if data < self._min or data > self._max:
            raise ValidationError(f"Value {data} outside of {type(self).__name__} range, must be {self._min} to {self._max}")
        return data

    def size(self) -> int:
        return self._bit_size // 8

    @classmethod
    def static_size(cls) -> int:
        """Gets the statically-known size of this class."""

        return cls._bit_size // 8

    def _get_bytes(self) -> bytes:
        if self._data is None:
            raise BuildError("Primitive does not yet have a value")
        return self._data.to_bytes(self.size(), signed=self._data < 0)

    def __int__(self) -> int:
        if self._data is None:
            raise DependencyError("Primitive does not yet have a value")
        return self._data


class U8(_Primitive):
    """Datatype for 8-bit unsigned integers. Supports int() conversion."""

    _bit_size = 8
    _min = 0
    _max = 2 ** 8 - 1


class U16(_Primitive):
    """Datatype for 16-bit unsigned integers. Supports int() conversion."""

    _bit_size = 16
    _min = 0
    _max = 2 ** 16 - 1


class U32(_Primitive):
    """Datatype for 32-bit unsigned integers. Supports int() conversion."""

    _bit_size = 32
    _min = 0
    _max = 2 ** 32 - 1


class S8(_Primitive):
    """Datatype for 8-bit signed integers."""

    _bit_size = 8
    _min = -2 ** 8 // 2
    _max = 2 ** 8 // 2 - 1


class S16(_Primitive):
    """Datatype for 16-bit signed integers. Supports int() conversion."""

    _bit_size = 16
    _min = -2 ** 16 // 2
    _max = 2 ** 16 // 2 - 1


class S32(_Primitive):
    """Datatype for 32-bit signed integers. Supports int() conversion."""

    _bit_size = 32
    _min = -2 ** 32 // 2
    _max = 2 ** 32 // 2 - 1


class I8(_Primitive):
    """Datatype for 8-bit integers which can ambiguously be signed or
       unsigned. Supports int() conversion."""

    _bit_size = 8
    _min = S8._min
    _max = U8._max


class I16(_Primitive):
    """Datatype for 16-bit integers which can ambiguously be signed or
       unsigned. Supports int() conversion."""

    _bit_size = 16
    _min = S16._min
    _max = U16._max


class I32(_Primitive):
    """Datatype for 32-bit integers which can ambiguously be signed or
       unsigned. Supports int() conversion."""

    _bit_size = 32
    _min = S32._min
    _max = U32._max


class Bytes(Datatype[bytes]):
    """Datatype for a sequence of raw bytes."""

    _size: int | None = None
    _data: bytes

    def __init__(self, size: int | None = None, *, default: bytes | None = None) -> None:
        self._size = size
        super().__init__(default=default)

    def _process(self, data: bytes) -> None:
        self._data = data

    def _preprocess(self, data) -> bytes:
        if not isinstance(self._size, int | None):
            raise SpecError(f"Bytes size parameter must be int; received {type(self._size).__name__}")
        if type(data) is not bytes and type(data) is not bytearray:
            raise ValidationError(f"Expected bytes type, received {type(data).__name__}")
        if self._size is not None and len(data) != self._size:
            raise ValidationError(f"Expected {self._size} bytes but data is {len(data)} bytes")
        return bytes(data)

    def size(self) -> int:
        if self._size is not None:
            return self._size
        if not hasattr(self, '_data'):
            raise DependencyError("Size of Bytes is not yet known")
        return len(self._data)

    def _get_bytes(self) -> bytes:
        return self._data


class File(Datatype[str]):
    """Datatype that accepts a file path and outputs the raw bytes of that
       file."""

    _data: bytes

    def _process(self, data: bytes) -> None:
        self._data = data

    def _preprocess(self, data) -> bytes:
        try:
            path = Path(data)
        except TypeError:
            raise ValidationError(f"File datatype expected PathLike or str, received {type(data).__name__}")
        if not path.is_absolute():
            path = baf.root_path/path
        if not Path.exists(path):
            raise ValidationError(f"File does not exist: {path}")
        with open(path, 'rb') as f:
            return f.read()

    def size(self) -> int:
        if not hasattr(self, '_data'):
            raise DependencyError("Size of File is not yet known")
        return len(self._data)

    def _get_bytes(self) -> bytes:
        return self._data


@dataclass
class _BlockItem:
    name: str
    model: DatatypeBase
    base_data: Any
    data: Any = None
    setter: Callable | None = None
    setter_done: bool = False
    done: bool = False

    def build(self, parent: Block) -> None:
        if self.setter and not self.setter_done:
            self.data = self.setter(self.base_data)
            self.setter_done = True
        if isinstance(self.data, type(self.model)):
            setattr(parent, self.name, self.data)
            self.done = True
            return
        item_model, item_data = parent._unpack_type(self.model, self.data)
        item = item_model.instantiate(parent)
        setattr(parent, self.name, item)
        item.build(item_data)
        self.done = True


class Block(Container[dict], ABC):
    """The base class for most user-defined datatypes. It builds data based on
       its class attributes."""

    # Instantiate empty datatypes with a parent so offset() works more reliably
    # in setters
    def __init__(self, *, default: dict | None = None) -> None:
        for name, model in self._fields().items():
            setattr(self, name, model.instantiate(self))
        super().__init__(default=default)

    def _process(self, data: dict) -> None:
        blockitems = [_BlockItem(name, model, data) for name, model in self._fields().items()]
        for item in blockitems:
            item.setter = getattr(self, 'set_' + item.name, None)
        for item in blockitems:
            name, model = item.name, item.model
            # Check if this field is in dict data
            if name in data:
                item.data = data[name]
            # Check for default value
            elif isinstance(model, Datatype) and model._default_value is not None:
                item.data = model._default_value
        # Build blocks until all dependencies are resolved
        while any(not blockitem.done for blockitem in blockitems):
            progress = False
            for item in blockitems:
                if item.done:
                    continue
                try:
                    item.build(self)
                except DependencyError:
                    continue
                except Exception as e:
                    e.add_note(f'{type(self).__name__} -> {item.name}: {type(item.model).__name__}')
                    raise
                progress = True
            # If nothing got resolved in a full pass, cyclical dependencies
            if not progress:
                raise BuildError("Could not resolve dependencies. Check for cyclical dependencies in: "
                    f"{', '.join([item.name for item in blockitems if not item.done])}")

    @classmethod
    def _fields(cls) -> dict[str, DatatypeBase]:
        return {k:v for (k, v) in cls.__dict__.items() if not k.startswith('_') and isinstance(v, DatatypeBase)}

    def _preprocess(self, data) -> dict:
        if type(data) is not dict:
            raise ValidationError(f"Expected dict, received {type(data).__name__}")
        for name, model in self._fields().items():
            if isinstance(model, GenDatatype | Optional) or isinstance(model, Datatype) and model._default_value is not None:
                continue
            if name in data or hasattr(self, 'set_' + name):
                continue
            raise ValidationError(f"No setter or dict value found for {name}")
        return data

    def get_items(self, default_if_missing: bool = False) -> Sequence[DatatypeBase]:
        if not default_if_missing:
            return [getattr(self, name) for name in self._fields()]
        return [getattr(self, name, default) for (name, default) in self._fields().items()]

    def force_dependency(self, model: DatatypeBase) -> None:
        """Forces a dependency error if the given model is not yet built, so
           that the current setter does not build until the forced dependency
           does."""
        if not model._is_built:
            raise DependencyError(f"Forced dependency: Model is not yet built")

    @classmethod
    def static_size(cls) -> int:
        """Attempts to get the size of this class, provided all its attributes
           have a statically-known size."""

        return sum(item.size() for item in cls._fields().values())
        

class Array[T: DatatypeBase](Container[Sequence[T]]):
    """Datatype for an array of other datatypes. If known, the item count can
       optionally be specified. This object supports len() but does not
       otherwise behave like a Python list type. Use get_items() to get a list
       of items."""

    _model: T | None
    _item_count: int | None
    _items: list[T]

    def __init__(self, model: T | None = None, item_count: int | None = None, *, default: Sequence[T] | None = None) -> None:
        self._model = model
        self._item_count = item_count
        self._items = []
        super().__init__(default=default)

    def _preprocess(self, data) -> Sequence:
        if self._model is None:
            if self._generic_type is None:
                raise SpecError("Array has no valid type argument")
            self._model = self._generic_type()
        if not isinstance(self._model, DatatypeBase):
            raise SpecError(f"Array type {type(self._model).__name__} is not a Datatype")
        if not isinstance(data, Sequence):
            raise ValidationError(f"Expected Sequence type, received {type(data).__name__}")
        if self._item_count is None:
            self._item_count = len(data)
            return data
        if self._item_count < 0:
            raise SpecError("Array item count cannot be less than 0")
        if len(data) != self._item_count:
            raise ValidationError(f"Expected {self._item_count} items, received {len(data)}")
        return data

    def _process(self, data: Sequence) -> None:
        if self._model is None:
            raise InternalError("Array still has no inferred type in _process()")
        items = []
        for i, data_item in enumerate(data):
            # Check if passing in an already-built item
            if isinstance(data_item, type(self._model)):
                items.append(data_item)
                continue
            model, data_item = self._unpack_type(self._model, data_item)
            item = model.instantiate(self)
            items.append(item)
            try:
                item.build(data_item)
            except Exception as e:
                e.add_note(f'Array[{type(self._model).__name__}] -> (element {i})')
                raise
        self._items = items

    def get_items(self, default_if_missing: bool = False) -> list[T]:
        items = [item for item in self._items]
        if self._item_count is None and not items:
            raise DependencyError("Cannot get items of un-built Array with unknown size")
        if self._item_count is None:
            return items
        items_left = self._item_count - len(items)
        if items_left > 0 and not default_if_missing:
            raise DependencyError("Array is not finished building")
        if self._model is None:
            raise InternalError("Array still has no inferred type in get_items()")
        return items + [self._model.instantiate(self)] * items_left

    def __len__(self) -> int:
        if self._item_count is not None:
            return self._item_count
        return len(self.get_items(True))


class Optional[T: Datatype](DatatypeBase):
    """A wrapper for any Datatype that denotes it as optional. If no data is
       provided to build the datum, it will have a size and output of 0 bytes
       instead of failing.
       Supports __bool__(), i.e. this object is treated as True if it has
       been confirmed to receive data, and False if it has resolved to not
       receive data."""

    _item: T | None = None
    model: T

    def __init__(self, model: T) -> None:
        self.model = model
        super().__init__()

    def _build(self, data: Any | None) -> None:
        self._preprocess(data)
        if data is None or isinstance(data, Sequence) and len(data) == 0:
            return
        item = self.model.instantiate(self.parent)
        item.build(data)
        self._item = item

    def _preprocess(self, _) -> None:
        if not isinstance(self.model, Datatype):
            raise SpecError(f"Optional must wrap a known Datatype but received {type(self.model).__name__}")

    def size(self) -> int:
        if not self._is_built:
            raise DependencyError("Cannot get size of Optional before it's built")
        return self._item.size() if self._item else 0

    def _get_bytes(self) -> bytes:
        return self._item.get_bytes() if self._item else bytes(0)

    def __bool__(self) -> bool:
        if not self._is_built:
            raise DependencyError("Optional is ambiguous until it is built")
        return self._item is not None


class Align(GenDatatype):
    """A datatype that generates the amount of padding needed to align the
       parent container to a specific byte count. For example, Align(2) will
       add padding to give the data 16-bit alignment at that point. If the data
       is already aligned, no padding will be added, and this object will have
       a size and output of 0 bytes."""

    _align_size: int
    _pad_amount: int | None = None

    def __init__(self, align_size: int | DatatypeBase) -> None:
        if isinstance(align_size, DatatypeBase):
            self._align_size = align_size.size()
        else:
            self._align_size = align_size

    def _preprocess(self) -> None:
        if self._align_size < 2:
            raise SpecError("Align size must be at least 2")

    def _process(self) -> None:
        self._pad_amount = self.size()

    def _get_bytes(self) -> bytes:
        if self._pad_amount is None:
            raise BuildError("Cannot get bytes before having been built")
        return bytes(self._pad_amount)

    def size(self) -> int:
        align = self._align_size
        pad_amount = (align - self.offset() % align) % align
        return pad_amount
