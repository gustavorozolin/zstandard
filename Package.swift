// swift-tools-version: 5.9
import PackageDescription

// SwiftPM facade for the canonical native implementation kept in
// zstandard_native/src/zstd. The Apple platform packages depend on this
// product instead of carrying another copy of the C sources.
let package = Package(
    name: "zstandard_native",
    platforms: [
        .iOS(.v13),
        .macOS(.v10_15),
    ],
    products: [
        .library(
            name: "zstandard-native",
            targets: ["zstandard_native", "zstandard_ffi"]
        ),
    ],
    targets: [
        .target(
            name: "zstandard_native",
            path: "zstandard_native/src/zstd",
            exclude: [
                "deprecated",
                "dictBuilder",
                "dll",
                "legacy",
                "decompress/huf_decompress_amd64.S",
                "module.modulemap",
            ],
            publicHeadersPath: "include",
            cSettings: [
                .headerSearchPath("."),
                .headerSearchPath("include"),
                // Required when Xcode precompiles zstd.h as a Clang module;
                // internal zstd translation units consume these declarations.
                .define("ZSTD_STATIC_LINKING_ONLY"),
                .define("ZSTD_DISABLE_ASM"),
            ]
        ),
        // Registration calls this bridge to retain the Dart FFI entry points
        // under dead-code stripping without unsafe dependency build flags.
        .target(
            name: "zstandard_ffi",
            dependencies: ["zstandard_native"],
            path: "zstandard_native/apple",
            publicHeadersPath: "include"
        ),
    ]
)
