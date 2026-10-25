import 'dart:io';

/// Prepare matched, unpublished candidate dependencies for CI path-layout tests.
/// This never claims that the candidate was downloaded from pub.dev.
void main(List<String> arguments) {
  try {
    if (arguments.length != 1 ||
        !const {'workspace', 'pub-cache'}.contains(arguments.single)) {
      throw const CandidateSourceFailure('invalid-source');
    }
    final environmentPath = Platform.environment['GITHUB_ENV'];
    final temporaryPath = Platform.environment['RUNNER_TEMP'];
    if (environmentPath == null ||
        temporaryPath == null ||
        !File(environmentPath).existsSync()) {
      throw const CandidateSourceFailure('missing-ci-environment');
    }
    final root = Directory(Directory.current.resolveSymbolicLinksSync());
    final temporary = Directory(
      Directory(temporaryPath).resolveSymbolicLinksSync(),
    );
    if ([
      root.path,
      temporary.path,
      environmentPath,
    ].any((value) => value.contains(RegExp(r'[\r\n]')))) {
      throw const CandidateSourceFailure('unsafe-runtime-path');
    }
    final native = Directory('${root.path}/zstandard_native');
    if (FileSystemEntity.typeSync(native.path, followLinks: false) !=
        FileSystemEntityType.directory) {
      throw const CandidateSourceFailure('missing-native-candidate');
    }
    final tracked = _trackedFiles(root);
    final version = _version(
      File('${native.path}/pubspec.yaml').readAsStringSync(),
    );
    _requireCleanNative(root);
    if (arguments.single == 'workspace') {
      _export(environmentPath, native.path, root.path);
      return;
    }

    final stage = temporary.createTempSync('zstandard-candidate-cache-');
    final cached = Directory(
      '${stage.path}/pub-cache/hosted/pub.dev/zstandard_native-$version',
    );
    final swiftRoot = Directory('${stage.path}/swift-root');
    final hidden = Directory('${stage.path}/workspace-native');
    var moved = false;
    try {
      for (final relative in tracked) {
        final source = File('${root.path}/$relative');
        if (relative == 'Package.swift') {
          _copy(source, File('${swiftRoot.path}/Package.swift'));
        } else {
          final nativeRelative = relative.substring('zstandard_native/'.length);
          _copy(source, File('${cached.path}/$nativeRelative'));
          _copy(source, File('${swiftRoot.path}/$relative'));
        }
      }
      _requireCleanNative(root);
      native.renameSync(hidden.path);
      moved = true;
      _export(environmentPath, cached.path, swiftRoot.path);
      File(environmentPath).writeAsStringSync(
        'ZSTANDARD_NATIVE_ORIGINAL_PATH=${hidden.path}\n',
        mode: FileMode.append,
      );
    } catch (_) {
      // Restore authored/untracked workspace material before retiring our copies.
      // A failed restore retains the stage instead of deleting the original.
      if (moved) hidden.renameSync(native.path);
      stage.deleteSync(recursive: true);
      rethrow;
    }
  } on CandidateSourceFailure catch (error) {
    stderr.writeln('Native candidate preparation failed: ${error.code}.');
    exitCode = 1;
  } catch (_) {
    stderr.writeln(
      'Native candidate preparation failed: filesystem-or-tool-error.',
    );
    exitCode = 1;
  }
}

List<String> _trackedFiles(Directory root) {
  final result = Process.runSync('git', [
    'ls-files',
    '-z',
    '--',
    'zstandard_native',
    'Package.swift',
  ], workingDirectory: root.path);
  if (result.exitCode != 0) {
    throw const CandidateSourceFailure('git-source-unavailable');
  }
  final files = (result.stdout as String).split('\u0000')
    ..removeWhere((file) => file.isEmpty);
  if (!files.contains('zstandard_native/pubspec.yaml') ||
      !files.contains('Package.swift')) {
    throw const CandidateSourceFailure('incomplete-native-candidate');
  }
  for (final relative in files) {
    final file = File('${root.path}/$relative');
    if (FileSystemEntity.typeSync(file.path, followLinks: false) !=
            FileSystemEntityType.file ||
        !file.resolveSymbolicLinksSync().startsWith(
          '${root.path}${Platform.pathSeparator}',
        )) {
      throw const CandidateSourceFailure('unsafe-candidate-path');
    }
  }
  return files;
}

String _version(String manifest) {
  final matches = RegExp(
    r'^version:[ \t]*(\S+)[ \t]*(?:#.*)?$',
    multiLine: true,
  ).allMatches(manifest).toList();
  if (matches.length != 1) {
    throw const CandidateSourceFailure('invalid-candidate-version');
  }
  var value = matches.single.group(1)!;
  if ((value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))) {
    value = value.substring(1, value.length - 1);
  }
  if (value.length > 100 ||
      !RegExp(
        r'^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$',
      ).hasMatch(value)) {
    throw const CandidateSourceFailure('invalid-candidate-version');
  }
  return value;
}

void _requireCleanNative(Directory root) {
  final result = Process.runSync('git', [
    'diff',
    '--quiet',
    '--',
    'zstandard_native',
    'Package.swift',
  ], workingDirectory: root.path);
  if (result.exitCode != 0) {
    throw const CandidateSourceFailure('native-source-drift');
  }
}

void _copy(File source, File destination) {
  destination.parent.createSync(recursive: true);
  source.copySync(destination.path);
}

void _export(String environmentPath, String dartPath, String swiftPath) {
  File(environmentPath).writeAsStringSync(
    'ZSTANDARD_NATIVE_DART_PATH=$dartPath\nZSTANDARD_NATIVE_PACKAGE_PATH=$swiftPath\n',
    mode: FileMode.append,
  );
}

class CandidateSourceFailure implements Exception {
  const CandidateSourceFailure(this.code);
  final String code;
}
