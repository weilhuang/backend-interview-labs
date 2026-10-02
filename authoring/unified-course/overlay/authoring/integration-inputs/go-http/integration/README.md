# Additive integration proposal

Preserve the reviewed R2 root. This source is an overlay proposal, not a complete course and not a replacement for `go-course/section-info.yaml`.

1. Copy only the new `go-course/http` subtree and `materials/go-http` into a new unified candidate
2. Append `http` to existing Go section content without losing `core`; append the two tasks in `task-map.json` to the true authoring model/course-map
3. Add the two exact Gradle project mappings to generated settings; apply `materials/go-http/course.gradle` once from the root
4. Add all public task files and shared course material to the unified additional-file inventory; generate one course-info.yaml with UTF-16 placeholders from each task-info.yaml
5. Keep JDK21 / JUnit5.11.4 / launcher1.11.4. Produce and verify final module strict locks under the unified lock owner. No fabricated/copied lock is supplied as if it were newly resolved
6. Final root Go wrapper must require explicit GO_MODULE_CACHE (or `-PgoModuleCache`) for the Gin dependencies; prewarm with the pinned module checksums before checking. Java test processes stay offline. Resolve-And-Lock is preparation, never a hidden test step
7. Add both projects to existing aggregate test/unitTest via the true map. Run source/model/metadata tests, then Java bridges and full owned-process HTTP tests for the final assembled source
8. Native Academy import/Check remains NOT_RUN until actually executed. Do not publish, add Actions, install plugins or alter visibility as part of this proposal

The Python verifier runs copies with per-variant working roots and a shared owned Go cache; it never overwrites the authored source or writes into reviewed R2. Scope includes ordinary JSON/HTTP1 loopback examples, not Docker, DB/GORM, TLS, production auth or HTTP3.
