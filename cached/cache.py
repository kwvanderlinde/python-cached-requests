from abc import ABC, abstractmethod
from copy import copy
from dataclasses import dataclass
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import tempfile
from typing import Mapping, Optional
from .util import clamp, Tee
from .model import CacheEntry, Request, Response


logger = logging.getLogger(__name__)


class Cache(ABC):
    """
    An abstraction of a response cache.

    A response cache has a relatively narrow scope: to remember a response such that it can be recalled later for a
    matching request. Note that this deliberately precludes certain responsibilities such as automatic cache
    invalidation. We rely on the users to determine when a cache entry is stale, and also how to replace it.
    """

    @abstractmethod
    def get(self, request: Request) -> Optional[CacheEntry]:
        """
        Retrieve a cached response matching `request`.

        TODO Support fallback behaviour for a stale, yet potentially valid cache entry (i.e., ETag).

        @param request
          The request to look up in the cache.
        @return
          A cached response for `request`, or `None` if there is no valid one.
        """

    @abstractmethod
    def add(self, request: Request, response: Response) -> Optional[CacheEntry]:
        """
        Add a response to the cache.

        This should only be called if there is not already a cached response for `request`. Any prior items should first
        be `delete()`d.

        Note that the body stream from `response` may be consumed as part of caching. The component using the cache
        should be sure to read from the returned entry's response body instead.

        @param request
          The request for which a response should be cached.
        @param response
          The response to cache.
        @return
          A cached entry, or `None` if the cache could not cache the response.
        """

    @abstractmethod
    def delete(self, request: Request) -> None:
        """
        Delete a response from the cache.

        @param request
            A request to find in the cache. The corresponding response will be deleted.

        @todo I may be that we really should delete based on URI or something like that.
        """

    def close(self):
        """
        Close any resources associated with the cache.
        """


class HttpAwareCache(Cache):
    """
    Augments a cache with HTTP-specific knowledge.

    Some examples are:
    - Checking Vary headers.
    - Only cache sensible responses (e.g., 200, 203, 300, 301 are used in cachecontrol).
    - Respecting the Cache-Control header such as no-cache, max-age, etc. (Will require expanding the entry structure).
    """

    def __init__(self, implementation: Cache) -> None:
        self.__impl = implementation

    def get(self, request: Request) -> Optional[CacheEntry]:
        logger.info('Delegating cache lookup to decorated cache.')
        entry = self.__impl.get(request)
        if entry is None:
            logger.info('Decorated cache did not find a matching cache entry.')
            return None

        # region Only cache for response statuses that make sense to cache.
        if not self._is_cachable_status_code(entry.response.status):
            logger.info('Status code {} is not cachable'.format(entry.response.status))
            return None
        if not self._is_cachable_method(entry.request.method):
            logger.info('Method {} is not cachable'.format(entry.request.method))
            return None
        # endregion

        # region Only cache if all specific Vary headers match.
        vary_header_keys = entry.response.headers.get('Vary', []).split(',')
        for key in vary_header_keys:
            if key not in entry.request.headers:
                logger.warning('The cache entry does not have all of its own Vary headers. Missing header: {}'.format(key))
                return None
            expected_value = entry.request.headers[key]

            if key not in request.headers:
                logger.info('Cache entry is rejected because the incoming request is missing a Vary header: {}'.format(key))
                return None
            value = request.headers[key]

            if expected_value != value:
                # Doesn't match as the vary header doesn't have the same value.
                logger.info('Cache entry is rejected because the value for a Vary header is not equal to the value in the original request. Header: {}. Expected value: {}. Actual value: {}'.format(key, expected_value, value))
                return None
        # endregion

        # region Only cache if the Cache-Control predicate is satisfied.
        # TODO
        # endregion

        logger.info('Cache entry passed all HTTP checks. Returning entry from cache.')

        return entry

    def add(self, request: Request, response: Response) -> Optional[CacheEntry]:
        if not self._is_cachable_status_code(response.status):
            logger.info('Refusing to create cache entry. Status code {} is not cachable.'.format(response.status))
            return None
        if not self._is_cachable_method(request.method):
            logger.info('Refusing to create cache entry. Method {} is not cachable.'.format(request.method))
            return None

        logger.info('Delegating cache entry creation to decorated cache.')
        return self.__impl.add(request, response)

    def delete(self, request: Request) -> None:
        logger.info('Delegating cache entry deletion to decorated cache.')
        self.__impl.delete(request)

    def _is_cachable_status_code(self, status: int) -> bool:
        return status in (200, 203, 300, 301,)

    def _is_cachable_method(self, method: str) -> bool:
        # TODO We could cache HEAD as well, even return a HEAD based on a GET.
        return method in {'GET'}


@dataclass
class FileCacheResponseModel:
    status: int
    reason: str
    headers: Mapping[str, str]
    body_path: Path


@dataclass
class FileCacheEntryModel:
    entry_path: Path
    request: Request
    response: FileCacheResponseModel


class CorruptEntry(Exception):
    def __init__(self, entry_path: Path):
        super().__init__()
        self.__entry_path = entry_path

    @property
    def entry_path(self) -> Path:
        return self.__entry_path


class FileCache(Cache):
    # TODO Implement proper file locking, etc.

    def __init__(self, directory: Path, cache_directory_levels: int) -> None:
        """
        Initialize the file cache.

        @param directory
          The path to the root directory of the cache.
        @param cache_directory_levels
          The number of subdirectory levels to use in the cache directory. This
          will be clamped to be between 0 and 20, respectively.
        """
        self.__directory = directory
        self.__entry_directory = directory / 'entries'
        self.__body_directory = directory / 'bodies'
        self.__cache_directory_levels = clamp(cache_directory_levels, 0, 20)

    # TODO Factor out pathing into an injectable strategy that can be
    # separately tested
    def _get_path(self, uri: str) -> Path:
        hashed = hashlib.sha256(uri.encode('utf-8')).hexdigest()
        return self._split_path(hashed)

    def _split_path(self, path: str) -> Path:
        # TODO Ensure that `path` is at least `self.__cache_directory_levels` long.
        subdirectories = (list(path[:self.__cache_directory_levels])
                          + [path[self.__cache_directory_levels:]])
        subdirectory = Path(*subdirectories)
        return subdirectory

    # Paths to cache items are represented by a hash of the URL. Each cache
    # item file should be able to store several cache items. I think the list
    # of cache entries should be keyed by a SHA hash of a sorted JSON object of
    # the Vary headers, and the values should be the expanded form. The simpler
    # option, however, is simply to have the file be a list of entries, as
    # JSON, wtih the headers as literal objects, which can be compared for
    # equality with the current set of headers.

    def _load_entry(self, request: Request) -> FileCacheEntryModel:
        """
        Read a cache entry from a file.

        @param request
            The request for which a matching cache entry is desired. The path to the cache entry will be deduced from
            `request`.
        @return
            A tuple containing:
            1. The path to the entry file.
            2. The decoded contents of the file. If the file is corrupt in any way, this will be `None`.
        @throws CorruptEntry
            If the entry file could not be parsed.
        """
        entry_path = self.__entry_directory / self._get_path(request.uri)
        try:
            with open(entry_path, 'r') as f:
                entry = json.load(f)
            return FileCacheEntryModel(entry_path=entry_path,
                                       request=Request(
                                           method=entry['request']['method'],
                                           uri=entry['request']['uri'],
                                           headers=entry['request']['headers']
                                       ),
                                       response=FileCacheResponseModel(
                                           status=entry['response']['status'],
                                           reason=entry['response']['reason'],
                                           headers=entry['response']['headers'],
                                           body_path=self.__body_directory / Path(entry['response']['body'])))
        except FileNotFoundError as e:
            raise e
        except (KeyError, json.JSONDecodeError) as e:
            raise CorruptEntry(entry_path)

    def get(self, request: Request) -> Optional[CacheEntry]:
        try:
            logger.info('Looking at the file system for a cache entry matching the request.')
            entry_model = self._load_entry(request)
            logger.info('Loaded entry file. Returning the cache entry')
            return CacheEntry(
                request=entry_model.request,
                response=Response(
                    status=entry_model.response.status,
                    reason=entry_model.response.reason,
                    headers=entry_model.response.headers,
                    body=open(entry_model.response.body_path, 'rb')
                )
            )
        # TODO When if entry_model.response.body_path does not exist? We *must* distinguish that from the
        # FileNotFuondError thrown for a missing entry. If the body does not exist, that should be treated the same as a
        # CorruptEntry.
        except CorruptEntry as e:
            logger.warning('Found a corrupt cache entry. Deleting the entry file.')
            e.entry_path.unlink()
            return None
        except FileNotFoundError as e:
            logger.info('No matching cache entry found.')
            return None

    def add(self, request: Request, response: Response) -> CacheEntry:
        logger.info('Building path to the entry file.')
        entry_path = self.__entry_directory / self._get_path(request.uri)
        if entry_path.exists():
            logger.warning('Aborting. The entry file already exists: {}'.format(entry_path))
            raise Exception('I refuse to overwrite a cache entry')

        logger.info('Building randomized path to the body file.')
        # We use a randomized body path as the entry can point to it anyways.
        body_path = self.__body_directory / self._split_path(os.urandom(32).hex())
        if body_path.exists():
            logger.warning('Aborting. The body file already exists: {}'.format(entry_path))
            raise Exception('I refuse to overwrite an existing response body')

        serialized = {
            'request': {
                'method': request.method,
                'uri': request.uri,
                'headers': request.headers,
            },
            'response': {
                'status': response.status,
                'reason': response.reason,
                'headers': response.headers,
                'body': str(body_path.relative_to(self.__body_directory))
            }
        }

        logger.info('Tee the response body so we can write to the cache as it is read.')
        # The way we are using `Tee` here means that we will only cache a body that is fully read. This avoids waiting
        # on the full download - say, if the user wants to interrupt the download - while also ensuring we don't write
        # partial state to the cache.
        temp_body_file = tempfile.NamedTemporaryFile(mode='wb', delete=False)
        def on_complete():
            logger.info('Download complete.')

            logger.info('Moving temporary body file into permanent location')
            body_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(Path(temp_body_file.name), body_path)

            logger.info('Creating entry file that points to the permanent body file')
            entry_path.parent.mkdir(parents=True, exist_ok=True)
            with open(entry_path, 'w') as f:
                json.dump(serialized, f)
        tee = Tee(
            response.body,
            temp_body_file,
            on_complete
        )

        logger.info('Build a new cache entry using the tee\'d response body')
        response = copy(response)
        response.body = tee
        result = CacheEntry(
            request,
            response
        )
        return result

    def delete(self, request: Request) -> None:
        try:
            logger.info('Looking at the file system for a cache entry matching the request so that we can delete both the entry and the associated body.')
            entry_model = self._load_entry(request)
            logger.info('Found a matching cache entry. Marking both the entry file and the body file for deletion.')
            paths_to_delete = [entry_model.entry_path, entry_model.response.body_path]
        except CorruptEntry as e:
            logger.warning('Found a corrupt cache entry. Marking only the entry file for deletion.')
            paths_to_delete = [e.entry_path]
        except FileNotFoundError as e:
            # TODO Log this.
            logger.info('No matching cache entry found. Nothing to delete.')
            return

        for path in paths_to_delete:
            try:
                logger.info('Deleting {}'.format(path))
                path.unlink()
            except Exception:
                logger.exception('Unexpected error occurred while deleting {}'.format(path))
