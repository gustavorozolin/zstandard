#ifndef ZSTANDARD_FFI_H
#define ZSTANDARD_FFI_H

#ifdef __cplusplus
extern "C" {
#endif

/* Call during plugin registration to preserve Dart FFI entry points. */
void zstandard_ffi_retain_symbols(void);

#ifdef __cplusplus
}
#endif

#endif
