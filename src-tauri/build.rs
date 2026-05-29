fn ensure_sidecar_stub() {
    let sidecar = std::path::Path::new("binaries/fluxion-server-aarch64-apple-darwin");
    if sidecar.exists() {
        return;
    }
    let _ = std::fs::create_dir_all("binaries");
    let _ = std::fs::write(sidecar, "#!/bin/sh\nexit 0\n");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if let Ok(metadata) = std::fs::metadata(sidecar) {
            let mut permissions = metadata.permissions();
            permissions.set_mode(0o755);
            let _ = std::fs::set_permissions(sidecar, permissions);
        }
    }
}

fn main() {
    ensure_sidecar_stub();
    let build_id = std::env::var("FLUXION_BUILD_ID").unwrap_or_else(|_| "dev".to_string());
    println!("cargo:rustc-env=FLUXION_BUILD_ID={build_id}");

    let sparkle_public = std::env::var("FLUXION_SPARKLE_PUBLIC_ED_KEY").unwrap_or_else(|_| {
        std::fs::read_to_string("../assets/macos/sparkle_public_ed_key.txt")
            .unwrap_or_default()
    });
    let sparkle_public = sparkle_public
        .lines()
        .find(|line| {
            let trimmed = line.trim();
            !trimmed.is_empty() && !trimmed.starts_with('#')
        })
        .unwrap_or("")
        .trim()
        .to_string();
    println!("cargo:rustc-env=FLUXION_SPARKLE_PUBLIC_ED_KEY={sparkle_public}");

    tauri_build::build()
}
