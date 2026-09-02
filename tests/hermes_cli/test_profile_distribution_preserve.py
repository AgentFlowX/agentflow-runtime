"""`hermes profile update` must never silently destroy a local edit.

Distribution-owned files (SOUL.md, skills/, cron/, mcp.json) are refreshed from
the source on update.  These tests pin the rule that decides whether a given
file is refreshed or kept:

* install/update records a sha256 of every file it writes in
  ``.dist-hashes.json`` at the profile root;
* on update a file whose content still matches that record is overwritten
  (template improvements reach installed agents);
* a file whose content no longer matches was edited locally — by the owner or
  by the agent itself — so the local version stays and the incoming version is
  written beside it as ``<name>.new``;
* a LEGACY profile (installed before the record existed) has no record at all;
  that must not read as "unmodified", so such a file counts as edited whenever
  it differs from the incoming version;
* ``force=True`` waives all of it.

Exercised through the library API (install_distribution / update_distribution)
rather than the CLI.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hermes_cli.profile_distribution import (
    DIST_HASHES_FILENAME,
    DistributionManifest,
    install_distribution,
    read_manifest,
    update_distribution,
    write_manifest,
)


@pytest.fixture()
def profile_env(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    default_home = tmp_path / ".hermes"
    default_home.mkdir(exist_ok=True)
    monkeypatch.setenv("HERMES_HOME", str(default_home))
    return tmp_path


def _make_staging_dir(root: Path, name: str = "src") -> Path:
    """A minimal local distribution: SOUL.md, config.yaml, mcp.json, a skill."""
    staged = root / f"staging_{name}"
    staged.mkdir(parents=True, exist_ok=True)
    (staged / "SOUL.md").write_text("I am Source.\n")
    (staged / "config.yaml").write_text("model:\n  model: gpt-4\n")
    (staged / "mcp.json").write_text('{"servers": {}}\n')
    (staged / "skills" / "demo").mkdir(parents=True, exist_ok=True)
    (staged / "skills" / "demo" / "SKILL.md").write_text(
        "---\nname: demo\ndescription: test\n---\n# Demo skill\n"
    )
    write_manifest(staged, DistributionManifest(name=name, version="0.1.0"))
    return staged


def _install(staged: Path, name: str):
    return install_distribution(str(staged), name=name)


def _drop_hash_record(target: Path) -> None:
    """Turn an installed profile into a pre-upgrade ("legacy") one."""
    (target / DIST_HASHES_FILENAME).unlink()


def _bump(staged: Path, version: str) -> None:
    mf = read_manifest(staged)
    mf.version = version
    write_manifest(staged, mf)


# ===========================================================================
# (a) local edit is kept, incoming version lands as <name>.new
# ===========================================================================


class TestLocalEditPreserved:

    def test_edited_soul_is_kept_and_new_version_written_beside_it(self, profile_env):
        staged = _make_staging_dir(profile_env, "keep")
        plan = _install(staged, "keep")
        target = plan.target_dir

        # The agent appends a rule to its own SOUL.md after install.
        (target / "SOUL.md").write_text("I am Source.\nRule the agent added.\n")

        # The distribution moves on.
        (staged / "SOUL.md").write_text("I am Source v2.\n")
        _bump(staged, "0.2.0")

        result = update_distribution("keep")

        assert (target / "SOUL.md").read_text() == (
            "I am Source.\nRule the agent added.\n"
        ), "the agent's edit must survive the update"
        assert (target / "SOUL.md.new").read_text() == "I am Source v2.\n"
        assert result.preserved_paths == ["SOUL.md"]

    def test_edited_file_inside_a_directory_entry_is_kept(self, profile_env):
        staged = _make_staging_dir(profile_env, "dirkeep")
        plan = _install(staged, "dirkeep")
        target = plan.target_dir
        skill = target / "skills" / "demo" / "SKILL.md"

        skill.write_text("---\nname: demo\n---\n# Edited by the agent\n")
        (staged / "skills" / "demo" / "SKILL.md").write_text(
            "---\nname: demo\n---\n# Upstream v2\n"
        )

        result = update_distribution("dirkeep")

        assert "# Edited by the agent" in skill.read_text()
        assert "# Upstream v2" in (
            target / "skills" / "demo" / "SKILL.md.new"
        ).read_text()
        assert result.preserved_paths == ["skills/demo/SKILL.md"]

    def test_agent_authored_file_inside_a_dist_directory_survives(self, profile_env):
        """A skill the agent wrote itself is not swept away by the refresh."""
        staged = _make_staging_dir(profile_env, "own")
        plan = _install(staged, "own")
        own = plan.target_dir / "skills" / "mine" / "SKILL.md"
        own.parent.mkdir(parents=True, exist_ok=True)
        own.write_text("---\nname: mine\n---\n# Written by the agent\n")

        update_distribution("own")

        assert own.read_text() == "---\nname: mine\n---\n# Written by the agent\n"

    def test_preserved_file_stays_preserved_across_repeated_updates(self, profile_env):
        staged = _make_staging_dir(profile_env, "again")
        plan = _install(staged, "again")
        (plan.target_dir / "SOUL.md").write_text("local\n")

        (staged / "SOUL.md").write_text("v2\n")
        assert update_distribution("again").preserved_paths == ["SOUL.md"]
        assert update_distribution("again").preserved_paths == ["SOUL.md"]
        assert (plan.target_dir / "SOUL.md").read_text() == "local\n"

    def test_adopting_the_new_file_resyncs_the_path(self, profile_env):
        """Copying <name>.new over the local file re-enrolls it in updates."""
        staged = _make_staging_dir(profile_env, "adopt")
        plan = _install(staged, "adopt")
        target = plan.target_dir
        (target / "SOUL.md").write_text("local\n")
        (staged / "SOUL.md").write_text("v2\n")
        update_distribution("adopt")

        # Owner accepts the incoming version.
        (target / "SOUL.md").write_text((target / "SOUL.md.new").read_text())

        (staged / "SOUL.md").write_text("v3\n")
        result = update_distribution("adopt")
        assert result.preserved_paths == []
        assert (target / "SOUL.md").read_text() == "v3\n"


# ===========================================================================
# (b) untouched files still receive template improvements
# ===========================================================================


class TestUntouchedFilesStillUpdate:

    def test_unmodified_soul_is_overwritten(self, profile_env):
        staged = _make_staging_dir(profile_env, "flow")
        plan = _install(staged, "flow")

        (staged / "SOUL.md").write_text("I am Source v2.\n")
        _bump(staged, "0.2.0")

        result = update_distribution("flow")

        assert (plan.target_dir / "SOUL.md").read_text() == "I am Source v2.\n"
        assert not (plan.target_dir / "SOUL.md.new").exists()
        assert result.preserved_paths == []

    def test_unmodified_skill_is_overwritten(self, profile_env):
        staged = _make_staging_dir(profile_env, "flowdir")
        plan = _install(staged, "flowdir")

        (staged / "skills" / "demo" / "SKILL.md").write_text(
            "---\nname: demo\n---\n# Upstream v2\n"
        )
        update_distribution("flowdir")

        assert "# Upstream v2" in (
            plan.target_dir / "skills" / "demo" / "SKILL.md"
        ).read_text()

    def test_hash_record_is_written_on_install(self, profile_env):
        staged = _make_staging_dir(profile_env, "rec")
        plan = _install(staged, "rec")
        import json

        data = json.loads((plan.target_dir / DIST_HASHES_FILENAME).read_text())
        assert data["version"] == 1
        assert "SOUL.md" in data["files"]
        assert "skills/demo/SKILL.md" in data["files"]


# ===========================================================================
# (c) legacy profile — no hash record on disk
# ===========================================================================


class TestLegacyProfileWithoutHashRecord:

    def test_modified_soul_is_kept_when_no_record_exists(self, profile_env):
        staged = _make_staging_dir(profile_env, "legacy")
        plan = _install(staged, "legacy")
        target = plan.target_dir

        (target / "SOUL.md").write_text("Edited before the upgrade.\n")
        _drop_hash_record(target)

        (staged / "SOUL.md").write_text("I am Source v2.\n")
        result = update_distribution("legacy")

        assert (target / "SOUL.md").read_text() == "Edited before the upgrade.\n"
        assert (target / "SOUL.md.new").read_text() == "I am Source v2.\n"
        assert result.preserved_paths == ["SOUL.md"]

    def test_changed_template_is_also_kept_when_no_record_exists(self, profile_env):
        """The deliberate cost of the legacy fallback.

        Without a record we cannot tell "the owner edited this" from "the
        template moved on" — both just look different from the incoming file.
        We choose the safe side and keep the local copy, so on a legacy
        profile the first update after the upgrade may hand back a .new for a
        file nobody touched.  That costs one manual copy; the other branch
        would cost the edit itself.  The record is seeded here, so every later
        update is exact (see test_record_is_seeded_so_the_next_update_is_precise).
        """
        staged = _make_staging_dir(profile_env, "legacy2")
        plan = _install(staged, "legacy2")
        _drop_hash_record(plan.target_dir)

        (staged / "SOUL.md").write_text("I am Source v2.\n")
        result = update_distribution("legacy2")

        assert (plan.target_dir / "SOUL.md").read_text() == "I am Source.\n"
        assert (plan.target_dir / "SOUL.md.new").read_text() == "I am Source v2.\n"
        assert result.preserved_paths == ["SOUL.md"]

    def test_identical_file_updates_silently_when_no_record_exists(self, profile_env):
        """No record, but the file matches what we are about to write: nothing
        is at stake, so it flows through as a normal overwrite."""
        staged = _make_staging_dir(profile_env, "legacy3")
        plan = _install(staged, "legacy3")
        _drop_hash_record(plan.target_dir)

        result = update_distribution("legacy3")

        assert (plan.target_dir / "SOUL.md").read_text() == "I am Source.\n"
        assert not (plan.target_dir / "SOUL.md.new").exists()
        assert result.preserved_paths == []

    def test_record_is_seeded_so_the_next_update_is_precise(self, profile_env):
        staged = _make_staging_dir(profile_env, "seed")
        plan = _install(staged, "seed")
        target = plan.target_dir
        _drop_hash_record(target)

        update_distribution("seed")
        assert (target / DIST_HASHES_FILENAME).is_file()

        # With a record in place an edit is detected even though the incoming
        # file is byte-identical to what the distribution shipped before.
        (target / "SOUL.md").write_text("edited after the upgrade\n")
        result = update_distribution("seed")
        assert result.preserved_paths == ["SOUL.md"]
        assert (target / "SOUL.md").read_text() == "edited after the upgrade\n"

    def test_corrupt_record_falls_back_to_the_safe_comparison(self, profile_env):
        staged = _make_staging_dir(profile_env, "corrupt")
        plan = _install(staged, "corrupt")
        target = plan.target_dir
        (target / DIST_HASHES_FILENAME).write_text("{not json")

        (target / "SOUL.md").write_text("local\n")
        result = update_distribution("corrupt")

        assert (target / "SOUL.md").read_text() == "local\n"
        assert result.preserved_paths == ["SOUL.md"]


# ===========================================================================
# (d) --force overwrites regardless
# ===========================================================================


class TestForceOverwrites:

    def test_force_overwrites_a_local_edit(self, profile_env):
        staged = _make_staging_dir(profile_env, "forced")
        plan = _install(staged, "forced")
        target = plan.target_dir

        (target / "SOUL.md").write_text("local edit\n")
        (staged / "SOUL.md").write_text("I am Source v2.\n")

        result = update_distribution("forced", force=True)

        assert (target / "SOUL.md").read_text() == "I am Source v2.\n"
        assert not (target / "SOUL.md.new").exists()
        assert result.preserved_paths == []

    def test_force_also_overwrites_config(self, profile_env):
        staged = _make_staging_dir(profile_env, "forcedcfg")
        plan = _install(staged, "forcedcfg")
        (plan.target_dir / "config.yaml").write_text("model:\n  model: gpt-5\n")
        (staged / "config.yaml").write_text("model:\n  model: claude\n")

        update_distribution("forcedcfg", force=True)
        assert "claude" in (plan.target_dir / "config.yaml").read_text()

    def test_force_sweeps_local_files_out_of_a_dist_directory(self, profile_env):
        staged = _make_staging_dir(profile_env, "forcedir")
        plan = _install(staged, "forcedir")
        stray = plan.target_dir / "skills" / "mine" / "SKILL.md"
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_text("# agent's own\n")

        update_distribution("forcedir", force=True)
        assert not stray.exists()

    def test_without_force_config_stays_preserved(self, profile_env):
        staged = _make_staging_dir(profile_env, "cfgkeep")
        plan = _install(staged, "cfgkeep")
        (plan.target_dir / "config.yaml").write_text("model:\n  model: gpt-5\n")
        (staged / "config.yaml").write_text("model:\n  model: claude\n")

        result = update_distribution("cfgkeep")
        assert "gpt-5" in (plan.target_dir / "config.yaml").read_text()
        # config.yaml is preserved wholesale, so it is not reported as an edit.
        assert result.preserved_paths == []


# ===========================================================================
# Stale template files
# ===========================================================================


class TestStaleTemplateFiles:

    def test_untouched_file_dropped_by_the_distribution_is_removed(self, profile_env):
        staged = _make_staging_dir(profile_env, "stale")
        (staged / "skills" / "old").mkdir(parents=True)
        (staged / "skills" / "old" / "SKILL.md").write_text("# old skill\n")
        plan = _install(staged, "stale")
        assert (plan.target_dir / "skills" / "old" / "SKILL.md").exists()

        import shutil
        shutil.rmtree(staged / "skills" / "old")
        update_distribution("stale")

        assert not (plan.target_dir / "skills" / "old" / "SKILL.md").exists()

    def test_edited_file_dropped_by_the_distribution_is_kept(self, profile_env):
        staged = _make_staging_dir(profile_env, "stale2")
        (staged / "skills" / "old").mkdir(parents=True)
        (staged / "skills" / "old" / "SKILL.md").write_text("# old skill\n")
        plan = _install(staged, "stale2")
        kept = plan.target_dir / "skills" / "old" / "SKILL.md"
        kept.write_text("# old skill, edited by the agent\n")

        import shutil
        shutil.rmtree(staged / "skills" / "old")
        update_distribution("stale2")

        assert kept.read_text() == "# old skill, edited by the agent\n"
