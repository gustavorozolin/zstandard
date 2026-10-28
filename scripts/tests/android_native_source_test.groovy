// Run from the repository root with a JDK and an installed Gradle distribution:
// java -cp "<gradle-home>/lib/*" groovy.ui.GroovyMain scripts/tests/android_native_source_test.groovy
// The same fixtures run on Windows, macOS and Linux using the host's file URIs.
import groovy.json.JsonOutput
import java.nio.file.Files
import org.gradle.api.GradleException

def binding = new Binding([ext: [:]])
new GroovyShell(getClass().classLoader, binding).evaluate(
    new File('zstandard_android/android/resolve_zstd.gradle'))
def resolve = binding.getVariable('ext').resolveZstdRoot
File fixture = Files.createTempDirectory('zstd-source-test-').toFile().canonicalFile
int checks = 0

def createSource = { String path ->
    File root = new File(fixture, "${path}/src/zstd")
    ['common', 'compress', 'decompress'].each { new File(root, it).mkdirs() }
    new File(root, 'zstd.h').text = '// fixture'
    return root.canonicalFile
}
def writeConfig = { File app, List packages ->
    File config = new File(app, '.dart_tool/package_config.json')
    config.parentFile.mkdirs()
    config.setText(JsonOutput.toJson([configVersion: 2, packages: packages]), 'UTF-8')
    return config
}
def expectFailure = { String text, Closure action ->
    try {
        action()
        assert false: "Expected failure containing ${text}"
    } catch (GradleException error) {
        assert error.message.contains(text): error.message
    }
    checks++
}

try {
    File app = new File(fixture, 'consumer')
    File android = new File(app, 'android')
    android.mkdirs()
    File wanted = createSource('cache with spaces/João+%/hosted/pub.dev/zstandard_native-1.5.3')
    // Neither another cached version nor a repository sibling may win.
    createSource('cache with spaces/João+%/hosted/pub.dev/zstandard_native-1.5.0')
    createSource('zstandard_native')
    def entry = [rootUri: wanted.parentFile.parentFile.toURI().toASCIIString(), name: 'zstandard_native']
    writeConfig(app, [entry])
    assert resolve(android) == wanted
    checks++

    // A relative URI is based at .dart_tool, not the Android/plugin directory.
    File relative = createSource('consumer/vendor/native with spaces')
    writeConfig(app, [[name: 'zstandard_native', rootUri: '../vendor/native%20with%20spaces']])
    assert resolve(android) == relative
    checks++

    File workspace = new File(fixture, 'workspace')
    File moduleAndroid = new File(workspace, 'apps/mobile/.android')
    moduleAndroid.mkdirs()
    writeConfig(workspace, [entry])
    assert resolve(moduleAndroid) == wanted
    checks++

    // The closest package configuration takes precedence over workspace parents.
    File nestedApp = moduleAndroid.parentFile
    writeConfig(nestedApp, [[name: 'zstandard_native', rootUri: relative.parentFile.parentFile.toURI().toASCIIString()]])
    assert resolve(moduleAndroid) == relative
    checks++

    File orphanAndroid = new File(fixture, 'orphan/android')
    orphanAndroid.mkdirs()
    expectFailure('package_config.json not found') { resolve(orphanAndroid) }

    writeConfig(app, [[name: 'another_package', rootUri: entry.rootUri]])
    expectFailure('zstandard_native is missing') { resolve(android) }
    writeConfig(app, [[name: 'zstandard_native', rootUri: '']])
    expectFailure('zstandard_native is missing') { resolve(android) }

    writeConfig(app, [[name: 'zstandard_native', rootUri: 'https://example.invalid/native']])
    expectFailure('invalid zstandard_native rootUri') { resolve(android) }

    writeConfig(app, [[name: 'zstandard_native', rootUri: '../missing']])
    expectFailure('zstd source not found') { resolve(android) }

    File incomplete = createSource('incomplete')
    assert new File(incomplete, 'compress').delete()
    writeConfig(app, [[name: 'zstandard_native', rootUri: incomplete.parentFile.parentFile.toURI().toASCIIString()]])
    expectFailure('zstd source not found') { resolve(android) }

    println "PASS: ${checks} Android native source resolution checks on ${System.getProperty('os.name')}"
} finally {
    fixture.deleteDir()
}
