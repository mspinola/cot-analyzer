"""Store-free smoke test: byte-compile the app source tree so import-name and
syntax errors surface in CI without constructing the (data-store-backed) indexer.
The metrics/data layer is tested in the cotmetrics repo."""
import compileall
import pathlib


def test_app_source_compiles():
    src = pathlib.Path(__file__).resolve().parent.parent / "src"
    assert compileall.compile_dir(str(src), quiet=1), "app source failed to byte-compile"
