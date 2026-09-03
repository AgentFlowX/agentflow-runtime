"""A manifest-only directory must never shadow a working plugin.

Observed live: a half-cleaned backup copy of a plugin (``tg_ops.pre_fix``) kept
its ``plugin.yaml`` but lost its Python files. Discovery still parsed that
manifest, which claims the SAME key as the real plugin, so the real one never
loaded and all 25 of its tools vanished from the agent — with the plugin listed
as "enabled" the whole time.
"""

import textwrap
from pathlib import Path

from hermes_cli.plugins import _has_plugin_code


def _write(dirpath: Path, *, code: bool, key: str = "demo") -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    (dirpath / "plugin.yaml").write_text(
        textwrap.dedent(f"""\
        name: {key}
        version: 0.1.0
        description: demo
        kind: backend
        """)
    )
    if code:
        (dirpath / "__init__.py").write_text("def register(ctx):\n    pass\n")
    return dirpath


def test_directory_with_code_is_a_plugin(tmp_path):
    assert _has_plugin_code(_write(tmp_path / "real", code=True))


def test_manifest_without_code_is_debris(tmp_path):
    assert not _has_plugin_code(_write(tmp_path / "real.pre_fix", code=False))


def test_single_module_plugin_counts_as_code(tmp_path):
    d = _write(tmp_path / "mod", code=False)
    (d / "main.py").write_text("x = 1\n")
    assert _has_plugin_code(d)


def test_portable_manifest_counts_as_code(tmp_path):
    d = _write(tmp_path / "portable", code=False)
    (d / "plugin.json").write_text('{"name": "portable"}')
    assert _has_plugin_code(d)


def test_scan_skips_debris_and_keeps_the_real_plugin(tmp_path):
    """The whole point: a broken copy must not hide the working plugin."""
    from hermes_cli.plugins import PluginManager

    root = tmp_path / "plugins"
    _write(root / "demo", code=True, key="demo")
    _write(root / "demo.pre_fix", code=False, key="demo")

    mgr = PluginManager.__new__(PluginManager)  # no __init__: scanning needs no state
    found = mgr._scan_directory_level(root, "bundled", skip_names=set(), prefix="", depth=0)
    paths = {Path(m.path).name for m in found}
    assert "demo" in paths
    assert "demo.pre_fix" not in paths
