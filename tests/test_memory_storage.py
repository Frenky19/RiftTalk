import os
import time

import pytest


def test_memory_storage_set_get_and_expire():
    os.environ.setdefault('REDIS_URL', 'memory://')
    from shared.database import MemoryStorage

    storage = MemoryStorage()

    assert storage.set('k1', 'v1') is True
    assert storage.get('k1') == 'v1'

    assert storage.set('k1', 'v2', nx=True) is False
    assert storage.get('k1') == 'v1'

    assert storage.set('k2', 'v2', ex=1) is True
    time.sleep(1.1)
    assert storage.get('k2') is None


def test_memory_storage_hset_hgetall():
    os.environ.setdefault('REDIS_URL', 'memory://')
    from shared.database import MemoryStorage

    storage = MemoryStorage()
    storage.hset('hash', mapping={'a': '1', 'b': '2'})
    assert storage.hget('hash', 'a') == '1'
    assert storage.hgetall('hash') == {'a': '1', 'b': '2'}


@pytest.mark.asyncio
async def test_async_wrapper_incr_and_scan():
    os.environ.setdefault('REDIS_URL', 'memory://')
    from shared.database import MemoryStorage, AsyncRedisWrapper

    storage = MemoryStorage()
    wrapper = AsyncRedisWrapper(storage, True)

    assert await wrapper.incr('counter') == 1
    assert await wrapper.incr('counter') == 2

    await wrapper.set('room:1', 'x')
    await wrapper.set('user:1', 'y')

    keys = await wrapper.scan_iter(match='room:*')
    assert 'room:1' in keys
    assert 'user:1' not in keys
