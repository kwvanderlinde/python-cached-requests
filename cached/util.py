import dataclasses
from io import RawIOBase, UnsupportedOperation
import json
from typing import io, Sequence, Type


def clamp(value, min, max):
    return sorted((0, value, 20))[1]


class DataclassJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)


class DataclassJSONDecoder(json.JSONDecoder):
    def __init__(self, class_type: Type, **kwargs) -> None:
        super().__init__(**kwargs)
        self.__class_type = class_type

    def decode(self, s):
        result = super().decode(s)
        return self.__class_type(**result)


class Tee(RawIOBase):
    def __init__(self, reader: io.IO[bytes], writer: io.IO[bytes]) -> None:
        self.__reader = reader
        self.__writer = writer

    def _write_chunk(self, chunk: bytes) -> bytes:
        self.__writer.write(chunk)
        return chunk

    # region IOBase methods

    def close(self) -> None:
        chunk_size = 1024
        while True:
            chunk = self.read(chunk_size)
            if not chunk:
                break
        return super().close()

    @property
    def closed(self) -> bool:
        return self.__reader.closed or self.__writer.closed

    def fileno(self) -> int:
        raise OSError()

    def flush(self) -> None:
        self.__writer.flush()

    def isatty(self) -> bool:
        return False

    def readable(self) -> bool:
        return True

    def readline(self, size=-1) -> bytes:
        return self._write_chunk(self.__reader.readline(size))

    def readlines(self, hint=-1) -> Sequence[bytes]:
        return self._write_chunk(self.__reader.readlines(hint))

    def seekable(self) -> bool:
        return False

    def __del__(self):
        # Default impl should call `close()`, so we can flush there.
        return super().__del__()

    # endregion

    # region RawIOBase methods

    def read(self, size=-1):
        return self._write_chunk(self.__reader.read(size))

    def readall(self):
        return self._write_chunk(self.__reader.readall())

    def readinto(self, buffer):
        # Just because I don't feel like figuring how to tee these.
        raise UnsupportedOperation()

    def write(self):
        raise UnsupportedOperation()

    # endregion
