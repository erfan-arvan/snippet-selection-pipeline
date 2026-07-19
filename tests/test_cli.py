from snippet_pipeline.cli import repos_needed_by
from snippet_pipeline.config import RepoConfig
from snippet_pipeline.method_analyzer import MethodRecord


def _repo(name):
    return RepoConfig(name=name, path=f"/fake/{name}", commit=None, build_system="gradle")


def _candidate(project):
    return MethodRecord(raw={
        "project": project, "filePath": "F.java", "qualifiedClassName": "F",
        "methodName": "m", "numParams": 1, "paramTypes": ["int"],
        "passesAllCriteria": True, "targetMethodSignature": "F#m(int)",
    })


def test_only_repos_with_candidates_are_kept():
    all_repos = [_repo("netty"), _repo("kafka"), _repo("guava")]
    candidates = [_candidate("kafka"), _candidate("kafka"), _candidate("guava")]

    result = repos_needed_by(candidates, all_repos)

    assert {r.name for r in result} == {"kafka", "guava"}


def test_repo_with_zero_candidates_is_excluded():
    all_repos = [_repo("netty"), _repo("kafka")]
    candidates = [_candidate("kafka")]

    result = repos_needed_by(candidates, all_repos)

    assert [r.name for r in result] == ["kafka"]


def test_empty_candidates_yields_no_repos():
    all_repos = [_repo("netty"), _repo("kafka")]

    result = repos_needed_by([], all_repos)

    assert result == []


def test_works_the_same_regardless_of_what_criteria_produced_the_candidates():
    # The point of this function: it doesn't care *why* a repo has candidates, only *that* it
    # does - so a totally different/looser candidate set (e.g. from changed filtering criteria
    # in the future) still filters correctly with no code changes needed.
    all_repos = [_repo("netty"), _repo("kafka"), _repo("guava"), _repo("dubbo")]
    differently_shaped_candidates = [_candidate("dubbo"), _candidate("netty"), _candidate("netty")]

    result = repos_needed_by(differently_shaped_candidates, all_repos)

    assert {r.name for r in result} == {"dubbo", "netty"}
