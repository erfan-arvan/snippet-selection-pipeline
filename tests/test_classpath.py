from snippet_pipeline.classpath import discover_source_roots, resolve_classpath_gradle, resolve_classpath_maven


def _touch_java_dir(base, *parts):
    d = base.joinpath(*parts)
    d.mkdir(parents=True, exist_ok=True)
    (d / "Dummy.java").write_text("class Dummy {}")
    return d


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


def test_finds_standard_main_source_set(tmp_path):
    expected = _touch_java_dir(tmp_path, "src", "main", "java")

    roots = discover_source_roots(tmp_path)

    assert expected in roots


def test_finds_multi_module_main_source_sets(tmp_path):
    expected_a = _touch_java_dir(tmp_path, "module-a", "src", "main", "java")
    expected_b = _touch_java_dir(tmp_path, "module-b", "src", "main", "java")

    roots = discover_source_roots(tmp_path)

    assert expected_a in roots
    assert expected_b in roots


def test_finds_the_real_ghidra_gpl_dmg_non_standard_source_set(tmp_path):
    # Regression test for the real bug: ghidra's GPL/DMG module uses "src/dmg/java" instead of
    # the Gradle-default "src/main/java" - confirmed directly against the live repo, not a
    # hypothetical. discover_source_roots must find it via EXTRA_SOURCE_SET_NAMES.
    expected = _touch_java_dir(tmp_path, "GPL", "DMG", "src", "dmg", "java")

    roots = discover_source_roots(tmp_path)

    assert expected in roots


def test_does_not_treat_arbitrary_non_main_source_sets_as_production(tmp_path):
    # Only "main" plus confirmed EXTRA_SOURCE_SET_NAMES entries count - an arbitrary custom
    # source set (e.g. a jmh benchmark source set) must not be swept in as if it were
    # production code just because it isn't literally named "test".
    _touch_java_dir(tmp_path, "src", "jmh", "java")

    roots = discover_source_roots(tmp_path)

    assert not any("jmh" in str(r) for r in roots)


def test_excludes_test_source_set(tmp_path):
    _touch_java_dir(tmp_path, "module-a", "src", "test", "java")
    expected_main = _touch_java_dir(tmp_path, "module-a", "src", "main", "java")

    roots = discover_source_roots(tmp_path)

    assert expected_main in roots
    assert not any("/test/" in str(r) for r in roots)


def test_falls_back_to_repo_root_when_nothing_found(tmp_path):
    roots = discover_source_roots(tmp_path)

    assert roots == [tmp_path]
