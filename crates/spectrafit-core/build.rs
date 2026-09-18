// build.rs — link-arg shim for PyO3 cdylib on macOS
//
// On macOS, Python extension modules (.so/.dylib) must allow undefined
// symbols at link time — they are resolved at runtime when Python loads
// the module.  Without this flag the linker refuses to produce the dylib
// because it cannot find the CPython symbols (Py_None, PyArg_*, etc.).
//
// maturin adds this flag automatically, but plain `cargo build` does not.
// Emitting `cargo:rustc-cdylib-link-arg` here applies it to *this* crate's
// cdylib output and makes `cargo build -p spectrafit-core` succeed on macOS.

fn main() {
    #[cfg(target_os = "macos")]
    {
        println!("cargo:rustc-cdylib-link-arg=-undefined");
        println!("cargo:rustc-cdylib-link-arg=dynamic_lookup");
    }
}
