# Build-A-File

Build-A-File (BAF) is a simple, hackable Python framework that makes it easy to design and build your very own custom binary filetypes.

BAF, used as an internal tool to build complex level files for *Magicore Anomala*, was originally created to assist with developing games targeting Amiga and other retro systems. However, it can be used for any general purpose.

BAF is a one-way tool: It takes source data and builds it into a binary file. If you want to reverse-engineer existing binary files into an ORM, check out [Mr. Crowbar](https://github.com/moralrecordings/mrcrowbar), which inspired this project.

## Key Features

- Write simple, self-documenting code used as both the design model and the build step for your custom file
- Read in data from a TOML or JSON file, with key/value pairs corresponding to your custom datatypes, and BAF builds it into a binary file
- Use setters to add data programmatically, such as getting an offset to another piece of data, or running a file path through an external tool to insert the result
- BAF automatically resolves dependencies by building in the order needed, e.g. to satisfy a setter needing the size of another piece of data
- Small, hackable source makes it easy to add features and adjust behavior if needed

## Requirements

BAF requires Python 3.12 or higher.

## Basic use

### Simple example

With BAF, data structures are defined using `Block`s. Create a class that derives from `Block`, then add some attributes.

In your TOML file, create some corresponding entries with the same names as your attributes. When you run `build_toml()` and specify your new class, BAF will automatically build all the fields with the data from the TOML file.

`example.py`:

```python
import baf
from baf.datatypes import *

class Level(Block):
    world_num = U8()
    level_num = U8()
    setting = U8()
    bgm_id = U8()


level = baf.build_toml(Level, 'example.toml')
level_bytes = level.get_bytes()
print(level_bytes.hex())
# Write file to disk
with open('out.bin', 'wb') as f:
    f.write(level_bytes)
```

`example.toml`:

```toml
world_num = 2
level_num = 1
setting = 0
bgm_id = 7
```

Output:

```console
$ python example.py
02010007
```

### Setters

Using setters, you can set data using code instead of directly from the TOML file.

`example.py`:

```python
import baf
from baf.datatypes import *

class Level(Block):
    world_num = U8()
    level_num = U8()
    setting = U8()
    bgm_id = U8()
    name_length = U8()
    name = Bytes()

    def set_name_length(self, data):
        return self.name.size()

    def set_name(self, data):
        return bytes(data['name'], 'UTF8')

...
```

`example.toml`:

```toml
world_num = 2
level_num = 1
setting = 0
bgm_id = 7
name = "Example Level"
```

Output:
```console
$ python example.py
020100070d4578616d706c65204c6576656c
```

Above, `set_name_length()` returns the size of `name` instead of using any data from the TOML.

Meanwhile, `set_name()` takes a string from the TOML and converts it to bytes in the desired encoding. Whatever data is given to the `Block` will also be passed to the setter. So, if you need that data to determine your value, you can use it.
### Nested `Block`s

You can nest `Block`s to create more complex data structures.

`example.py`:

```python
import baf
from baf.datatypes import *

class LevelHeader(Block):
    world_num = U8()
    level_num = U8()
    setting = U8()
    bgm_id = U8()
    name_length = U8()
    name = Bytes()

    def set_name_length(self, data):
        return self.name.size()

    def set_name(self, data):
        return data['name'].encode('UTF8')


class LevelData(Block):
    width = U16()
    height = U16()
    spawn_x = U16()
    spawn_y = U16()


class Level(Block):
    version = Bytes(default='LV01'.encode('UTF8'))
    header = LevelHeader()
    data = LevelData()

...
```

`example.toml`:

```toml
[header]
world_num = 2
level_num = 1
setting = 0
bgm_id = 7
name = "Example Level"

[data]
width = 1024
height = 400
spawn_x = 16
spawn_y = 16
```

Output:
```console
$ python example.py
4c563031020100070d4578616d706c65204c6576656c0400019000100010
```

Now, `Level` is a top-level struct that holds `header` and `data`. The corresponding keys are found in the TOML, and everything nested under them is passed to `LevelHeader` and `LevelData`, respectively.

Also note how `version` has a `default` parameter. Most datatypes accept a default of the appropriate type (`bytes` for `Bytes`, `int` for `U8`, `dict` for `Block`, etc.). If no data or setters are found, the default value is used.

### `size()` and `offset()`

Since `header` is a variable length, we might need to know the offset to `data`.

```python
class Level(Block):
    version = Bytes(default='LV01'.encode('UTF8'))
    data_offset = U16()
    header = LevelHeader()
    data = LevelData()

    def set_data_offset(self, data):
        return self.data.offset()
```

You can call `size()` and `offset()` on any of the class attributes in this way. Since `header` has a variable size, `data_offset` is unknown until `header` is built. BAF will attempt builds in multiple passes until all dependencies are met. If there are cyclical dependencies, you will get an error.

### `Array`

The `Array` datatype takes TOML/JSON arrays and Python lists.

```python
class Enemy(Block):
    kind = U8()
    spawn = Array(U16(), 2)


class LevelData(Block):
    width = U16()
    height = U16()
    spawn = Array(U16(), 2)
    checkpoints = Array(U16())
    enemies = Array(Enemy())
```

```toml
[data]
width = 1024
height = 400
spawn = [16, 16]
checkpoints = [60, 180, 320, 400]

[[data.enemies]]
kind = 1
spawn = [100, 32]

[[data.enemies]]
kind = 1
spawn = [240, 32]

[[data.enemies]]
kind = 2
spawn = [280, 56]

```

`Array` has an optional size parameter, which enforces an exact item count (and can give it a statically-known size). Above, `spawn` must have 2 items, but `checkpoints` and `enemies` can have any (or none).

### `File`

The `File` datatype accepts a file path string that can be either absolute, or relative to your input file. The file is read and inserted into your data structure as raw bytes.

If you need the root path of the input file yourself (e.g. for use in a setter), you can access it via `baf.root_path`.

```python
class LevelData(Block):
    width = U16()
    height = U16()
    spawn = Array(U16(), 2)
    checkpoints = Array(U16())
    enemies = Array(Enemy())
    splash_image = File()
```

```toml
[data]
width = 1024
height = 400
spawn = [16, 16]
checkpoints = [60, 180, 320, 400]
splash_image = "level1/splash.raw"
```

### `Align`

The `Align` datatype can be used if you need to pad your data to a certain size.

```python
class AnimDef(Block):
    frame_count = U8
    loop_frame = U8
    sprite_ids = Array(U8())
    sprite_ids_align = Align(2)
```

```toml
[[spritesheet.animations]]
frame_count = 5
loop_frame = 4
sprite_ids = [0, 1, 2, 3, 4]
```

Above, since `sprite_ids` is 5 bytes, `sprite_ids_align` will add a byte of padding to align the data to a multiple of 2.

### `Optional`

You can wrap any datatype in `Optional()`. If no data is found, or the setter returns `None`, that attribute will have a size and output of 0 bytes.

```python
class Spritesheet(Block):
    gfx_offset = U16()
    has_anims = U8()
    pivot = S8(default=0)
    palette = Array(U8(), 32)
    anims = Optional(Anims())
    gfx = SpriteGFX()
```

## Advanced use

### Preprocessing

Any datatype can be given a `preprocess()` method that lets you manipulate the received data before the object is built. It can also be a good time for data validation.

```python
from baf.errors import ValidationError

class LevelHeader(Block):
    world_num = U8()
    level_num = U8()
    setting = U8()
    bgm_id = U8()
    name_length = U8()
    name = Bytes()

    def preprocess(self, data):
        if len(data['name']) == 0:
            raise ValidationError("Name must not be empty")
```

### Integrating with external tools

Python makes it easy to run external processes and grab the output. You can do this in your setter—for example, to run your source file through a compression algorithm before returning the bytes.

```python
import subprocess

class LevelData(Block):
    width = U16()
    height = U16()
    background = Bytes()

    def set_background(self, data):
        path = data['background_path']
        background = subprocess.check_output(['bin/some_tool', '--stdout', path])
        return background
```

```toml
[data]
width = 1024
height = 400
background_path = "images/background.png"
```

### Custom datatypes

You can build on top of BAF with custom datatypes that suit your purposes.

For example, BAF doesn't have built-in `Bool` or `String` datatypes because they can have different implementations depending on the platform. It's easy to define your own.

```python
class Bool(U8):

    def preprocess(self, data: bool) -> int:
        return 0xff if data else 0

    def __bool__(self) -> bool:
        return int(self) != 0


class String(Bytes):

    def __init__(self, *, default: str | None = None) -> None:
        super().__init__(default=default.encode('UTF8'))

    def preprocess(self, data: str) -> bytes:
        return data.encode('UTF8')


class LevelData(Block):
    width = U16()
    height = U16()
    has_boss = Bool(default=False)
    boss_name = String(default='The Guy')
```

```toml
[data]
width = 1024
height = 400
has_boss = true
boss_name = 'Kraidgeif'
```

Above, `String` needs a constructor because it inherits `Bytes` but we want it to accept a string as a default value. (`Bool` doesn't need this because `bool` is a subclass of `int` in Python.)

Below is an example of a custom `List` datatype which combines item count, item offsets, and item data.

```python
class List[T: Datatype](Block):
    """Contains item count, item offsets, and a byte array of all the items."""
    count = U16()
    offsets = Array(U32())
    items = Array[T]()

    def preprocess(self, data: list) -> dict:
        # Wrap data in a dict to be Block-compliant
        return {'items': data}

    def set_count(self, _):
        return len(self.items)

    def set_offsets(self, _):
        start_offset = 2 + 4 * int(self.count)
        return [start_offset + item.offset() for item in self.items.get_items()]


class Rooms(List[Room]):
    count = U16()
    offsets = Array(U32())
    items = Array(Room())


class Spritesheets(List[Spritesheet]):
    count = U16()
    offsets = Array(U32())
    items = Array(Spritesheet())
```

When building, BAF ignores the fields in the base `List` class—it only cares about those in the derived `Rooms` and `Spritesheets` classes. Notice how `items` contains a different `Array` type in `Rooms` and `Spritesheets`.

Side note: `Array` has limited support for passing in generic types, as shown above, to help with static type checkers.

### Accepting multiple datatypes

Sometimes you want your `Array` or a field in your `Block` to accept multiple possible datatypes. To do this, you can make the datatype a base type (e.g. `Block` or a base type of your creation).

Then, when you return data from the setter, wrap it in a tuple: `(MyDatatype(), data)` where `MyDatatype` is the type you want the data to build into.

```python
class AssetDefs(Block):
    asset_count = U16()
    asset_data = Array(Block())

    def set_asset_data(self, data):
        asset_list = []
        for key, value in data.items():
            datatype = ASSET_TYPES[key]
            asset_list.append((datatype(), value))
        return asset_list
```

### Controlling build order by forcing dependencies

BAF builds `Block` fields in linear order. If you want to prevent a setter from attempting to run until other data is built, you can use `force_dependency()`.

```python
class AssetDefs(Block):
    asset_count = U16()
    asset_defs = Array(AssetDef())
    # deferred_data is above asset_data but must be built later
    deferred_data = Array(Asset())
    asset_data = Array(Asset())

    def set_deferred_data(self, _):
        self.force_dependency(self.asset_data)
        ...

```

Usually, this isn't necessary because BAF handles dependencies as they come up. However, `force_dependency()` helps in these two cases:

1. You want to ensure the dependency error occurs before any work is attempted (e.g. if the work is expensive or runs an external process)
2. You are tracking a global state that must finish getting populated by other parts of the build before it can be used by the data that needs it

### Building datatypes manually

BAF takes data from your TOML or setter and builds each object behind the scenes. If need be, you can build objects manually, but there is usually a better way of doing things.

In either `preprocess()` or a setter, you can replace the raw data with an object you've already built.

```python
    def set_spritesheet(self, data):
        model = self.spritesheet
        datum = model.instantiate(self)
        datum.build(data)
        return datum
```

BAF will notice it received the final object instead of raw data, and simply insert that object instead of performing its own build.

The build process is as follows:

1. Retrieve a *model* (e.g. `model = self.some_field`) or create a new one (e.g. `model = Spritesheet()`).
2. Instantiate the model into a *datum*. The parameter sets the parent object (e.g. `datum = model.instantiate(self)`).
3. Build the datum by passing your raw data into it: `datum.build(spritesheet_data)`

### Visualizer

After getting your fully-built file with `baf.build_toml()`, you can use `baf.visualize()` to view a tree of your file.

```python
level = baf.build_toml('visualizer_example.toml', Level)
tree = baf.visualize(level)
print(tree)
```

Output:
```console
$ python visualizer_example.py
0x0 (0x4) version: Bytes
0x4 (0x2) data_offset: U16
0x6 (0x12) header: LevelHeader
  0x6 (0x1) world_num: U8
  0x7 (0x1) level_num: U8
  0x8 (0x1) setting: U8
  0x9 (0x1) bgm_id: U8
  0xa (0x1) name_length: U8
  0xb (0xd) name: Bytes
0x18 (0x1f) data: LevelData
  0x18 (0x2) width: U16
  0x1a (0x2) height: U16
  0x1c (0x4) spawn: Array[U16] (2)
    0x1c ...
  0x20 (0x8) checkpoints: Array[U16] (4)
    0x20 ...
  0x28 (0xf) enemies: Array[Enemy] (3)
    0x28 (0x5) Enemy
      0x28 (0x1) kind: U8
      0x29 (0x4) spawn: Array[U16] (2)
        0x29 ...
    0x2d (0x5) Enemy
      0x2d (0x1) kind: U8
      0x2e (0x4) spawn: Array[U16] (2)
        0x2e ...
    0x32 (0x5) Enemy
      0x32 (0x1) kind: U8
      0x33 (0x4) spawn: Array[U16] (2)
        0x33 ...
```

### Errors

If an error occurs, BAF will add notes to the exception containing a traceback of your data structures, so you can pinpoint what data or setter caused the issue.

BAF doesn't discard or sanitize the full Python traceback, so it's ugly by default. If you want it to look nice, catch the exception yourself and log `__notes__`, as shown below. However, the default Python exception will also show the notes at the bottom, so this is optional.

```python
import sys
import baf

try:
    level = baf.build_toml(Level, 'error_example.toml')
except Exception as e:
    print(f"ERROR: {e}\nTraceback:")
    print('\n'.join(e.__notes__))
    sys.exit(1)
```

```toml
[[spritesheet.animations]]
frame_count = 5
loop_frame = 4
sprite_ids = [0, 1, 2, 3, 4, "bad data"]
```

Output:
```console
$ python error_example.py
ERROR: Expected int type, received str
Traceback:
Array[U8] -> (element 5)
AnimDef -> sprite_ids: Array
Array[AnimDef] -> (element 0)
Anims -> anim_data: Array
Spritesheet -> anim_list: Anims
Array[Spritesheet] -> (element 1)
Spritesheets -> items: Array
AssetDefs -> asset_data: Array
Level -> assets: AssetDefs
```
