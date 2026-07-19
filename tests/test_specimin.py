import pytest

from snippet_pipeline.classpath import ResolvedRepo
from snippet_pipeline.config import RepoConfig
from snippet_pipeline.method_analyzer import MethodRecord
from snippet_pipeline.specimin import SourceRootNotFoundError, find_source_root_and_target_file


def _make_staged_repo(tmp_path):
    """Mimics what classpath.stage_repo() produces: a staging dir with a "source" symlink
    to a (fake) repo containing one module's src/main/java.
    """
    real_repo = tmp_path / "real_repo"
    module_src = real_repo / "transport" / "src" / "main" / "java"
    package_dir = module_src / "io" / "netty" / "channel"
    package_dir.mkdir(parents=True)
    (package_dir / "Foo.java").write_text("package io.netty.channel; class Foo {}")

    staging_dir = tmp_path / "staging" / "netty"
    staging_dir.mkdir(parents=True)
    (staging_dir / "source").symlink_to(real_repo, target_is_directory=True)

    resolved_repo = ResolvedRepo(
        repo=RepoConfig(name="netty", path=str(real_repo), commit=None, build_system="maven"),
        staging_dir=staging_dir,
        source_roots=[staging_dir / "source" / "transport" / "src" / "main" / "java"],
        classpath_jars=[],
    )
    return staging_dir, resolved_repo


def test_finds_source_root_and_relative_target_file(tmp_path):
    staging_dir, resolved_repo = _make_staged_repo(tmp_path)

    record = MethodRecord(raw={
        "project": "netty",
        "filePath": "source/transport/src/main/java/io/netty/channel/Foo.java",
        "qualifiedClassName": "io.netty.channel.Foo",
        "methodName": "bar",
        "numParams": 1,
        "paramTypes": ["int"],
        "passesAllCriteria": True,
        "targetMethodSignature": "io.netty.channel.Foo#bar(int)",
    })

    source_root, target_file = find_source_root_and_target_file(resolved_repo, staging_dir, record)

    # find_source_root_and_target_file resolves through the "source" symlink (the real disk
    # path), which is what Specimin's --root needs - so compare against the resolved form of
    # the configured source root, not its (symlinked) literal spelling.
    assert source_root == resolved_repo.source_roots[0].resolve()
    assert target_file == "io/netty/channel/Foo.java"


def test_raises_when_file_not_under_any_source_root(tmp_path):
    staging_dir, resolved_repo = _make_staged_repo(tmp_path)

    record = MethodRecord(raw={
        "project": "netty",
        "filePath": "source/some/other/module/src/main/java/Other.java",
        "qualifiedClassName": "Other",
        "methodName": "bar",
        "numParams": 1,
        "paramTypes": ["int"],
        "passesAllCriteria": True,
        "targetMethodSignature": "Other#bar(int)",
    })

    with pytest.raises(SourceRootNotFoundError):
        find_source_root_and_target_file(resolved_repo, staging_dir, record)
