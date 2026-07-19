from snippet_pipeline.classpath import resolve_classpath_gradle, resolve_classpath_maven


def test_gradle_resolution_degrades_gracefully_when_no_wrapper_and_no_fallback(tmp_path, capsys):
    # Reproduces the real failure hit on HPC: a repo checkout with no gradlew of its own, and
    # a fallback command that also doesn't exist anywhere on PATH. This must not crash the
    # whole run - it should log a warning and return an empty jar list.
    jars = resolve_classpath_gradle(tmp_path, "definitely-not-a-real-command-xyz")

    assert jars == []
    assert "WARNING" in capsys.readouterr().out


def test_maven_resolution_degrades_gracefully_when_no_wrapper_and_no_fallback(tmp_path, capsys):
    (tmp_path / "pom.xml").write_text("<project></project>")

    jars = resolve_classpath_maven(tmp_path, "definitely-not-a-real-command-xyz")

    assert jars == []
    assert "WARNING" in capsys.readouterr().out


def test_maven_resolution_with_no_pom_returns_empty_without_running_anything(tmp_path, capsys):
    jars = resolve_classpath_maven(tmp_path, "definitely-not-a-real-command-xyz")

    assert jars == []
    assert capsys.readouterr().out == ""
