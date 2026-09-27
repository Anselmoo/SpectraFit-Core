fn main() {
    // Link Apple Accelerate on macOS so vvexp (vForce) is available.
    // On all other platforms the scalar fallback in math_backend.rs is used.
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("macos") {
        println!("cargo:rustc-link-lib=framework=Accelerate");
    }
}
