#!/usr/bin/env python3
"""Converts an old MethodAnalyzerApp export (the pre-rewrite CSV/xlsx schema, with columns
like ParamTypes/AllStandard/AllCustomAndUnresolved/CleanLoc) into this pipeline's manifest
JSONL format, so Stage C (select) onward can run without re-scanning the repos.

This is a one-off bridge for reusing already-computed data, not a supported input format for
the pipeline in general - it inherits the old schema's known limitations:

  - Criterion 1 (all-JDK-types) is approximated via `AllCustomAndUnresolved == 0` rather than
    recomputed with the newer, stricter check (which also verifies the *declaring type* of
    every method call, not just resolved expression/parameter types). Accepted as a known,
    intentional gap for this one-off conversion.
  - The old CSV export sanitized commas out of list-like fields (ParamTypes), so for methods
    with 2+ parameters there is no reliable way to split individual parameter types back out.
    Rows where that split can't be validated are dropped, not guessed, and counted separately
    in the summary this script prints.
  - There's no line-range information in the old schema, so `startLine`/`endLine` are written
    as null - purely informational fields the rest of the pipeline doesn't actually need to
    function (Specimin slicing only needs the file path + target method signature).

Usage:
    python3 convert_legacy_xlsx.py <input.xlsx> <output_manifest.jsonl>
"""
from __future__ import annotations

import json
import re
import sys

import openpyxl

MIN_LOC = 20
MAX_LOC = 30

# Reverses the token substitutions the old CSVWriter.sanitizeForCSV applied to bracket-like
# characters (commas were also replaced with spaces, but that's not reversible - see module
# docstring). Order matters: longer/more-specific tokens must be replaced before shorter ones
# that could be a substring of another (none actually collide here, but keep it explicit).
_TOKEN_UNSANITIZE = [
    (" ocb ", "{"), (" ccb ", "}"),
    (" ob ", "["), (" cb ", "]"),
    (" op ", "("), (" cp ", ")"),
]


# Specimin matches --targetMethod against type names as they're spelled in the source (i.e.
# respecting imports), not fully-qualified names - but the old xlsx's ParamTypes column stored
# fully-resolved names from the original tool's symbol resolution. This strips any qualified
# prefix down to the simple name (java.lang.CharSequence -> CharSequence), leaving primitives
# and type variables (int, E) untouched, and works inside generics too (List<java.lang.String>
# -> List<String>) since it just matches "lowercase.lowercase.Uppercase" anywhere in the string.
_QUALIFIED_TYPE_RE = re.compile(r"\b(?:[a-z_][a-zA-Z0-9_]*\.)+([A-Z][a-zA-Z0-9_]*)\b")


def _simple_type_name(qualified: str) -> str:
    return _QUALIFIED_TYPE_RE.sub(r"\1", qualified)


def _unsanitize_tokens(text: str) -> str:
    # Pad with a leading/trailing space before matching: the original sanitizer's substitution
    # (e.g. "[" -> " ob ") naturally produces a leading/trailing space when the bracket was at
    # the very start/end of the field, but it's not certain that space survived being written
    # to and re-read from Excel - padding here makes the match work either way.
    result = f" {text} "
    for token, char in _TOKEN_UNSANITIZE:
        result = result.replace(token, char)
    return result.strip()


def parse_param_types(raw_param_types: str, num_params: int) -> list[str] | None:
    """Recovers the parameter type list from the old sanitized ParamTypes field.

    Returns None (meaning: drop this row) if the split can't be validated - e.g. any case
    where the recovered token count doesn't match num_params, since that means the original
    comma-separated boundaries can't be reliably reconstructed from the sanitized text.
    """
    if num_params == 0:
        return []

    text = _unsanitize_tokens(raw_param_types or "")
    # Expect something like "[int]" or "[int String]" (commas already lost to sanitization).
    match = re.match(r"^\[(.*)\]$", text)
    if not match:
        return None
    inner = match.group(1).strip()
    if not inner:
        return None

    if num_params == 1:
        # A single parameter's type may itself contain spaces (e.g. "int []", generics with
        # nested types), so don't split on whitespace here - the whole bracket contents is it.
        return [inner]

    # 2+ params: the original comma separators are gone, so all we can do is split on
    # whitespace and check the token count matches. This only works because any row that
    # reaches this function already passed the AllCustomAndUnresolved == 0 check, so its
    # types should be plain (no generics/spaces) - see module docstring.
    tokens = inner.split()
    if len(tokens) != num_params:
        return None
    return tokens


def convert(input_path: str, output_path: str) -> None:
    wb = openpyxl.load_workbook(input_path, read_only=True, data_only=True)
    ws = wb.active

    rows = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else "" for h in next(rows)]

    # The sheet has two columns both named "CleanLoc" (Z and AA) - use the first occurrence
    # per the user's confirmation that it's the authoritative one, not the later duplicate.
    clean_loc_index = header.index("CleanLoc")

    def col(name: str, row: tuple):
        return row[header.index(name)]

    total = 0
    passed = 0
    dropped_unparseable_params = 0

    with open(output_path, "w") as out:
        for row in rows:
            if row is None:
                continue
            # A real data row must have a method name - this is a stronger signal than "not
            # every cell is None", which turned out to be too weak: the source sheet's used
            # range extends to Excel's absolute row limit (a formatting artifact, not real
            # data), and some of those trailing "ghost" rows have a stray non-null value in
            # some column while still having no actual method data.
            method_name = col("Method", row)
            if method_name is None or not str(method_name).strip():
                continue
            total += 1

            path = col("Path", row) or ""
            class_name = col("Class", row) or ""
            package_name = col("Package", row) or ""
            return_type = col("ReturnType", row) or ""
            is_static = str(col("isStatic", row)).strip().upper() == "TRUE"
            num_params = int(col("NumParams", row) or 0)
            annotations_raw = col("Annotations", row) or ""
            javadoc = col("Javadoc", row) or ""
            all_custom_and_unresolved = col("AllCustomAndUnresolved", row)
            all_custom_and_unresolved = int(all_custom_and_unresolved) if all_custom_and_unresolved is not None else None
            clean_loc = row[clean_loc_index]
            clean_loc = int(clean_loc) if clean_loc is not None else None
            project = col("project", row) or ""

            qualified_class_name = f"{package_name}.{class_name}" if package_name else str(class_name)

            criteria = {
                "isStatic": is_static,
                "noAnnotations": not str(annotations_raw).strip(),
                "hasJavadoc": bool(str(javadoc).strip()),
                "paramAndReturnOk": num_params >= 1 and str(return_type).strip() != "void",
                "locInRange": clean_loc is not None and MIN_LOC <= clean_loc <= MAX_LOC,
                "allTypesJdk": all_custom_and_unresolved == 0,
            }
            passes_all = all(criteria.values())

            # Computed for every row, not just ones passing all six criteria: the signature is
            # purely a function of the method's own shape (class/name/param types), and which
            # criteria matter is a config choice (`required_criteria`) made later in `select` -
            # a row can be a valid candidate under a looser required-criteria set without
            # passing all six, and still needs a real signature to be sliceable.
            param_types = parse_param_types(col("ParamTypes", row) or "", num_params)
            if param_types is None:
                dropped_unparseable_params += 1
                continue
            simple_param_types = [_simple_type_name(t) for t in param_types]
            target_method_signature = f"{qualified_class_name}#{method_name}(" + ", ".join(simple_param_types) + ")"

            # Recreate the staging-relative file path convention: strip the old "repos/<repo>/"
            # prefix and prepend "source/" (matching classpath.stage_repo's symlink layout).
            file_path = "source/" + re.sub(r"^repos/[^/]+/", "", str(path))

            record = {
                "project": str(project),
                "filePath": file_path,
                "packageName": str(package_name),
                "qualifiedClassName": qualified_class_name,
                "methodName": str(method_name),
                "returnType": str(return_type),
                "paramTypes": param_types if param_types is not None else [],
                "numParams": num_params,
                "isStatic": is_static,
                "annotations": [] if criteria["noAnnotations"] else [str(annotations_raw)],
                "hasJavadoc": criteria["hasJavadoc"],
                "javadoc": str(javadoc),
                "rawLoc": clean_loc,
                "cleanLoc": clean_loc,
                "startLine": None,
                "endLine": None,
                "allTypesJdk": criteria["allTypesJdk"],
                "offendingTypes": [],
                "criteria": criteria,
                "passesAllCriteria": passes_all,
                "targetMethodSignature": target_method_signature,
            }
            out.write(json.dumps(record) + "\n")
            if passes_all:
                passed += 1

    print(f"Total rows read: {total}")
    print(f"Rows dropped for unrecoverable multi-param types (any row, pass or fail criteria): {dropped_unparseable_params}")
    print(f"Rows written to manifest: {total - dropped_unparseable_params}")
    print(f"  of which passing all six criteria: {passed}")
    print(f"Manifest written to: {output_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.xlsx> <output_manifest.jsonl>", file=sys.stderr)
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
