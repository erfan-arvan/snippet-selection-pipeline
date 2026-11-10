# Refactorings for the included rows

One patch per included row of the review spreadsheet (Martin's 5 inclusions + 4 suggested from his
criteria), each against the pinned commit, meant to make the checker accept the method **without
annotations and without changing behaviour**. `submit_check_refactorings.sh` runs the checker on the
original (control) and on the refactored method and reports whether the warning goes away.

| case | method | checker / warning | refactoring | behaviour |
|---|---|---|---|---|
| row13 | dubbo `ReflectUtils.getGenericClass` | index, `[0]` and `[i]` | explicit length checks before both array accesses, throwing the `ArrayIndexOutOfBoundsException` the access threw, inside the same `try` so the `catch` still wraps it in the same `IllegalArgumentException` | same; only the inner exception's stack trace differs |
| row16 | dubbo `UrlUtils.isMatchGlobPattern` | index, `substring(i + 1)` | branch `i == 0` becomes `i == 0 && pattern.length() > 1` and uses `substring(1)` | same: in that branch the length is always > 1 (i == 0 is a valid index and the previous branch handled length 1) |
| row49 | ghidra `TerminalLayoutModel.getLayout` | index, `layouts.get(index.intValue())` | int local, explicit bounds check against `layouts.size()`, `signum()` instead of `compareTo(ZERO)` | same, including the exception (same type and message) when `numIndexes` exceeds `layouts.size()` |
| row53 | ghidra `MachHeaderFlags.getFlags` | nullness, unboxing | `value != null &&` before the unboxing | same: null used to throw an NPE that the surrounding `catch` ignored |
| row54 | ghidra `MachHeaderFlags.getFlags` | index, `substring("MH_".length())` | `field.getName()` stored in a local, checked and used | same |
| row90 | ghidra `InstructionUtils.getFormatedInstructionObjects` | nullness, `toArray` | `set.toArray(new String[set.size()])` | same |
| row95 | ghidra `ByteArray.get` | index, negative index | explicit `index < 0` check throwing the same `ArrayIndexOutOfBoundsException` | same |
| row114 | hudi `HoodieTableFileSystemView.fetchAllStoredFileGroups` | nullness, second `map.get` | use the already-checked local `fileGroups` | same single-threaded; only differs if another thread changes the map between the two `get` calls |
| row153 | netty `DomainWildcardMappingBuilder.normalizeHostName` | index, `charAt(0)` after reassignment | explicit `isEmpty()` check on the normalized value, throwing `StringIndexOutOfBoundsException` | same exception type; message text matches JDK 17. NOTE: this case may be a (rare) true positive: `normalize()` can return "" for some IDN input |

Exception messages copy the JDK 11+ format (`Index N out of bounds for length M`).

Row 29 (`DataBuffer.unsignedCompareTo`, "Maybe?") is not included: Martin suggested adding the
annotations first, so it is not a refactoring-only case.
