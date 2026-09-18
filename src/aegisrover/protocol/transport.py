"""Wire transport: versioned frames, serial sequence numbers, reassembly and auth.

The frame checksum covers header *and* body: a frame whose type byte was flipped in
flight must be rejected, because the same body interpreted as another message type
is a different command. Sequence numbers are compared with serial-number arithmetic
so a 16-bit counter that wrapped from 65535 to 0 keeps working. Fragments are
reassembled with an explicit conflict rule: re-sending the same fragment with the
same bytes is idempotent, re-sending it with different bytes is an error.
"""
from __future__ import annotations

import hashlib
import hmac
import struct
import zlib
from dataclasses import dataclass, field
from typing import Iterable

from . import sequence as serial

__all__ = (
    'MAGIC', 'MAX_FRAME', 'FrameError', 'Frame', 'encode_frame', 'decode_frame',
    'SequenceTracker', 'FragmentConflict', 'Reassembler', 'authenticate', 'verify_frame',
)

MAGIC = b'AR'
VERSION = 1
HEADER = struct.Struct('>2sBBBH')
MAX_FRAME = 4096


class FrameError(ValueError):
    def __init__(self, reason: str, detail: str = ''):
        super().__init__(f'{reason}: {detail}' if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class Frame:
    version: int
    kind: int
    flags: int
    body: bytes

    @property
    def header(self) -> bytes:
        return HEADER.pack(MAGIC, self.version, self.kind, self.flags, len(self.body))


def encode_frame(kind: int, body: bytes, *, version: int = VERSION, flags: int = 0) -> bytes:
    if not 0 <= kind <= 255:
        raise FrameError('kind', 'out of range')
    if not 0 <= flags <= 255:
        raise FrameError('flags', 'out of range')
    if len(body) > MAX_FRAME:
        raise FrameError('too_large', f'{len(body)} > {MAX_FRAME}')
    frame = Frame(version, kind, flags, bytes(body))
    header = frame.header
    crc = zlib.crc32(header + body) & 0xFFFFFFFF
    return header + body + struct.pack('>I', crc)


def decode_frame(data: bytes) -> Frame:
    if len(data) < HEADER.size + 4:
        raise FrameError('short', f'need {HEADER.size + 4} bytes')
    magic, version, kind, flags, length = HEADER.unpack(data[:HEADER.size])
    if magic != MAGIC:
        raise FrameError('magic', magic.hex())
    if version != VERSION:
        raise FrameError('version', str(version))
    if length > MAX_FRAME:
        raise FrameError('too_large', str(length))
    if len(data) != HEADER.size + length + 4:
        raise FrameError('length', f'declared {length}, got {len(data) - HEADER.size - 4}')
    body = data[HEADER.size:HEADER.size + length]
    stored = struct.unpack('>I', data[-4:])[0]
    if zlib.crc32(data[:-4]) & 0xFFFFFFFF != stored:
        raise FrameError('crc', 'checksum mismatch')
    return Frame(version, kind, flags, body)


class SequenceTracker:
    """Serial-number aware duplicate / gap detection."""

    def __init__(self, bits: int = 16, window: int = 64):
        self.bits = bits
        self.window = window
        self._last: int | None = None
        self._seen: set[int] = set()
        self.gaps: list[tuple[int, int]] = []

    def observe(self, seq: int) -> str:
        if self._last is None:
            self._last = seq
            self._seen.add(seq)
            return 'new'
        if seq == self._last:
            return 'duplicate'
        if serial.newer(seq, self._last, self.bits):
            missing = []
            cursor = (self._last + 1) % (1 << self.bits)
            while cursor != seq:
                if cursor not in self._seen:
                    missing.append(cursor)
                cursor = (cursor + 1) % (1 << self.bits)
                if len(missing) > 1024:
                    break
            if missing:
                self.gaps.append((self._last, seq))
            self._seen.add(seq)
            self._last = seq
            return 'gap' if missing else 'new'
        return 'stale'

    def missing(self) -> tuple[int, ...]:
        return tuple(m for _, _ in self.gaps)

    def stats(self) -> dict:
        return {'last': self._last, 'gaps': len(self.gaps)}


class FragmentConflict(RuntimeError):
    def __init__(self, message_id: str, index: int):
        super().__init__(f'{message_id}: fragment {index} resent with different bytes')
        self.message_id = message_id
        self.index = index


@dataclass
class _Assembly:
    total: int
    parts: dict[int, bytes] = field(default_factory=dict)
    updated_at: float = 0.0

    def complete(self) -> bool:
        return len(self.parts) == self.total

    def payload(self) -> bytes:
        return b''.join(self.parts[i] for i in range(self.total))


class Reassembler:
    def __init__(self, *, ttl: float = 30.0, max_messages: int = 64):
        self.ttl = ttl
        self.max_messages = max_messages
        self._pending: dict[str, _Assembly] = {}
        self.completed = 0
        self.dropped = 0
        self.duplicate_fragments = 0

    def add(self, message_id: str, index: int, total: int, data: bytes, *, now: float) -> bytes | None:
        if total <= 0 or not 0 <= index < total:
            raise ValueError('bad fragment index')
        self.evict(now)
        if message_id not in self._pending:
            if len(self._pending) >= self.max_messages:
                oldest = min(self._pending, key=lambda k: self._pending[k].updated_at)
                del self._pending[oldest]
                self.dropped += 1
            self._pending[message_id] = _Assembly(total, {}, now)
        assembly = self._pending[message_id]
        if assembly.total != total:
            raise ValueError('total changed mid-message')
        previous = assembly.parts.get(index)
        if previous is not None:
            if previous != data:
                raise FragmentConflict(message_id, index)
            self.duplicate_fragments += 1
            return None
        assembly.parts[index] = bytes(data)
        assembly.updated_at = now
        if assembly.complete():
            payload = assembly.payload()
            del self._pending[message_id]
            self.completed += 1
            return payload
        return None

    def evict(self, now: float) -> int:
        stale = [key for key, assembly in self._pending.items() if now - assembly.updated_at > self.ttl]
        for key in stale:
            del self._pending[key]
            self.dropped += 1
        return len(stale)

    def pending(self) -> dict[str, dict]:
        return {key: {'total': a.total, 'received': len(a.parts)} for key, a in self._pending.items()}

    def stats(self) -> dict:
        return {'pending': len(self._pending), 'completed': self.completed,
                'dropped': self.dropped, 'duplicate_fragments': self.duplicate_fragments}


def authenticate(secret: bytes, sequence: int, frame: Frame) -> bytes:
    material = frame.header + frame.body + struct.pack('>Q', sequence)
    return hmac.new(secret, material, hashlib.sha256).digest()


def verify_frame(secret: bytes, sequence: int, data: bytes, tag: bytes, window) -> Frame:
    frame = decode_frame(data)
    expected = authenticate(secret, sequence, frame)
    if not hmac.compare_digest(expected, tag):
        raise FrameError('auth', 'tag mismatch')
    if not window.accept(sequence):
        raise FrameError('replay', f'sequence {sequence} already used')
    return frame
