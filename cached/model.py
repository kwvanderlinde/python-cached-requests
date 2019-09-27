"""
Defines types to use in the caching interface.

These types are as simple as possible in order to most conveniently consume and
produce instances of them.
"""

from dataclasses import dataclass, field
from typing import Mapping, Optional, io


@dataclass
class Request:
    """
    Represents an arbitrary request, excluding parts not used for caching.

    The body and the HTTP version do not affect caching, and so we exclude
    them.
    """

    method: str
    """
    The HTTP method of the request. E.g., "GET".
    """

    uri: str
    """
    The id of the resource being requested.
    """

    headers: Mapping[str, str]
    """
    All the headers being sent with the request.
    """


@dataclass
class Response:
    """
    Represents an arbitrary response, without any bells and whistles.

    We deliberately do not use urllib3's `Response` we just want a type that
    does what we need, and nothing more. It is trivial to convert one of our
    `Response` instances to a urllib3 `Response`.
    """

    status: int
    """
    The status code of the response. E.g., 200 or 400.
    """

    reason: str
    """
    The reason string, which relates to the status code.
    """

    headers: Mapping[str, str]
    """
    All the headers sent with the response.
    """

    body: io.IO[bytes] = field(compare=False)
    """
    A file-like object containing the response payload.
    """


@dataclass
class CacheEntry:
    """
    A cache entry.

    A cache entry deliberately does not store a response body since those can
    be arbitrarily large, and therefore consume significant amounts of memory.
    To avoid that, we store a pointer to a file (i.e., a path) that contains
    the data of the response body. For robustness, if the path does not point
    to an existing file, it is considered a cache miss. Similarly, if the file
    is not the expected size, that is likely a fault of the implementation
    (unless a user has been tampering) and should be logged and treated as a
    cache miss.
    """
    request: Request
    response: Response
