import Darwin
import zstandard_ffi
import zstandard_native

// Match Swift plugin registration. All zstd calls below go through dlsym so
// they cannot themselves keep the FFI entry points alive during linking.
zstandard_ffi_retain_symbols()

let process = dlopen(nil, RTLD_NOW)!
let names = [
    "ZSTD_compress", "ZSTD_decompress", "ZSTD_compressBound", "ZSTD_isError",
    "ZSTD_getFrameContentSize", "ZSTD_createDStream", "ZSTD_initDStream",
    "ZSTD_decompressStream", "ZSTD_freeDStream", "ZSTD_DStreamOutSize",
]
for name in names {
    if dlsym(process, name) == nil {
        fputs("Missing FFI export: \(name)\n", stderr)
        exit(1)
    }
}

typealias Compress = @convention(c) (
    UnsafeMutableRawPointer?, UInt, UnsafeRawPointer?, UInt, Int32
) -> UInt
typealias Decompress = @convention(c) (
    UnsafeMutableRawPointer?, UInt, UnsafeRawPointer?, UInt
) -> UInt
typealias CreateStream = @convention(c) () -> UnsafeMutableRawPointer?
typealias IsError = @convention(c) (UInt) -> UInt32
typealias StreamOperation = @convention(c) (UnsafeMutableRawPointer?) -> UInt
typealias DecompressStream = @convention(c) (
    UnsafeMutableRawPointer?, UnsafeMutablePointer<ZSTD_outBuffer>?,
    UnsafeMutablePointer<ZSTD_inBuffer>?
) -> UInt

let compress = unsafeBitCast(dlsym(process, "ZSTD_compress")!, to: Compress.self)
let decompress = unsafeBitCast(dlsym(process, "ZSTD_decompress")!, to: Decompress.self)
let createStream = unsafeBitCast(dlsym(process, "ZSTD_createDStream")!, to: CreateStream.self)
let isError = unsafeBitCast(dlsym(process, "ZSTD_isError")!, to: IsError.self)
let initStream = unsafeBitCast(dlsym(process, "ZSTD_initDStream")!, to: StreamOperation.self)
let freeStream = unsafeBitCast(dlsym(process, "ZSTD_freeDStream")!, to: StreamOperation.self)
let decompressStream = unsafeBitCast(
    dlsym(process, "ZSTD_decompressStream")!, to: DecompressStream.self
)

let input = Array(String(repeating: "SwiftPM FFI release regression ", count: 8).utf8)
var compressed = [UInt8](repeating: 0, count: 1024)
var output = [UInt8](repeating: 0, count: input.count)
let compressedSize = compressed.withUnsafeMutableBytes { dst in
    input.withUnsafeBytes { src in
        compress(dst.baseAddress, UInt(dst.count), src.baseAddress, UInt(src.count), 3)
    }
}
precondition(isError(compressedSize) == 0 && compressedSize <= compressed.count)
let outputSize = output.withUnsafeMutableBytes { dst in
    compressed.withUnsafeBytes { src in
        decompress(dst.baseAddress, UInt(dst.count), src.baseAddress, compressedSize)
    }
}
precondition(outputSize == input.count && output == input)

let stream = createStream()!
precondition(isError(initStream(stream)) == 0)
output = [UInt8](repeating: 0, count: input.count)
output.withUnsafeMutableBytes { dst in
    compressed.withUnsafeBytes { src in
        var source = ZSTD_inBuffer(src: src.baseAddress, size: Int(compressedSize), pos: 0)
        var destination = ZSTD_outBuffer(dst: dst.baseAddress, size: dst.count, pos: 0)
        precondition(decompressStream(stream, &destination, &source) == 0)
        precondition(source.pos == compressedSize && destination.pos == input.count)
    }
}
precondition(freeStream(stream) == 0 && output == input)
print("FFI release probe passed: 10 exports, compression, decompression, streaming.")
