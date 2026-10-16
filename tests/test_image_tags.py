import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from image_tags import metadata, select_tags, validate_version

SHA = "a" * 40


def test_fork_name_is_used_and_normalized():
    result = metadata("Th3Cube/PingPlotter", "refs/heads/main", SHA)
    assert result["image"] == "ghcr.io/th3cube/pingplotter"
    assert result["version"] == "sha-aaaaaaaaaaaa"
    assert not result["release"]


def test_stale_main_cannot_move_edge():
    assert select_tags("refs/heads/main", "sha-123", [], False) == ["sha-123"]
    assert select_tags("refs/heads/main", "sha-123", [], True) == ["sha-123", "edge"]


def test_stable_release_advances_latest_numerically():
    assert select_tags("refs/tags/v1.10.0", "1.10.0", ["edge", "1.9.0"]) == ["1.10.0", "latest"]


def test_older_release_cannot_move_latest():
    assert select_tags("refs/tags/v1.2.0", "1.2.0", ["1.10.0"]) == ["1.2.0"]


def test_first_release_gets_latest():
    assert select_tags("refs/tags/v0.1.0", "0.1.0", ["edge"]) == ["0.1.0", "latest"]


def test_prerelease_never_gets_latest():
    result = metadata("th3cube/pingplotter", "refs/tags/v1.0.0-rc.1", SHA)
    assert result["prerelease"]
    assert select_tags("refs/tags/v1.0.0-rc.1", "1.0.0-rc.1", []) == ["1.0.0-rc.1"]


def test_published_versions_cannot_be_overwritten():
    with pytest.raises(ValueError, match="already exists"):
        select_tags("refs/tags/v1.0.0", "1.0.0", ["1.0.0"])


@pytest.mark.parametrize("version", ["1.0", "01.0.0", "1.0.0-", "1.0.0-rc.01", "1.0.0+build", "1.0.0-rc..1"])
def test_invalid_versions_are_rejected(version):
    with pytest.raises(ValueError):
        validate_version(version)


def test_other_branches_cannot_publish():
    with pytest.raises(ValueError):
        metadata("th3cube/pingplotter", "refs/heads/feature/example", SHA)


def test_pull_request_is_validation_only():
    assert not metadata("th3cube/pingplotter", "refs/pull/1/merge", SHA)["release"]
