import dataclasses
from io import RawIOBase, UnsupportedOperation
import json
from typing import Callable, io, Sequence, Type


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
    def __init__(self, reader: io.IO[bytes], writer: io.IO[bytes], on_complete: Callable[[], None]) -> None:
        self.__reader = reader
        self.__writer = writer
        self.__on_complete = on_complete

    def _write_chunk(self, chunk: bytes) -> bytes:
        self.__writer.write(chunk)
        if not chunk:
            # Indicates EOF was reached in the reader.
            self.__on_complete()
        return chunk

    # region IOBase methods

    def close(self) -> None:
        self.__reader.close()
        self.__writer.close()

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
