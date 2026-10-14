"""Offline debug APK fallback using installed SDK tools and cached Kotlin. Does not run AGP/lint or device tests."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-home", type=Path, required=True)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=Path.home() / ".gradle/caches/modules-2/files-2.1")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    project = (root / "app/build.gradle.kts").read_text(encoding="utf-8")
    def number(name):
        return re.search(rf"\b{name}\s*=\s*(\d+)", project).group(1)
    package = re.search(r'applicationId\s*=\s*"([^"]+)"', project).group(1)
    sdk = args.sdk.resolve()
    tools = sdk / "build-tools/35.0.0"
    android = sdk / f"platforms/android-{number('compileSdk')}/android.jar"
    work = root / "app/build/sdk-debug"
    work.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["JAVA_HOME"] = str(args.java_home.resolve())
    env["ARI_DEBUG_SIGN_PASSWORD"] = "android"  # Standard local debug identity only.
    exe = ".exe" if os.name == "nt" else ""
    java = args.java_home / "bin" / ("java" + exe)
    def run(command, **kwargs):
        command = list(map(str, command))
        if os.name == "nt" and command[0].endswith(".bat"):
            command = ["cmd.exe", "/c", *command]
        subprocess.run(command, env=env, check=True, **kwargs)
    def jar(group, module, version=None):
        folder = args.cache / group / module
        if version:
            folder /= version
        files = [p for p in folder.rglob("*.jar") if not p.name.endswith(("-sources.jar", "-javadoc.jar"))]
        if not files:
            parser.error(f"Cached dependency missing: {folder}")
        return sorted(files)[-1]
    stdlib = jar("org.jetbrains.kotlin", "kotlin-stdlib", "2.0.21")
    compiler = [jar("org.jetbrains.kotlin", "kotlin-compiler-embeddable", "2.0.21"), stdlib,
        jar("org.jetbrains.kotlin", "kotlin-script-runtime", "2.0.21"), jar("org.jetbrains.kotlin", "kotlin-daemon-embeddable", "2.0.21"),
        jar("org.jetbrains.intellij.deps", "trove4j"), jar("org.jetbrains", "annotations", "23.0.0"),
        jar("org.jetbrains.kotlinx", "kotlinx-coroutines-core-jvm")]
    ET.register_namespace("android", "http://schemas.android.com/apk/res/android")
    ns = "{http://schemas.android.com/apk/res/android}"
    manifest = ET.parse(root / "app/src/main/AndroidManifest.xml")
    manifest.getroot().set("package", package)
    application = manifest.getroot().find("application")
    application.set(ns + "debuggable", "true")
    debug = ET.parse(root / "app/src/debug/AndroidManifest.xml")
    for child in debug.getroot().find("application"):
        application.append(child)
    manifest_path = work / "AndroidManifest.xml"
    manifest.write(manifest_path, encoding="utf-8", xml_declaration=True)
    resources = work / "resources.zip"
    run([tools / ("aapt2" + exe), "compile", "--dir", root / "app/src/main/res", "-o", resources])
    java_source = work / "generated"
    java_source.mkdir(exist_ok=True)
    resource_apk = work / "resources.ap_"
    run([tools / ("aapt2" + exe), "link", "-I", android, "--manifest", manifest_path, "--java", java_source,
        "--min-sdk-version", number("minSdk"), "--target-sdk-version", number("targetSdk"),
        "--version-code", number("versionCode"), "--version-name", "0.1.0", "-o", resource_apk, resources])
    config = java_source / package.replace(".", "/") / "BuildConfig.java"
    config.parent.mkdir(parents=True, exist_ok=True)
    origin = re.search(r'buildConfigField\("String", "TOUR_ORIGIN", "\\"([^\\]+)\\""\)', project).group(1)
    config.write_text(f'package {package}; public final class BuildConfig {{ public static final boolean DEBUG=true; public static final String TOUR_ORIGIN="{origin}"; }}', encoding="utf-8")
    classes = work / "java-classes"
    classes.mkdir(exist_ok=True)
    run([args.java_home / "bin" / ("javac" + exe), "--release", "17", "-encoding", "UTF-8", "-d", classes, *java_source.rglob("*.java")])
    app_jar = work / "app-classes.jar"
    kotlin_sources = list((root / "app/src/main/java").rglob("*.kt")) + list((root / "app/src/debug/java").rglob("*.kt"))
    run([java, "-cp", os.pathsep.join(map(str, compiler)), "org.jetbrains.kotlin.cli.jvm.K2JVMCompiler",
        "-no-stdlib", "-no-reflect", "-jvm-target", "17", "-classpath", os.pathsep.join(map(str, [android, classes, stdlib])),
        "-d", app_jar, *kotlin_sources])
    with zipfile.ZipFile(app_jar, "a", zipfile.ZIP_DEFLATED) as archive:
        for file in classes.rglob("*.class"):
            archive.write(file, file.relative_to(classes).as_posix())
    dex = work / "dex"
    dex.mkdir(exist_ok=True)
    run([java, "-Xmx2048m", "-cp", tools / "lib/d8.jar", "com.android.tools.r8.D8", "--lib", android,
        "--min-api", number("minSdk"), "--output", dex, app_jar, stdlib])
    unsigned = work / "unsigned.apk"
    with zipfile.ZipFile(resource_apk) as base, zipfile.ZipFile(unsigned, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in base.infolist():
            archive.writestr(item.filename, base.read(item.filename))
        for file in dex.glob("*.dex"):
            archive.write(file, file.name)
        tour = root.parent / "web_api/tour"
        for file in tour.rglob("*"):
            if file.is_file():
                archive.write(file, "assets/tour/" + file.relative_to(tour).as_posix())
    output = root / "app/build/outputs/apk/debug/app-debug.apk"
    output.parent.mkdir(parents=True, exist_ok=True)
    run([tools / ("zipalign" + exe), "-f", "4", unsigned, output])
    keystore = work / "debug.keystore"
    if not keystore.exists():
        run([args.java_home / "bin" / ("keytool" + exe), "-genkeypair", "-keystore", keystore,
            "-storepass:env", "ARI_DEBUG_SIGN_PASSWORD", "-keypass:env", "ARI_DEBUG_SIGN_PASSWORD", "-alias", "androiddebugkey",
            "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000", "-dname", "CN=Android Debug,O=Android,C=US"])
    signer = tools / ("apksigner.bat" if os.name == "nt" else "apksigner")
    run([signer, "sign", "--ks", keystore, "--ks-key-alias", "androiddebugkey", "--ks-pass", "env:ARI_DEBUG_SIGN_PASSWORD",
        "--key-pass", "env:ARI_DEBUG_SIGN_PASSWORD", output])
    run([signer, "verify", "--verbose", output])
    run([tools / ("zipalign" + exe), "-c", "4", output])
    print(f"SDK DEBUG APK: {output} ({output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
