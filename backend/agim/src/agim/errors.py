"""Errors agim raises for platform payloads it refuses to hand back."""


class MediaTooLargeError(ValueError):
    """One attachment exceeded the payload size agim is willing to hold.

    Callers decide what an oversized attachment means for their own surface: an
    SDK caller may log it, and a chat host may answer the sender instead of
    running a turn over bytes it never received.
    """


__all__ = ["MediaTooLargeError"]
