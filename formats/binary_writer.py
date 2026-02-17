import struct
import array
from contextlib import contextmanager
from typing import Tuple


class BinaryWriter:
    """Struct-based binary writer for Urho3D formats."""

    def __init__(self):
        self._buffer = array.array('B')

    def write_ascii(self, s: str) -> None:
        self._buffer.extend(s.encode('ascii', errors='replace'))

    def write_cstring(self, s: str) -> None:
        """Write null-terminated ASCII string."""
        self.write_ascii(s)
        self.write_ubyte(0)

    def write_uint(self, v: int) -> None:
        self._buffer.extend(struct.pack('<I', v))

    def write_ushort(self, v: int) -> None:
        self._buffer.extend(struct.pack('<H', v))

    def write_ubyte(self, v: int) -> None:
        self._buffer.extend(struct.pack('<B', v))

    def write_float(self, v: float) -> None:
        self._buffer.extend(struct.pack('<f', v))

    def write_vector3(self, v: Tuple[float, float, float]) -> None:
        self._buffer.extend(struct.pack('<3f', v[0], v[1], v[2]))

    def write_vector2(self, v: Tuple[float, float]) -> None:
        self._buffer.extend(struct.pack('<2f', v[0], v[1]))

    def write_quaternion(self, w: float, x: float, y: float, z: float) -> None:
        """Write quaternion in Urho3D order: w, x, y, z."""
        self._buffer.extend(struct.pack('<4f', w, x, y, z))

    def write_color_ubyte4(self, r: int, g: int, b: int, a: int) -> None:
        self._buffer.extend(struct.pack('<4B', r, g, b, a))

    def write_matrix3x4(self, matrix_rows: list) -> None:
        """Write 3x4 matrix as 12 floats (3 rows of 4 columns), row-major."""
        for row in matrix_rows[:3]:
            for col in row[:4]:
                self.write_float(col)

    def save(self, filepath: str) -> None:
        with open(filepath, 'wb', buffering=1024 * 1024) as f:
            self._buffer.tofile(f)

    @property
    def size(self) -> int:
        return len(self._buffer)


@contextmanager
def binary_file(filepath: str):
    """Context manager that yields a BinaryWriter and saves on exit."""
    writer = BinaryWriter()
    yield writer
    writer.save(filepath)
