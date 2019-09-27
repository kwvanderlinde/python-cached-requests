from ddt import ddt, data, unpack
from io import BytesIO
import json
from mockito import when, mock, unstub, verify
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional
from unittest import TestCase

from cached.cache import Cache, FileCache, HttpAwareCache
from cached.model import CacheEntry, Request, Response


# TODO Separate unit test for FileCache and HttpAwareCache. Move existing type of test to integration tests.


@ddt
class TestFileCache(TestCase):
    # TODO Cover the exceptional overwrite cases.

    @data(
        (
            # When the request is an exact match for a cache entry, return that cache entry.
            Request(
                method='GET',
                uri='http://google.ca',
                headers={
                    'Accept': 'application/pdf',
                }
            ),
            Path('9', '8', 'c', 'e', '0', 'b4f1e97102727131a3807371ff3494db4343c7ca41027ad7271a47af279'),
            json.dumps({
                'request': {
                    'method': 'GET',
                    'uri': 'http://google.ca',
                    'headers': {
                        'Accept': 'application/pdf',
                    },
                },
                'response': {
                    'status': 200,
                    'reason': 'OK',
                    'headers': {
                        'Vary': 'Accept',
                        'ETag': 'gibberish',
                    },
                    'body': str(Path('path', 'to', 'body'))
                }
            }),
            CacheEntry(
                Request(
                    method='GET',
                    uri='http://google.ca',
                    headers={
                        'Accept': 'application/pdf',
                    }
                ),
                Response(
                    status=200,
                    reason='OK',
                    headers={
                        'Vary': 'Accept',
                        'ETag': 'gibberish',
                    },
                    body=Path('path', 'to', 'body')
                ),
            ),
        ),

        (
            # When no entry file exists for the request consider it a cache miss.
            Request(
                method='GET',
                uri='http://google.ca',
                headers={
                    'Accept': 'application/pdf',
                }
            ),
            None,
            None,
            None,
        ),
    )
    @unpack
    def test_get(self, request: Request, expected_path: Optional[Path], entry_contents: Optional[str],
                 expected_entry: Optional[CacheEntry]):
        expected_body_path = Path('path', 'to', 'body')
        expected_body_contents = b'some contents';

        with TemporaryDirectory() as directory:
            directory = Path(directory)

            expected_body_path = directory / 'bodies' / expected_body_path
            expected_body_path.parent.mkdir(parents=True, exist_ok=True)
            with open(expected_body_path, 'wb') as f:
                f.write(expected_body_contents)

            if expected_path is not None:
                expected_path = directory / 'entries' / expected_path
                expected_path.parent.mkdir(parents=True, exist_ok=True)
                with open(expected_path, 'w') as f:
                    f.write(entry_contents)

            cache = FileCache(directory, 5)
            entry = cache.get(request)

            if expected_entry is None:
                self.assertIs(None, entry)
            else:
                self.assertEqual(expected_entry.request, entry.request)
                self.assertEqual(expected_entry.response.status, entry.response.status)
                self.assertEqual(expected_entry.response.reason, entry.response.reason)
                self.assertEqual(expected_entry.response.headers, entry.response.headers)
                # Need to check file contents, not file descriptors.
                body_contents = entry.response.body.read()
                self.assertEqual(expected_body_contents, body_contents)

    @data(
        (
            Request(
                method='GET',
                uri='http://google.ca',
                headers={
                    'Accept': 'application/pdf',
                    'X-something-else': 'some value',
                }
            ),
            Response(
                status=200,
                reason='OK',
                headers={
                    'Vary': 'Accept',
                    'ETag': 'gibberish',
                },
                body=BytesIO(b'some contents')
            ),
            b'some contents',
            Path('9', '8', 'c', 'e', '0', 'b4f1e97102727131a3807371ff3494db4343c7ca41027ad7271a47af279'),
            {
                'request': {
                    'method': 'GET',
                    'uri': 'http://google.ca',
                    'headers': {
                        'Accept': 'application/pdf',
                        'X-something-else': 'some value',
                    },
                },
                'response': {
                    'status': 200,
                    'reason': 'OK',
                    'headers': {
                        'Vary': 'Accept',
                        'ETag': 'gibberish',
                    },
                    'body': Path('bodies', '9', '8', 'c', 'e', '0', 'b4f1e97102727131a3807371ff3494db4343c7ca41027ad7271a47af279')
                }
            }
        )
    )
    @unpack
    def test_add(self, request: Request, response: Response, expected_body_contents: bytes, expected_path, expected_contents: dict):
        with TemporaryDirectory() as directory:
            directory = Path(directory)

            expected_contents['response']['body'] = str(directory / expected_contents['response']['body'])
            expected_path = directory / 'entries' / expected_path

            cache = FileCache(directory, 5)
            cache_entry = cache.add(request, response)
            # Read the entire body to ensure all tee-ing is done.
            body_contents = cache_entry.response.body.readall()

            self.assertTrue(expected_path.exists(), 'The cache should create the file for the cache entry')
            with open(expected_path, 'r') as f:
                entry_contents = json.load(f)

            # The body path is deliberately not predictable.
            del expected_contents['response']['body']
            del entry_contents['response']['body']
            self.assertEqual(expected_contents, entry_contents)

            self.assertEqual(expected_body_contents, body_contents)

    # TODO Test that a `add()` can be followed by a `get()`.


    def test_delete(self):
        request = Request(
            method='GET',
            uri='http://google.ca',
            headers={
                'Accept': 'application/pdf',
                'X-something-else': 'some value',
            }
        )
        expected_path = Path('9', '8', 'c', 'e', '0', 'b4f1e97102727131a3807371ff3494db4343c7ca41027ad7271a47af279')

        with TemporaryDirectory() as directory:
            directory = Path(directory)
            expected_path = directory / expected_path

            cache = FileCache(directory, 5)
            cache.delete(request)


@ddt
class TestHttpAwareCache(TestCase):
    def setUp(self):
        self.__wrapped = mock(Cache)
        self.__sut = HttpAwareCache(self.__wrapped)

    def tearDown(self):
        unstub()

    # TODO Invalid cache entries should be deleted.

    @data(
        (
            # When the decorated cache does not have an element, neither does the HTTP-aware cache.
            Request(
                method='GET',
                uri='http://google.ca',
                headers={
                    'Accept': 'application/pdf',
                }
            ),
            None,
            None,
        ),
        (
            # When the cached entry is a 5xx error, it does not qualify for caching by HTTP rules.
            Request(
                method='GET',
                uri='http://google.ca',
                headers={
                    'Accept': 'application/pdf',
                }
            ),
            CacheEntry(
                Request(
                    method='GET',
                    uri='http://google.ca',
                    headers={
                        'Accept': 'application/pdf',
                    }
                ),
                Response(
                    status=500,
                    reason='Internal Server Error',
                    headers={},
                    body = BytesIO(b'')
                )
            ),
            None,
        ),

        (
            # When the cached request is missing a Vary header specified in the cached response, the cache entry is invalid
            Request(
                method='GET',
                uri='http://google.ca',
                headers={
                    'Accept': 'application/pdf',
                }
            ),
            CacheEntry(
                Request(
                    method='GET',
                    uri='http://google.ca',
                    headers={
                        'Accept': 'application/pdf',
                    }
                ),
                Response(
                    status=200,
                    reason='OK',
                    headers={
                        'Vary': 'X-MY-COOL-HEADER'
                    },
                    body = BytesIO(b'')
                )
            ),
            None,
        ),

        (
            # When the new request is missing a Vary header specified in the cached response, the cache entry is not matched
            Request(
                method='GET',
                uri='http://google.ca',
                headers={
                    'Accept': 'application/pdf',
                }
            ),
            CacheEntry(
                Request(
                    method='GET',
                    uri='http://google.ca',
                    headers={
                        'Accept': 'application/pdf',
                        'X-MY-COOL-HEADER': 52,
                    }
                ),
                Response(
                    status=200,
                    reason='OK',
                    headers={
                        'Vary': 'X-MY-COOL-HEADER'
                    },
                    body = BytesIO(b'')
                )
            ),
            None,
        ),

        (
            # When the new request has a different value than the cached request for a Vary header, the cache entry is not matched
            Request(
                method='GET',
                uri='http://google.ca',
                headers={
                    'Accept': 'application/pdf',
                    'X-MY-COOL-HEADER': 53,
                }
            ),
            CacheEntry(
                Request(
                    method='GET',
                    uri='http://google.ca',
                    headers={
                        'Accept': 'application/pdf',
                        'X-MY-COOL-HEADER': 52,
                    }
                ),
                Response(
                    status=200,
                    reason='OK',
                    headers={
                        'Vary': 'X-MY-COOL-HEADER'
                    },
                    body = BytesIO(b'')
                )
            ),
            None,
        ),

        (
            # When the new request has matches the Vary headers of the cached request, and the status code is 200, then the cached entry is returned.
            Request(
                method='GET',
                uri='http://google.ca',
                headers={
                    'Accept': 'application/pdf',
                    'X-MY-COOL-HEADER': 52,
                }
            ),
            CacheEntry(
                Request(
                    method='GET',
                    uri='http://google.ca',
                    headers={
                        'Accept': 'application/pdf',
                        'X-MY-COOL-HEADER': 52,
                    }
                ),
                Response(
                    status=200,
                    reason='OK',
                    headers={
                        'Vary': 'X-MY-COOL-HEADER'
                    },
                    body = BytesIO(b'')
                )
            ),
            CacheEntry(
                Request(
                    method='GET',
                    uri='http://google.ca',
                    headers={
                        'Accept': 'application/pdf',
                        'X-MY-COOL-HEADER': 52,
                    }
                ),
                Response(
                    status=200,
                    reason='OK',
                    headers={
                        'Vary': 'X-MY-COOL-HEADER'
                    },
                    body = BytesIO(b'')
                )
            ),
        ),

        (
            # When the new request has matches the Vary headers of the cached request, and the status code is 203, then the cached entry is returned.
            Request(
                method='GET',
                uri='http://google.ca',
                headers={
                    'Accept': 'application/pdf',
                    'X-MY-COOL-HEADER': 52,
                }
            ),
            CacheEntry(
                Request(
                    method='GET',
                    uri='http://google.ca',
                    headers={
                        'Accept': 'application/pdf',
                        'X-MY-COOL-HEADER': 52,
                    }
                ),
                Response(
                    status=203,
                    reason='OK',
                    headers={
                        'Vary': 'X-MY-COOL-HEADER'
                    },
                    body = BytesIO(b'')
                )
            ),
            CacheEntry(
                Request(
                    method='GET',
                    uri='http://google.ca',
                    headers={
                        'Accept': 'application/pdf',
                        'X-MY-COOL-HEADER': 52,
                    }
                ),
                Response(
                    status=203,
                    reason='OK',
                    headers={
                        'Vary': 'X-MY-COOL-HEADER'
                    },
                    body = BytesIO(b'')
                )
            ),
        ),

        (
            # When the new request has matches the Vary headers of the cached request, and the status code is 300, then the cached entry is returned.
            Request(
                method='GET',
                uri='http://google.ca',
                headers={
                    'Accept': 'application/pdf',
                    'X-MY-COOL-HEADER': 52,
                }
            ),
            CacheEntry(
                Request(
                    method='GET',
                    uri='http://google.ca',
                    headers={
                        'Accept': 'application/pdf',
                        'X-MY-COOL-HEADER': 52,
                    }
                ),
                Response(
                    status=300,
                    reason='OK',
                    headers={
                        'Vary': 'X-MY-COOL-HEADER'
                    },
                    body = BytesIO(b'')
                )
            ),
            CacheEntry(
                Request(
                    method='GET',
                    uri='http://google.ca',
                    headers={
                        'Accept': 'application/pdf',
                        'X-MY-COOL-HEADER': 52,
                    }
                ),
                Response(
                    status=300,
                    reason='OK',
                    headers={
                        'Vary': 'X-MY-COOL-HEADER'
                    },
                    body = BytesIO(b'')
                )
            ),
        ),

        (
            # When the new request has matches the Vary headers of the cached request, and the status code is 301, then the cached entry is returned.
            Request(
                method='GET',
                uri='http://google.ca',
                headers={
                    'Accept': 'application/pdf',
                    'X-MY-COOL-HEADER': 52,
                }
            ),
            CacheEntry(
                Request(
                    method='GET',
                    uri='http://google.ca',
                    headers={
                        'Accept': 'application/pdf',
                        'X-MY-COOL-HEADER': 52,
                    }
                ),
                Response(
                    status=301,
                    reason='OK',
                    headers={
                        'Vary': 'X-MY-COOL-HEADER'
                    },
                    body = BytesIO(b'')
                )
            ),
            CacheEntry(
                Request(
                    method='GET',
                    uri='http://google.ca',
                    headers={
                        'Accept': 'application/pdf',
                        'X-MY-COOL-HEADER': 52,
                    }
                ),
                Response(
                    status=301,
                    reason='OK',
                    headers={
                        'Vary': 'X-MY-COOL-HEADER'
                    },
                    body = BytesIO(b'')
                )
            ),
        ),

        # TODO Test Cache-Control.
    )
    @unpack
    def test_get(self,
                 request: Request,
                 # expected_path: Optional[Path],
                 # entry_contents: Optional[str],
                 decorated_result: Optional[CacheEntry],
                 expected_entry: Optional[CacheEntry]):
        # region Set up
        when(self.__wrapped).get(request).thenReturn(decorated_result)
        # endregion

        # region Exercise
        entry = self.__sut.get(request)
        # endregion

        # region Verify
        self.assertEqual(expected_entry, entry)

        if expected_entry is not None:
            # Need to check file contents, not file descriptors.
            expected_body_contents = expected_entry.response.body.read()
            body_contents = entry.response.body.read()
            self.assertEqual(expected_body_contents, body_contents)
        # endregion

    @data(
        (
            # When the status code is 200, the response can be cached.
            Request(
                method='GET',
                uri='http://google.ca',
                headers={
                    'Accept': 'application/pdf',
                    'X-something-else': 'some value',
                }
            ),
            Response(
                status=200,
                reason='OK',
                headers={
                    'Vary': 'Accept',
                    'ETag': 'gibberish',
                },
                body=BytesIO(b'some contents')
            ),
            CacheEntry(
                Request(
                    method='GET',
                    uri='http://google.ca',
                    headers={
                        'Accept': 'application/pdf',
                        'X-something-else': 'some value',
                    }
                ),
                Response(
                    status=200,
                    reason='OK',
                    headers={
                        'Vary': 'Accept',
                        'ETag': 'gibberish',
                    },
                    body=BytesIO(b'some contents')
                )
            ),
            True,
        ),

        (
            # When the status code is 500, the response is not cached.
            Request(
                method='GET',
                uri='http://google.ca',
                headers={
                    'Accept': 'application/pdf',
                    'X-something-else': 'some value',
                }
            ),
            Response(
                status=500,
                reason='OK',
                headers={
                    'Vary': 'Accept',
                    'ETag': 'gibberish',
                },
                body=BytesIO(b'some contents')
            ),
            None,
            False,
        ),
    )
    @unpack
    def test_add(self, request: Request, response: Response, expected_entry: Optional[CacheEntry], expected_to_be_cached: bool):
        # region set up
        when(self.__wrapped).add(request, response).thenReturn(CacheEntry(request, response))
        # endregion

        result = self.__sut.add(request, response)

        self.assertEqual(expected_entry, result)
        verify(self.__wrapped, 1 if expected_to_be_cached else 0).add(request, response)

    def test_delete(self):
        # region set up
        request = Request(
            method='GET',
            uri='http://google.ca',
            headers={
                'Accept': 'application/pdf',
                'X-something-else': 'some value',
            }
        )
        when(self.__wrapped).delete(request).thenReturn(None)
        # endregion

        self.__sut.delete(request)

        verify(self.__wrapped).delete(request)
