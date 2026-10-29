#include "zstandard_ffi.h"
#include <zstd.h>

typedef void (*ZstandardFFISymbol)(void);

void zstandard_ffi_retain_symbols(void) {
    static ZstandardFFISymbol const symbols[] = {
        (ZstandardFFISymbol)ZSTD_compress,
        (ZstandardFFISymbol)ZSTD_decompress,
        (ZstandardFFISymbol)ZSTD_compressBound,
        (ZstandardFFISymbol)ZSTD_isError,
        (ZstandardFFISymbol)ZSTD_getFrameContentSize,
        (ZstandardFFISymbol)ZSTD_createDStream,
        (ZstandardFFISymbol)ZSTD_initDStream,
        (ZstandardFFISymbol)ZSTD_decompressStream,
        (ZstandardFFISymbol)ZSTD_freeDStream,
        (ZstandardFFISymbol)ZSTD_DStreamOutSize,
    };
    // The volatile access keeps the references observable under optimization.
    // A normal call from Swift registration roots the table for the linker.
    ZstandardFFISymbol const *volatile retained = symbols;
    (void)retained;
}
