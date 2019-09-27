from pathlib import Path

import requests
from requests.structures import CaseInsensitiveDict
from requests.adapters import HTTPAdapter

from .cache import Cache, HttpAwareCache, FileCache
from .model import Request, Response


class CachedHTTPAdapter(HTTPAdapter):
    invalidating_methods = {"PUT", "DELETE"}

    def __init__(self, cache: Cache, *args, **kw) -> None:
        super().__init__(*args, **kw)
        self.cache = cache

    # TODO Specify a type for `requests_request` and the return type..
    def send(self, requests_request: requests.PreparedRequest, **kw) -> requests.Response:
        """
        Send a request. Use the request information to see if it
        exists in the cache and cache the response if we need to and can.
        """
        # TODO Change implementation to match my steps.
        # Steps:
        # 1. Check the cache for a response matching the request.
        # 2. If a cache hit:
        #   a. Deserialize the cache entry
        #   b. If the cache entry is valid:
        #     i. If the cache entry is not stale, return a `Response` with the
        #        status and headers from the entry, and its `raw` field set to
        #        a file pointer to the response body.
        #     ii. If the cache entry is stale, send the request but with an
        #        "If-None-Match" header. If the response is "304 Not Modified",
        #        revalidate the cache entry and proceed as in case (2.b.i).
        #        Otherwise, overwrite the entry with the new response.
        #   c. If the cache entry is not valid:
        #     i. Eject the entry from the cache, and treat as in case (3).
        # 3. If a cache miss:
        #   a. Run the super's `send()`
        #   b. Pipe response body to a file as it is read. Must be sure it is
        #      all consumed, otherwise the cache entry will be invalid.

        request = Request(method=requests_request.method,
                          uri=requests_request.url,
                          headers=dict(requests_request.headers))

        entry = self.cache.get(request)
        if entry is None:
            # No valid cached entry. Need to make the request.
            requests_response = super().send(requests_request, **kw)
            response = Response(status=requests_response.status_code,
                                reason=requests_response.reason,
                                headers=dict(requests_response.headers),
                                body=requests_response.raw)
            entry = self.cache.add(request, response)
            response = entry.response
        else:
            # TODO Check if stale. If so, need to make the request with `If-None-Match: response.headers['etag']`,
            # checking for `HTTP 304 Not Modified`.
            # Staleness should be checked against either the time of response or request. Not sure.
            response = entry.response


        # TODO Is this conversion complete?
        result = requests.Response()
        result.status_code = response.status
        result.reason = response.reason
        result.headers = CaseInsensitiveDict(response.headers)
        # TODO I think if stream=True is provided, we set raw. Otherwise, we should read body and set content?
        result.raw = response.body
        result.url = request.uri
        result.request = request
        return result

    def close(self):
        self.cache.close()
        super().close()


def create(directory: Path) -> CachedHTTPAdapter:
    return CachedHTTPAdapter(HttpAwareCache(FileCache(directory, 5)))
