"""تست‌های نقطهٔ ورود برنامه بدون ساخت پنجرهٔ واقعی Tkinter.

هر سناریو در یک فرایند جداگانه اجرا می‌شود؛ sys.modules این فایل تست تغییر نمی‌کند.

تست CLI (python -m structpin):
    - با sys.executable و subprocess اجرا می‌شود؛ از runpy استفاده نمی‌شود.
    - stub قبل از شروع CLI از طریق sitecustomize.py موقت نصب می‌شود (پوشهٔ آن ابتدای PYTHONPATH است).
    - شمارنده‌ها در فایل JSON موقت نوشته و خوانده می‌شوند.

اجرا (ریشهٔ مخزن):
    python -m unittest discover -s tests -p "test_app_entrypoint.py" -v
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest


_SRC_DIR = str(pathlib.Path(__file__).resolve().parent.parent / "src")
_TIMEOUT_SECONDS = 60
_COUNTS_PREFIX = "__COUNTS__|"
_RAISE_MARKER = "STRUCTPIN-CLI-ERROR-MARKER-41c9"

# sitecustomize موقت: stub پیش از اجرای structpin.__main__ نصب می‌شود.
_SITECUSTOMIZE = textwrap.dedent(
    """
    import atexit
    import json
    import os

    _counts = {"tk": 0, "mainloop": 0, "window_main": 0}
    _counts_path = os.environ.get("STRUCTPIN_TEST_COUNTS_FILE")
    _mode = os.environ.get("STRUCTPIN_TEST_MODE", "")

    def _write_counts():
        if _counts_path:
            with open(_counts_path, "w", encoding="utf-8") as handle:
                json.dump(_counts, handle)

    atexit.register(_write_counts)

    import tkinter

    class _FakeTk:
        def __init__(self, *args, **kwargs):
            _counts["tk"] += 1

        def mainloop(self, *args, **kwargs):
            _counts["mainloop"] += 1

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    tkinter.Tk = _FakeTk

    import structpin.ui.main_window as _mw

    def _fake_window_main():
        _counts["window_main"] += 1
        if _mode == "raise":
            raise RuntimeError("STRUCTPIN-CLI-ERROR-MARKER-41c9")

    _mw.main = _fake_window_main
    """
)

# پیش‌درآمد مشترک برای تست‌های اسکریپتی (-c).
_PRELUDE = textwrap.dedent(
    """
    import tkinter

    _counts = {"tk": 0, "mainloop": 0, "window_main": 0}

    class _FakeTk:
        def __init__(self, *args, **kwargs):
            _counts["tk"] += 1
        def mainloop(self, *args, **kwargs):
            _counts["mainloop"] += 1
        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    tkinter.Tk = _FakeTk

    import structpin.ui.main_window as _mw

    def _fake_window_main():
        _counts["window_main"] += 1

    _mw.main = _fake_window_main
    """
)

_REPORT_TAIL = textwrap.dedent(
    """
    def _report(app_main_callable):
        print(
            "__COUNTS__|tk={}|mainloop={}|window_main={}|callable={}".format(
                _counts["tk"], _counts["mainloop"], _counts["window_main"],
                1 if app_main_callable else 0,
            ),
            flush=True,
        )
    """
)


def _env_with_src(extra_front: str = "") -> dict:
    env = dict(os.environ)
    parts = [p for p in (extra_front, _SRC_DIR, env.get("PYTHONPATH", "")) if p]
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def _run_child(script: str) -> subprocess.CompletedProcess:
    """اجرای اسکریپت در فرایند فرزند با PYTHONPATH شامل src."""
    try:
        return subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env=_env_with_src(),
            timeout=_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise AssertionError(
            f"فرایند فرزند بعد از {_TIMEOUT_SECONDS} ثانیه متوقف شد (timeout). "
            f"stdout={exc.stdout!r} stderr={exc.stderr!r}"
        ) from exc


def _parse_counts(stdout: str) -> dict:
    lines = [line for line in stdout.splitlines() if line.startswith(_COUNTS_PREFIX)]
    if len(lines) != 1:
        raise AssertionError(
            f"باید دقیقاً یک خط {_COUNTS_PREFIX!r} باشد؛ تعداد: {len(lines)}. stdout={stdout!r}"
        )
    fields = {}
    for part in lines[0][len(_COUNTS_PREFIX):].split("|"):
        key, _, value = part.partition("=")
        fields[key] = int(value)
    return fields


def _script(body: str) -> str:
    return _PRELUDE + _REPORT_TAIL + textwrap.dedent(body)


def _run_cli(mode: str = "") -> tuple:
    """اجرای واقعی `python -m structpin` با stub نصب‌شده از طریق sitecustomize.

    برمی‌گرداند: (CompletedProcess، شمارنده‌ها یا None اگر فایل شمارنده نوشته نشده باشد).
    """
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "sitecustomize.py"), "w", encoding="utf-8") as handle:
            handle.write(_SITECUSTOMIZE)
        counts_path = os.path.join(tmp, "counts.json")
        env = _env_with_src(extra_front=tmp)
        env["STRUCTPIN_TEST_COUNTS_FILE"] = counts_path
        env["STRUCTPIN_TEST_MODE"] = mode
        try:
            result = subprocess.run(
                [sys.executable, "-m", "structpin"],
                capture_output=True,
                text=True,
                env=env,
                cwd=tmp,
                timeout=_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise AssertionError(
                f"`python -m structpin` بعد از {_TIMEOUT_SECONDS} ثانیه متوقف شد (timeout). "
                f"stdout={exc.stdout!r} stderr={exc.stderr!r}"
            ) from exc
        counts = None
        if os.path.exists(counts_path):
            with open(counts_path, "r", encoding="utf-8") as handle:
                counts = json.load(handle)
        return result, counts


class CliRealInvocationTest(unittest.TestCase):
    """اجرای واقعی `python -m structpin` با stub پیش‌نصب‌شده؛ بدون runpy."""

    def test_python_dash_m_structpin_calls_window_main_once_and_no_tk(self):
        result, counts = _run_cli()
        self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr}")
        self.assertIsNotNone(counts, msg=f"فایل شمارنده نوشته نشد. stderr={result.stderr}")
        self.assertEqual(counts["window_main"], 1)
        self.assertEqual(counts["tk"], 0)
        self.assertEqual(counts["mainloop"], 0)

    def test_python_dash_m_structpin_propagates_window_error_to_stderr(self):
        result, counts = _run_cli(mode="raise")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RuntimeError", result.stderr)
        self.assertIn(_RAISE_MARKER, result.stderr)
        self.assertIsNotNone(counts, msg=f"فایل شمارنده نوشته نشد. stderr={result.stderr}")
        self.assertEqual(counts["window_main"], 1)
        self.assertEqual(counts["tk"], 0)
        self.assertEqual(counts["mainloop"], 0)


class ImportAppTest(unittest.TestCase):
    """import structpin.app نباید پنجره بسازد یا mainloop را اجرا کند."""

    def test_import_app_has_zero_side_effects_and_callable_main(self):
        result = _run_child(_script(
            """
            import structpin.app
            _report(callable(structpin.app.main))
            """
        ))
        self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr}")
        counts = _parse_counts(result.stdout)
        self.assertEqual(counts["tk"], 0)
        self.assertEqual(counts["mainloop"], 0)
        self.assertEqual(counts["window_main"], 0)
        self.assertEqual(counts["callable"], 1)


class ImportMainTest(unittest.TestCase):
    """import ماژول نقطهٔ ورود (__main__.py) نباید app.main را اجرا کند."""

    def test_import_entry_module_does_not_run_app(self):
        result = _run_child(_script(
            """
            import structpin.__main__
            _report(True)
            """
        ))
        self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr}")
        counts = _parse_counts(result.stdout)
        self.assertEqual(counts["tk"], 0)
        self.assertEqual(counts["mainloop"], 0)
        self.assertEqual(counts["window_main"], 0)


class AppMainDelegationTest(unittest.TestCase):
    """app.main باید دقیقاً یک بار stub شمارش‌شونده main_window.main را فراخوانی کند."""

    def test_app_main_calls_window_main_exactly_once(self):
        result = _run_child(_script(
            """
            import structpin.app
            structpin.app.main()
            _report(True)
            """
        ))
        self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr}")
        counts = _parse_counts(result.stdout)
        self.assertEqual(counts["window_main"], 1)
        self.assertEqual(counts["tk"], 0)
        self.assertEqual(counts["mainloop"], 0)


class ErrorPropagationTest(unittest.TestCase):
    """خطای تابع اصلی پنجره باید بدون پنهان‌سازی به stderr فرایند برسد (مسیر app.main)."""

    def test_runtime_error_reaches_stderr_via_app_main(self):
        result = _run_child(textwrap.dedent(
            f"""
            import tkinter
            class _FakeTk:
                def __init__(self, *a, **k): pass
                def __getattr__(self, name): return lambda *a, **k: None
            tkinter.Tk = _FakeTk

            import structpin.ui.main_window as _mw

            def _boom():
                raise RuntimeError("{_RAISE_MARKER}")

            _mw.main = _boom

            import structpin.app
            structpin.app.main()
            """
        ))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RuntimeError", result.stderr)
        self.assertIn(_RAISE_MARKER, result.stderr)


if __name__ == "__main__":
    unittest.main()
