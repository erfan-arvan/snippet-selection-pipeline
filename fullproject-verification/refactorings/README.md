# Refactorings for the included rows

One patch per included row of the review spreadsheet, each against the pinned commit, meant to make the checker accept the method **without
annotations and without changing behaviour**. `submit_check_refactorings.sh` runs the checker on the
original (control) and on the refactored method and reports whether the warning goes away.

| case | method | checker / warning | refactoring | behaviour |
|---|---|---|---|---|
| row13 | dubbo `ReflectUtils.getGenericClass` | index, `[0]` and `[i]` | Martin's version: validate the interface array and the index at the start and throw the method's own `IllegalArgumentException`; the `try` now only covers the remaining casts | NOT exactly equivalent: same exception type and message for invalid inputs, but (1) no wrapped cause, (2) reflection errors from malformed class files no longer wrapped, (3) for `cls == null` the NPE comes from a different call, so its JDK message differs |
| row16 | dubbo `UrlUtils.isMatchGlobPattern` | index, `substring(i + 1)` | inline `StringUtils.isEmpty` (`s == null \|\| s.isEmpty()`) and merge the two empty-checks, so the checker sees `pattern` is non-empty; no new check | identical for every input (both empty: true; one empty: false) |
| row54 | ghidra `MachHeaderFlags.getFlags` | index, `substring("MH_".length())` | `field.getName()` stored in a local, checked and used (Martin: LGTM) | identical |
| row90 | ghidra `InstructionUtils.getFormatedInstructionObjects` | nullness, `toArray` | `set.toArray(new String[set.size()])` (Martin: LGTM) | identical |
| row94 | ghidra `EuclideanHyperSpace.collectBounds` | index, `result[i * 2]`, `result[i * 2 + 1]` | loop over the result array in steps of 2 (`j + 1 < result.length`) with an iterator over the dimensions, instead of index arithmetic | identical (same elements, same order, same exception on an overflowing size); differs only if lower()/upper() modified the list during the loop |
| row114 | hudi `HoodieTableFileSystemView.fetchAllStoredFileGroups` | nullness, second `map.get` | use the already-checked local (Martin: LGTM) | identical single-threaded |

Dropped: row115 (the warning stays after two restructurings). Dropped after Martin's review: row49 (needed an explicit re-throw; probably not fixable), row53 (same
method as row54), row95 (annotation fix), row153 (true positive). Rules from his review: no checks that
always pass, never `throw new` the exception being avoided, shrink `try` scopes instead of relying on
catching, one case per method, no true positives, no annotation-only fixes.

Row 29 (`DataBuffer.unsignedCompareTo`, "Maybe?") is not included: Martin suggested adding the
annotations first, so it is not a refactoring-only case.
