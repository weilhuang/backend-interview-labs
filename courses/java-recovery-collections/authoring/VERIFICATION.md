# Pilot verification record

Checked 2026-09-30 in the dot cloud filesystem. This record is intentionally separated from future CI and Academy UI evidence.

## Actually executed and passed

- 12 author tasks, 4 lessons, 20 UTF-16 answer placeholder spans: YAML hierarchy, referenced files, duplicate-key detection, visibility conventions, placeholder ranges and allowed fields, pinned wrapper checksum
- Real OpenJDK javac compiler module: Java source17 / bytecode17, UTF-8, JUnit Platform Console 1.11.4
- 65/65 JUnit tests passed against reference implementations (53 hidden contract tests plus 12 visible examples)
- Every one of 12 untouched student implementations compiled and failed tests as expected; all TODO regions were materialized from metadata
- Every one of 12 deliberately incorrect variants compiled and was rejected by the tests
- 12 independently varied correct implementations passed those same tests (including alternative dedup, snapshot, comparator, eviction and array-shift approaches)
- Deliberate nonterminating HashIndex implementation: real JUnit TimeoutException after 250ms; process exited with one failed test rather than hanging
- Plain learner copy materialized outside author root: 12 Java implementation files, 20 TODO bodies, no authoring/instructor directories, no course-info.yaml. This is a plain Gradle exercise copy, not an Academy archive
- Python scripts compile; Gradle wrapper binary SHA-256 matches the pinned official template artifact

Machine-readable counts and compiler flags: verification-report.json. Reproduction: see ../README.md. Full ephemeral compile/test logs reside under build/verification after the script runs; they are not part of the learner course or repository deliverable.

## Limits and not-yet-run gates

- Cloud runtime: OpenJDK 21.0.12.1+1-1-deb13u1-Debian. It has the jdk.compiler module but lacks the javac launcher and ct.sym. `--release 17` fails in this stripped runtime. Therefore checks explicitly used `-source 17 -target 17`; they do **not** establish JDK17 API compatibility
- Real Gradle wrapper build/test was not run during this record. CI is configured to run real Gradle and `--release 17` on full Temurin17 and21, but a configured workflow is not proof of a successful CI run
- IntelliJ IDEA 2026.1.5 / matching Academy plugin import, Check button, course preview, archive export, clean re-import and answer-leak audit have not been run
- No claim of release-ready Academy learner archive. Source tree and ordinary zip are not interchangeable with a validated plugin-generated archive
- Behavior tests do not formally prove big-O complexity, constant-time operations, security, or concurrency safety. Current tasks are single-threaded; manual source/rubric review covers these distinctions
- Negative variants are a finite regression suite, not a comprehensive mutation-score measurement

## Before calling this a learner release

1. On a full JDK, run wrapper tests and verifier without source-target fallback; retain exact vendor/patch, Gradle output and CI commit
2. In the exact target IDE/plugin pair, confirm all12 tasks appear in order and all20 answer placeholders appear correctly
3. In learner preview, verify an empty solution fails, an intentional wrong solution fails, a corrected solution passes, and visible example tests can be edited/run
4. Export using Academy, inspect learner contents for unintended author/answer files, and re-import the actual archive into a fresh location
5. Record plugin version and screenshots for the above; only then label the learner archive validated
