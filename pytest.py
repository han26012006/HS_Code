"""Lightweight, zero-dependency pytest compatibility shim for local execution."""
import inspect
import re
import sys
import unittest

def fixture(*args, **kwargs):
    scope = kwargs.get('scope', 'function')
    if len(args) == 1 and callable(args[0]):
        fn = args[0]
        fn._pytest_fixture = True
        return fn
    def decorator(fn):
        fn._pytest_fixture = True
        fn._fixture_scope = scope
        return fn
    return decorator

class raises:
    def __init__(self, expected_exc, match=None):
        self.expected_exc = expected_exc
        self.match = match
        self.exc_value = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            raise AssertionError(f"DID NOT RAISE {self.expected_exc}")
        if not issubclass(exc_type, self.expected_exc):
            return False
        self.exc_value = exc_val
        if self.match is not None:
            msg = str(exc_val)
            if not re.search(self.match, msg):
                raise AssertionError(f"Pattern '{self.match}' does not match '{msg}'")
        return True

class _Mark:
    def skipif(self, condition, reason=""):
        def decorator(fn):
            fn._pytest_skipif = (condition, reason)
            return fn
        return decorator

    def parametrize(self, argnames, argvalues):
        def decorator(fn):
            fn._pytest_parametrize = (argnames, argvalues)
            return fn
        return decorator

    def __getattr__(self, name):
        def decorator(fn):
            return fn
        return decorator

mark = _Mark()

def importorskip(modname):
    try:
        return __import__(modname)
    except ImportError:
        raise unittest.SkipTest(f"Skipping: {modname} is not installed")

def skip(reason=""):
    raise unittest.SkipTest(reason)

