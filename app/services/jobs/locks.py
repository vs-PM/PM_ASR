import asyncio
from typing import Dict

_LOCKS: Dict[int, asyncio.Lock] = {}

def get_lock(tid: int) -> asyncio.Lock:
    if tid not in _LOCKS:
        _LOCKS[tid] = asyncio.Lock()
    return _LOCKS[tid]
