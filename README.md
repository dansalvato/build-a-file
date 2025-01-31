# Build-A-File

Build-A-File (BAF) is a framework that makes it easy to create custom binary file formats and assemble your data into them.

It was originally created to easily build binary data files for games targeting Amiga and other retro systems. However, BAF can be used for any general purpose. It was born as an internal-only tool, so it's a bit rough around the edges, but if you follow the rules then it gets the job done. :)

BAF is a one-way tool: It takes source data and builds it into a binary file. If you want to reverse-engineer existing binary files into an ORM, check out [Mr. Crowbar](https://github.com/moralrecordings/mrcrowbar), which inspired this project (and is probably much more well-written).

## Requirements

BAF requires Python 3.12 or higher.

## Examples

### Basic example

With BAF, data structures are defined using `Block`s. Create a class that derives from `Block`, then annotate some property names, and a datatype for each property.

In your TOML file, create some corresponding entries with the same names as your properties. When you load the TOML file to your `Block` class, BAF will automatically fill in all the properties with the data from the TOML file.

Notice we have one property, `name_length`, that isn't in the TOML. That's because we want to programmatically give this a value, rather than define it in the TOML. To do this, create a setter method called `set_name_length()`. If BAF finds a setter method called `set_<property_name>`, it will use that to fill in the data with whatever value you return.

Whatever data is given to the parent `Block` (in this case, the `dict` generated from our TOML file), that will also be passed to the setter method. So, if you need that data to determine your value, you can use it.

`example.py`:

```py
import baf
from baf.datatypes import *


class Level(Block):
    level_id: U8
    setting: U8
    name_length: U8
    name: Bytes

    def set_name_length(self, data):
        return self.name.size()


level = baf.build_toml('example.toml', Level)
level_bytes = level.to_bytes()
print(level_bytes.hex())
# Write file to disk
with open('out.bin', 'wb') as f:
    f.write(level_bytes)
```

`example.toml`:

```toml
level_id = 3
setting = 2
name = "Example Level"
```

Output:

```
$ python example.py
03020e4578616d706c65204c6576656c00
```

### Nested `Block`s

You can nest `Block`s to create more complex data structures.

In this example, `Level` has two properties, `header` and `data`, which are each a `Block` of their own. The TOML file reflects this.

Remember that we're passing `Level` to `baf.build_toml()`, which is how `Level` is specified as the top-level block.

```py
class LevelHeader(Block):
    level_id: U8
    setting: U8
    name_length: U8
    name: Bytes

    def set_name_length(self, data):
        return self.name.size()


class LevelData(Block):
    width: U16
    height: U16


class Level(Block):
    data_offset: U16
    header: LevelHeader
    data: LevelData

    def set_data_offset(self, data):
        return self.data.offset()
```

```toml
[header]
level_id = 3
setting = 2
name = "Example Level"

[data]
width = 640
height = 128
```

### `size()` and `offset()`

In the above example, you'll notice that `name_length` is set using `self.name.size()`, and `data_offset` is set using `self.data.offset()`. These two functions work on any datatype, and you can use them in your setter without worrying about the order in which data is built.

Behind the scenes, BAF uses some aggressive reflection to figure out which properties have dependencies on others. For example, to figure out `data_offset`, BAF needs to know the size of `header`, so it builds `header` first. If there is a circular dependency, you will get an error.

### `Array`

The `Array` datatype works seamlessly with TOML arrays and Python lists.

Below, we use `Array[U16]` for `checkpoints` and `Array[Enemy]` for `enemies`.

```py
class Enemy(Block):
    kind: U8
    spawn_x: U16
    spawn_y: U16


class LevelData(Block):
    width: U16
    height: U16
    checkpoints: Array[U16]
    enemies: Array[Enemy]
```

```toml
[data]
width = 640
height = 128
checkpoints = [60, 180, 320, 400]

[[data.enemies]]
kind = 1
spawn_x = 100
spawn_y = 32

[[data.enemies]]
kind = 1
spawn_x = 240
spawn_y = 32

[[data.enemies]]
kind = 2
spawn_x = 280
spawn_y = 56
```

### Visualizer

After getting our `Level` object with `baf.build_toml()`, we can use `baf.visualize()` to view a tree of our file format.

```py
level = baf.build_toml('visualizer_example.toml', Level)
tree = baf.visualize(level)
print(tree)
```

Output:
```
$ python visualizer_example.py
0x0 (0x0) data_offset: U16
0x2 (0x2) header: LevelHeader
    0x2 (0x0) level_id: U8
    0x3 (0x1) setting: U8
    0x4 (0x2) name_length: U8
    0x5 (0x3) name: Bytes
0x13 (0x13) data: LevelData
    0x13 (0x0) width: U16
    0x15 (0x2) height: U16
    0x17 (0x4) checkpoints: Array[U16] (4)
        0x17 ...
    0x1f (0xc) enemies: Array[Enemy] (4)
        0x1f (0x0) Enemy
            0x1f (0x0) kind: U8
            0x20 (0x1) spawn_x: U16
            0x22 (0x3) spawn_y: U16
        0x24 (0x5) Enemy
            0x24 (0x0) kind: U8
            0x25 (0x1) spawn_x: U16
            0x27 (0x3) spawn_y: U16
        0x29 (0xa) Enemy
            0x29 (0x0) kind: U8
            0x2a (0x1) spawn_x: U16
            0x2c (0x3) spawn_y: U16
```

### `File`

The `File` datatype extends `Bytes` to accept a file path that can be either absolute or relative to your TOML file. The file is read and inserted into your data structure as raw bytes.

```py
class LevelData(Block):
    width: U16
    height: U16
    checkpoints: Array[U16]
    enemies: Array[Enemy]
    splash_image: File
```

```toml
[data]
width = 640
height = 128
checkpoints = [60, 180, 320, 400]
splash_image = "level1/splash.raw"
```

### `Align`

The `Align` datatype can be used if you need to pad your data to a 16- or 32-bit boundary.

Below, `sprite_ids` is an array of 5 8-bit values, but we don't want the next data structure to begin on an odd byte. So, we use `Align[U16]` to pad the data to the nearest 16-bit boundary. If `sprite_ids` was already 4 bytes or 6 bytes, then `sprite_ids_align` would be zero bytes large. In this case, it's one byte large.

If using multiple `Align`s in one block, note that each property needs a unique name; Python annotations for member variables always need to be unique. A good convention is to name it the preceding property plus `_align`, as shown below.

```py
class AnimDef(Block):
    frame_count: U8
    loop_frame: U8
    sprite_ids: Array[U8]
    sprite_ids_align: Align[U16]
```

```toml
[[spritesheet.animations]]
frame_count = 5
loop_frame = 4
sprite_ids = [0, 1, 2, 3, 4]

```

### Integrating with external tools

Python makes it easy to run external processes and grab the output. You can do this in your setter—for example, to convert a source PNG image into a bitmap format specific to your platform's hardware.

```py
import subprocess


class LevelData(Block):
    width: U16
    height: U16
    background: Bytes

    def set_background(self, data):
        path = data['background_path']
        background = subprocess.check_output(['bin/some_tool', '--stdout', path])
        return background
```

```toml
[data]
width = 640
height = 128
background_path = "images/background.png"
```

### Custom datatypes

You can build on top of BAF with custom datatypes that suit your purposes.

For example, BAF doesn't have a built-in `Bool` datatype because `bool` can have different implementations depending on the platform. It's easy to define your own.

```py
class Bool(U8):
    def __init__(self, parent: Optional[Block], data: bool) -> None:
        super().__init__(parent, 0xff if data else 0x00)


class LevelData(Block):
    width: U16
    height: U16
    has_boss: Bool
```

```toml
[data]
width = 640
height = 128
has_boss = true
```

Below is an example of a custom `List` datatype which combines item count, item offsets, and item data.

BAF ignores the annotations in the base `List` class—it only cares about those in the derived `Rooms` and `Spritesheets` classes. Notice how `items` contains a different `Array` type in `Rooms` and `Spritesheets`.

```py
class List(Block):
    """Contains item count, item offsets, and an array of all the items."""
    count: U16
    offsets: Array[U32]
    items: Array

    def set_count(self, _):
        return len(self.items)

    def set_offsets(self, _):
        offsets = []
        current_offset = self.offsets.offset() + (4 * self.count)
        for item in self.items:
            offsets.append(current_offset)
            current_offset += item.size()
        return offsets

    def set_items(self, data):
        return data


class Rooms(List):
    count: U16
    offsets: Array[U32]
    items: Array[Room]


class Spritesheets(List):
    count: U16
    offsets: Array[U32]
    items: Array[Spritesheet]
```

### Overriding `__init__()`

You can override `__init__()` if you need to do something highly specific with your data that BAF can't handle automatically. Fill in whatever data you want manually, and then call `super().__init__(parent, data)` at the end (don't forget this step). BAF will kick in and build any remaining data based on your TOML.

Below, I have a list `Bobs`, but the data in the TOML needs to be processed into a more specific format before the list can be built.

```py
class Bob(Block):
    blit_size: U16
    blit_data: Bytes

    def set_blit_size(self, data: dict):
        return (data['height'] << 6) + data['width']


class Bobs(List):
    count: U16
    offsets: Array[U32]
    items: Array[Bob]

    def __init__(self, parent: Optional[Block], items: list) -> None:
        bob_list = []
        for item in items:
            width = item['width']
            data = image.get_bobs(item['image'])
            for height in item['heights']:
                bob_data = data[:width//8*height]
                bob = {'width': width, 'height': height, 'blit_data': bob_data}
                bob_list.append(bob)
                data = data[width//8*height:]
        super().__init__(parent, bob_list)
```

```toml
[[bobs]]
image = "bobs.png"
width = 16
heights = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
```

### Errors

If BAF catches an exception, it will add notes to the exception containing a traceback of your data structures, so you can pinpoint what data or setter caused the issue.

BAF doesn't discard or sanitize the full Python traceback, so it's ugly by default. If you want it to look nice, catch the exception yourself and print `__notes__`, as shown below. However, the default Python exception will also show the notes at the bottom, so this is optional.

```py
import sys
import baf
from baf.errors import BuildError


try:
    level = baf.build_toml('error_example.toml', Level)
except BuildError as e:
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
```
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
