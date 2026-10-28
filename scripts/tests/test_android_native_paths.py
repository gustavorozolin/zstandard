"""Build the Android plugin from a long Git-cache path with a separate consumer.

Requires Gradle 8.14 on PATH (or GRADLE_BIN), a JDK and ANDROID_HOME containing
NDK 27.0.12077973, CMake 3.22.1, platform 34 and build-tools 34.0.0.
Run directly with Python on Windows, macOS or Linux; no Flutter SDK is needed.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


REPOSITORY = Path(__file__).resolve().parents[2]


def main():
    gradle = os.environ.get('GRADLE_BIN') or shutil.which('gradle')
    sdk = os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT')
    if not gradle or not sdk:
        raise SystemExit('Gradle and ANDROID_HOME are required for this build test.')

    with tempfile.TemporaryDirectory(prefix='zstd-paths-') as temporary:
        root = Path(temporary).resolve()
        # Deliberately keep the plugin and native dependency outside the app.
        # A Git dependency adds a 40-character commit hash to the plugin path.
        cache = root / 'Pub Cache'
        plugin = cache / 'git' / ('zstandard-' + 'a' * 40) / 'zstandard_android'
        source = REPOSITORY / 'zstandard_android'
        for directory in ('android', 'zstd_build'):
            shutil.copytree(source / directory, plugin / directory,
                            ignore=shutil.ignore_patterns(
                                '.cxx', '.gradle', 'build', 'local.properties'))
        native = cache / 'hosted/pub.dev/zstandard_native-1.5.3'
        shutil.copytree(REPOSITORY / 'zstandard_native/src', native / 'src')

        app = root / 'consumer'
        android = app / 'android'
        android.mkdir(parents=True)
        config = app / '.dart_tool/package_config.json'
        config.parent.mkdir()
        config.write_text(json.dumps({
            'configVersion': 2,
            'packages': [{'name': 'zstandard_native', 'rootUri': native.as_uri()}],
        }), encoding='utf-8')
        (android / 'settings.gradle').write_text('''pluginManagement {
    repositories { google(); mavenCentral(); gradlePluginPortal() }
}
plugins {
    id 'com.android.library' version '8.11.1' apply false
    id 'org.jetbrains.kotlin.android' version '2.2.20' apply false
}
rootProject.name = 'native-path-consumer'
include ':zstandard_android'
project(':zstandard_android').projectDir = file(
    '../../Pub Cache/git/zstandard-''' + 'a' * 40 + '''/zstandard_android/android')
''', encoding='utf-8')
        (android / 'build.gradle').write_text('''subprojects {
    layout.buildDirectory.set(new File(rootProject.projectDir.parentFile, "build/${project.name}"))
    afterEvaluate {
        android.ndkVersion = '27.0.12077973'
        android.externalNativeBuild.cmake.version = '3.22.1'
        android.defaultConfig.ndk.abiFilters.clear()
        android.defaultConfig.ndk.abiFilters.add('arm64-v8a')
    }
}
''', encoding='utf-8')
        (android / 'local.properties').write_text(
            'sdk.dir=' + Path(sdk).resolve().as_posix() + '\n', encoding='utf-8')
        (android / 'gradle.properties').write_text(
            'org.gradle.jvmargs=-Xmx2g\norg.gradle.workers.max=4\n', encoding='utf-8')

        subprocess.run([
            gradle, '--no-daemon', '--console=plain', '-p', str(android),
            ':zstandard_android:externalNativeBuildRelease',
            ':zstandard_android:externalNativeBuildDebug',
        ], check=True, timeout=900)

        staging = android / '.cxx/zstd'
        plans = list(staging.glob('*/**/build.ninja'))
        assert len(plans) == 2, f'Expected debug/release Ninja plans under {staging}: {plans}'
        assert not (plugin / 'android/.cxx').exists(), 'Build must not stage in the Git cache'
        object_lengths = []
        for plan in plans:
            objects = []
            for line in plan.read_text(encoding='utf-8').splitlines():
                if line.startswith('build ') and ': C_COMPILER__zstandard_android_' in line:
                    relative = line[6:].split(': C_COMPILER__zstandard_android_', 1)[0]
                    relative = relative.replace('$ ', ' ').replace('$:', ':').replace('$$', '$')
                    obj = plan.parent / relative
                    assert obj.is_file(), f'Object was not built: {obj}'
                    objects.append(obj)
            assert len(objects) >= 26, f'Expected zstd objects in {plan}'
            object_lengths.extend(len(str(obj)) for obj in objects)
            commands = json.loads((plan.parent / 'compile_commands.json').read_text(encoding='utf-8'))
            native_files = [Path(item['file']).resolve() for item in commands
                            if 'zstandard_android_test_bridge.c' not in item['file']]
            assert all(path.is_relative_to(native / 'src/zstd') for path in native_files)

        assert max(object_lengths) <= 240, f'Object paths exceed the limit: {max(object_lengths)}'
        libraries = list((app / 'build/zstandard_android/intermediates/cxx').glob(
            '**/obj/arm64-v8a/libzstandard_android.so'))
        assert len(libraries) == 2, f'Missing debug/release libraries: {libraries}'
        print(f'PASS: Android arm64 debug/release from Git-cache layout; '
              f'{len(object_lengths)} objects, longest path {max(object_lengths)} characters.')


if __name__ == '__main__':
    main()
