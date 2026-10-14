"""Local Android build helper. Does not install tools or deploy anything."""
import argparse
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-home", type=Path)
    parser.add_argument("--sdk", type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("tasks", nargs="*", default=[":app:testDebugUnitTest", ":app:assembleDebug", ":app:lintDebug"])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    java = args.java_home or (Path(env["JAVA_HOME"]) if env.get("JAVA_HOME") else None)
    if java:
        executable = java / "bin" / ("java.exe" if os.name == "nt" else "java")
        if not executable.is_file():
            parser.error(f"Java not found: {executable}")
        env["JAVA_HOME"] = str(java.resolve())
    sdk = args.sdk or (Path(env["ANDROID_HOME"]) if env.get("ANDROID_HOME") else None)
    if sdk:
        if not (sdk / "platforms" / "android-35" / "android.jar").is_file():
            parser.error(f"API 35 platform not found under: {sdk}")
        (root / "local.properties").write_text("sdk.dir=" + sdk.resolve().as_posix() + "\n", encoding="utf-8")
    env["GRADLE_USER_HOME"] = str(root / "build" / "gradle-home")
    wrapper = root / ("gradlew.bat" if os.name == "nt" else "gradlew")
    command = (["cmd.exe", "/c", str(wrapper)] if os.name == "nt" else ["sh", str(wrapper)])
    command += args.tasks + ["--no-daemon", "--console=plain"]
    if args.offline:
        command.append("--offline")
    raise SystemExit(subprocess.run(command, cwd=root, env=env).returncode)


if __name__ == "__main__":
    main()
