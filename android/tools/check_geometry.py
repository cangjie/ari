"""Compile and run pure geofence tests from an existing offline Kotlin cache (not an APK build)."""
import argparse
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-home", type=Path, required=True)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=Path.home() / ".gradle/caches/modules-2/files-2.1")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    java = args.java_home / "bin" / ("java.exe" if os.name == "nt" else "java")
    def jar(group, module, version=None):
        folder = args.cache / group / module
        if version:
            folder /= version
        matches = [p for p in folder.rglob("*.jar") if not p.name.endswith(("-sources.jar", "-javadoc.jar"))]
        if not matches:
            parser.error(f"Cached dependency missing: {folder}")
        return sorted(matches)[-1]
    stdlib = jar("org.jetbrains.kotlin", "kotlin-stdlib", "2.0.21")
    junit = jar("junit", "junit", "4.13.2")
    hamcrest = jar("org.hamcrest", "hamcrest-core", "1.3")
    compiler = [jar("org.jetbrains.kotlin", "kotlin-compiler-embeddable", "2.0.21"), stdlib,
        jar("org.jetbrains.kotlin", "kotlin-script-runtime", "2.0.21"),
        jar("org.jetbrains.kotlin", "kotlin-daemon-embeddable", "2.0.21"),
        jar("org.jetbrains.intellij.deps", "trove4j"), jar("org.jetbrains", "annotations", "23.0.0"),
        jar("org.jetbrains.kotlinx", "kotlinx-coroutines-core-jvm")]
    android = args.sdk / "platforms/android-35/android.jar"
    output = root / "app/build/offline-check/geofence-tests.jar"
    output.parent.mkdir(parents=True, exist_ok=True)
    production = root / "app/src/main/java/top/snowmeet/tour/tour"
    test = root / "app/src/test/java/top/snowmeet/tour/tour"
    java_classes = output.parent / "json-classes"
    java_classes.mkdir(exist_ok=True)
    annotation_dir = output.parent / "annotation-src"
    annotations = {
        "android/compat/annotation/UnsupportedAppUsage.java": "package android.compat.annotation; public @interface UnsupportedAppUsage {}",
        "android/annotation/SystemApi.java": "package android.annotation; public @interface SystemApi { Client client() default Client.MODULE_LIBRARIES; enum Client {MODULE_LIBRARIES} }",
        "libcore/util/NonNull.java": "package libcore.util; @java.lang.annotation.Target({java.lang.annotation.ElementType.TYPE_USE}) public @interface NonNull {}",
        "libcore/util/Nullable.java": "package libcore.util; @java.lang.annotation.Target({java.lang.annotation.ElementType.TYPE_USE}) public @interface Nullable {}",
    }
    annotation_files = []
    for name, content in annotations.items():
        path = annotation_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        annotation_files.append(path)
    json_sources = list((args.sdk / "sources/android-35/org/json").glob("*.java"))
    if not json_sources:
        parser.error("Android API 35 JSON sources missing")
    javac = args.java_home / "bin" / ("javac.exe" if os.name == "nt" else "javac")
    result = subprocess.run([str(javac), "-encoding", "UTF-8", "-d", str(java_classes), *map(str, annotation_files + json_sources)])
    if result.returncode:
        raise SystemExit(result.returncode)
    command = [str(java), "-cp", os.pathsep.join(map(str, compiler)), "org.jetbrains.kotlin.cli.jvm.K2JVMCompiler",
        "-no-stdlib", "-no-reflect", "-jvm-target", "17", "-classpath", os.pathsep.join(map(str, [java_classes, android, stdlib, junit, hamcrest])),
        "-d", str(output), str(production / "TourData.kt"), str(production / "GeofenceEngine.kt"), *map(str, test.glob("*.kt"))]
    result = subprocess.run(command)
    if result.returncode:
        raise SystemExit(result.returncode)
    raise SystemExit(subprocess.run([str(java), "-cp", os.pathsep.join(map(str, [output, java_classes, android, stdlib, junit, hamcrest])),
        "org.junit.runner.JUnitCore", "top.snowmeet.tour.tour.GeofenceEngineTest", "top.snowmeet.tour.tour.TourDataTest",
        "top.snowmeet.tour.tour.GeofenceFixtureTest"], cwd=root / "app").returncode)


if __name__ == "__main__":
    main()
