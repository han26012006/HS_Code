"""Comprehensive test runner for HS Workspace."""
import os
import sys
import shutil
import tempfile
import inspect
import unittest
from pathlib import Path

class MonkeyPatch:
    def __init__(self):
        self._env_undo = []
        self._attr_undo = []

    def setenv(self, name, value):
        old = os.environ.get(name)
        self._env_undo.append((name, old))
        os.environ[name] = str(value)

    def delenv(self, name, raising=True):
        if name in os.environ:
            self._env_undo.append((name, os.environ[name]))
            del os.environ[name]
        elif raising:
            raise KeyError(name)

    def setattr(self, target, name, value, raising=True):
        if not hasattr(target, name) and raising:
            raise AttributeError(f"{target} has no attribute {name}")
        old = getattr(target, name, None)
        self._attr_undo.append((target, name, old, hasattr(target, name)))
        setattr(target, name, value)

    def undo(self):
        for name, old in reversed(self._env_undo):
            if old is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old
        self._env_undo.clear()
        for target, name, old, had in reversed(self._attr_undo):
            if had:
                setattr(target, name, old)
            else:
                try:
                    delattr(target, name)
                except AttributeError:
                    pass
        self._attr_undo.clear()

def run_test_module(mod, verbosity=1):
    total = 0
    passed = 0
    skipped = 0
    failed = 0

    # Collect module-level fixtures
    fixtures = {}
    for attr in dir(mod):
        val = getattr(mod, attr)
        if callable(val) and getattr(val, '_pytest_fixture', False):
            fixtures[attr] = val

    for name in sorted(dir(mod)):
        if not name.startswith('test_'):
            continue
        fn = getattr(mod, name)
        if not callable(fn):
            continue

        # Check skipif
        skipif = getattr(fn, '_pytest_skipif', None)
        if skipif and skipif[0]:
            print(f"SKIP {name}: {skipif[1]}")
            skipped += 1
            continue

        # Check parametrize
        parametrize = getattr(fn, '_pytest_parametrize', None)
        param_list = [None]
        if parametrize:
            argnames, argvalues = parametrize
            if isinstance(argnames, str):
                argnames = [a.strip() for a in argnames.split(',')]
            param_list = [(argnames, v) for v in argvalues]

        for p in param_list:
            total += 1
            test_desc = name if p is None else f"{name}[{p[1]}]"
            mp = MonkeyPatch()
            temp_dir = tempfile.mkdtemp(prefix="hs_test_")
            tmp_path = Path(temp_dir)

            resolved_fixtures = {}

            def resolve_fixture(f_name):
                if f_name == 'monkeypatch':
                    return mp
                if f_name == 'tmp_path':
                    return tmp_path
                if f_name in resolved_fixtures:
                    return resolved_fixtures[f_name]
                if f_name not in fixtures:
                    raise ValueError(f"Unknown fixture {f_name}")
                fix_fn = fixtures[f_name]
                fix_sig = inspect.signature(fix_fn)
                f_kwargs = {}
                for param in fix_sig.parameters:
                    f_kwargs[param] = resolve_fixture(param)
                res = fix_fn(**f_kwargs)
                if inspect.isgenerator(res):
                    val = next(res)
                else:
                    val = res
                resolved_fixtures[f_name] = val
                return val

            try:
                sig = inspect.signature(fn)
                kwargs = {}
                for param_name in sig.parameters:
                    if p and param_name in p[0]:
                        idx = p[0].index(param_name)
                        kwargs[param_name] = p[1] if len(p[0]) == 1 else p[1][idx]
                    else:
                        kwargs[param_name] = resolve_fixture(param_name)

                fn(**kwargs)
                passed += 1
                if verbosity > 1:
                    print(f"PASS {test_desc}")
            except unittest.SkipTest as e:
                skipped += 1
                print(f"SKIP {test_desc}: {e}")
            except Exception as e:
                failed += 1
                print(f"FAIL {test_desc}: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
            finally:
                mp.undo()
                shutil.rmtree(temp_dir, ignore_errors=True)

    return total, passed, skipped, failed

if __name__ == '__main__':
    mods = sys.argv[1:]
    if not mods:
        mods = ['tests.test_units', 'tests.test_tax', 'tests.test_decision_support']
    for m in mods:
        print(f"\n--- Running {m} ---")
        mod = __import__(m, fromlist=['*'])
        t, p, s, f = run_test_module(mod, verbosity=2)
        print(f"Summary for {m}: Total={t}, Passed={p}, Skipped={s}, Failed={f}")
        if f > 0:
            sys.exit(1)
    print("\nAll tested modules passed successfully!")
