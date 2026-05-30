//! Fluxion Tauri shell: spawns the packaged API sidecar and hosts the UI in a WebView.

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde::Deserialize;
use tauri::{AppHandle, Emitter, Manager, RunEvent};
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

const APP_NAME: &str = "Fluxion";
const APP_LABEL: &str = "io.fluxion.local";
const DEFAULT_HOST: &str = "127.0.0.1";
const DEFAULT_PORT: u16 = 9000;

#[derive(Default)]
struct BackendState {
    child: Mutex<Option<CommandChild>>,
}

#[derive(Debug, Deserialize)]
struct HealthPayload {
    status: String,
    app: Option<String>,
    packaged: Option<bool>,
    version: Option<String>,
    build_id: Option<String>,
}

fn app_version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

fn build_id() -> &'static str {
    env!("FLUXION_BUILD_ID")
}

fn data_dir() -> PathBuf {
    dirs::home_dir()
        .expect("home directory")
        .join("Library")
        .join("Application Support")
        .join(APP_NAME)
        .join("data")
}

fn service_url() -> String {
    format!("http://{DEFAULT_HOST}:{DEFAULT_PORT}")
}

fn health_url() -> String {
    format!("{}/api/health", service_url())
}

fn bootout_legacy_launch_agent() {
    #[cfg(target_os = "macos")]
    {
        let uid = std::process::Command::new("id")
            .args(["-u"])
            .output()
            .ok()
            .and_then(|output| String::from_utf8(output.stdout).ok())
            .map(|value| value.trim().to_string())
            .unwrap_or_else(|| "501".to_string());
        let plist = dirs::home_dir()
            .map(|home| {
                home.join("Library")
                    .join("LaunchAgents")
                    .join(format!("{APP_LABEL}.plist"))
            })
            .filter(|path| path.exists());

        if let Some(plist_path) = plist {
            let _ = std::process::Command::new("launchctl")
                .args([
                    "bootout",
                    &format!("gui/{uid}"),
                    &plist_path.to_string_lossy(),
                ])
                .status();
        }
    }
}

fn resolve_static_dir(handle: &AppHandle) -> Option<PathBuf> {
    let resource_dir = handle.path().resource_dir().ok()?;
    for candidate in [
        resource_dir.join("ui").join("dist"),
        resource_dir.join("dist"),
        resource_dir.join("_up_").join("ui").join("dist"),
    ] {
        if candidate.exists() {
            return Some(candidate);
        }
    }
    None
}

fn resolve_app_bundle(handle: &AppHandle) -> Option<PathBuf> {
    handle.path().resource_dir().ok().and_then(|resources| {
        resources
            .parent()
            .and_then(|contents| contents.parent())
            .map(|bundle| bundle.to_path_buf())
    })
}

fn sidecar_environment(handle: &AppHandle) -> HashMap<String, String> {
    let data = data_dir();
    let var_dir = data.join("var");
    let log_dir = data.join("logs");
    let mut env = HashMap::from([
        ("SERVE_STATIC".to_string(), "true".to_string()),
        ("DATABASE_PATH".to_string(), var_dir.join("traces.sqlite").to_string_lossy().into_owned()),
        ("LOG_DIR".to_string(), log_dir.to_string_lossy().into_owned()),
        ("LOG_TO_FILE".to_string(), "true".to_string()),
        ("FLUXION_PACKAGED".to_string(), "true".to_string()),
        ("FLUXION_APP_VERSION".to_string(), app_version().to_string()),
        ("FLUXION_BUILD_ID".to_string(), build_id().to_string()),
        (
            "PATH".to_string(),
            "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin".to_string(),
        ),
    ]);

    if let Some(static_dir) = resolve_static_dir(handle) {
        env.insert(
            "FLUXION_STATIC_DIR".to_string(),
            static_dir.to_string_lossy().into_owned(),
        );
    }
    if let Some(bundle) = resolve_app_bundle(handle) {
        env.insert(
            "FLUXION_APP_BUNDLE".to_string(),
            bundle.to_string_lossy().into_owned(),
        );
    }

    env
}

fn http_agent() -> ureq::Agent {
    let config = ureq::config::Config::builder()
        .timeout_global(Some(Duration::from_secs(2)))
        .build();
    ureq::Agent::new_with_config(config)
}

fn read_health() -> Option<HealthPayload> {
    let response = http_agent().get(&health_url()).call().ok()?;

    if !response.status().is_success() {
        return None;
    }

    response.into_body().read_json().ok()
}

fn health_matches(payload: &HealthPayload) -> bool {
    payload.status == "ok"
        && payload.app.as_deref() == Some(APP_NAME)
        && payload.packaged.unwrap_or(false)
        && payload.version.as_deref() == Some(app_version())
        && payload.build_id.as_deref() == Some(build_id())
}

fn kill_port_listener(port: u16) {
    let output = match std::process::Command::new("lsof")
        .args(["-nP", &format!("-iTCP:{port}"), "-sTCP:LISTEN", "-t"])
        .output()
    {
        Ok(output) => output,
        Err(_) => return,
    };

    if !output.status.success() {
        return;
    }

    for line in String::from_utf8_lossy(&output.stdout).lines() {
        let Ok(pid) = line.trim().parse::<i32>() else {
            continue;
        };
        let _ = std::process::Command::new("kill")
            .args(["-TERM", &pid.to_string()])
            .status();
    }
}

fn wait_for_port_release(port: u16, timeout: Duration) {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        let listening = std::process::Command::new("lsof")
            .args(["-nP", &format!("-iTCP:{port}"), "-sTCP:LISTEN", "-t"])
            .output()
            .map(|output| output.status.success() && !output.stdout.is_empty())
            .unwrap_or(false);
        if !listening {
            return;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
}

fn ensure_packaged_backend(handle: &AppHandle, state: &BackendState) -> Result<(), String> {
    if let Some(payload) = read_health() {
        if health_matches(&payload) {
            return Ok(());
        }
        if payload.app.as_deref() == Some(APP_NAME) {
            stop_sidecar(state);
            kill_port_listener(DEFAULT_PORT);
            wait_for_port_release(DEFAULT_PORT, Duration::from_secs(3));
        } else {
            return Err(format!(
                "Port {DEFAULT_PORT} is already in use by another service."
            ));
        }
    }

    spawn_sidecar(handle, state)?;
    wait_for_health(Duration::from_secs(60))
}

fn wait_for_health(timeout: Duration) -> Result<(), String> {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if let Some(payload) = read_health() {
            if health_matches(&payload) {
                return Ok(());
            }
            if payload.app.as_deref() == Some(APP_NAME)
                && payload.build_id.as_deref() != Some(build_id())
            {
                return Err(format!(
                    "Port {DEFAULT_PORT} is serving a different Fluxion build (version={:?}, build={:?}). Quit the other app and try again.",
                    payload.version, payload.build_id
                ));
            }
            if payload.app.as_deref() != Some(APP_NAME) {
                return Err(format!(
                    "Port {DEFAULT_PORT} is already in use by another service."
                ));
            }
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    Err(format!(
        "Fluxion backend did not become healthy at {}",
        service_url()
    ))
}

fn spawn_sidecar(handle: &AppHandle, state: &BackendState) -> Result<(), String> {
    std::fs::create_dir_all(data_dir().join("var")).map_err(|error| error.to_string())?;
    std::fs::create_dir_all(data_dir().join("logs")).map_err(|error| error.to_string())?;

    let mut command = handle
        .shell()
        .sidecar("fluxion-server")
        .map_err(|error| format!("sidecar missing (run release build): {error}"))?
        .args(["serve"]);

    for (key, value) in sidecar_environment(handle) {
        command = command.env(key, value);
    }

    let (mut rx, child) = command
        .spawn()
        .map_err(|error| format!("failed to start fluxion-server: {error}"))?;

    let app_handle = handle.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            if let tauri_plugin_shell::process::CommandEvent::Terminated(payload) = event {
                let _ = app_handle.emit("backend-terminated", payload.code);
                break;
            }
        }
    });

    *state.child.lock().unwrap() = Some(child);
    Ok(())
}

fn stop_sidecar(state: &BackendState) {
    if let Some(child) = state.child.lock().unwrap().take() {
        let _ = child.kill();
    }
}

fn service_webview_url() -> Result<url::Url, String> {
    service_url()
        .parse()
        .map_err(|error| format!("invalid service URL: {error}"))
}

fn show_splash_window(handle: &AppHandle) -> Result<(), String> {
    let window = handle
        .get_webview_window("main")
        .ok_or_else(|| "main window missing".to_string())?;
    window.show().map_err(|error| error.to_string())?;
    window.set_focus().map_err(|error| error.to_string())?;
    Ok(())
}

fn navigate_main_to_service(handle: &AppHandle) -> Result<(), String> {
    let window = handle
        .get_webview_window("main")
        .ok_or_else(|| "main window missing".to_string())?;
    let target = service_webview_url()?;
    window
        .navigate(target)
        .map_err(|error| format!("failed to navigate main window: {error}"))
}

fn show_splash_error(handle: &AppHandle, message: &str) {
    let Some(window) = handle.get_webview_window("main") else {
        return;
    };
    let escaped = message
        .replace('\\', "\\\\")
        .replace('\'', "\\'")
        .replace('\n', " ");
    let script = format!(
        "(() => {{
          const root = document.getElementById('status');
          const text = document.getElementById('status-text');
          if (root) root.classList.add('is-error');
          if (text) text.textContent = '{escaped}';
        }})();"
    );
    let _ = window.eval(&script);
}

fn start_backend_in_background(handle: AppHandle) {
    tauri::async_runtime::spawn(async move {
        let result = tauri::async_runtime::spawn_blocking({
            let handle = handle.clone();
            move || -> Result<(), String> {
                bootout_legacy_launch_agent();
                let state = handle.state::<BackendState>();
                if cfg!(debug_assertions) {
                    if read_health().is_none() {
                        return Err(format!(
                            "Start the API first (./dev.sh desktop from the repo root), then run cargo tauri dev. Expected {}",
                            service_url()
                        ));
                    }
                    return Ok(());
                }
                ensure_packaged_backend(&handle, &state)
            }
        })
        .await;

        let handle_for_ui = handle.clone();
        let _ = handle.run_on_main_thread(move || {
            match result {
                Ok(Ok(())) => {
                    if let Err(error) = navigate_main_to_service(&handle_for_ui) {
                        show_splash_error(&handle_for_ui, &error);
                    }
                }
                Ok(Err(message)) => {
                    eprintln!("[fluxion] backend startup failed: {message}");
                    show_splash_error(&handle_for_ui, &message);
                }
                Err(join_error) => {
                    let message = format!("Startup failed: {join_error}");
                    show_splash_error(&handle_for_ui, &message);
                }
            }
        });
    });
}

#[cfg(target_os = "macos")]
fn check_sparkle_updates(handle: &AppHandle) {
    use tauri_plugin_sparkle_updater::SparkleUpdaterExt;

    if cfg!(debug_assertions) {
        return;
    }

    if let Some(updater) = handle.sparkle_updater() {
        let _ = updater.check_for_updates_in_background();
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let mut builder = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .manage(BackendState::default())
        .setup(|app| {
            let handle = app.handle().clone();
            show_splash_window(&handle)?;
            start_backend_in_background(handle.clone());
            #[cfg(target_os = "macos")]
            check_sparkle_updates(&handle);
            Ok(())
        });

    #[cfg(target_os = "macos")]
    {
        builder = builder.plugin(tauri_plugin_sparkle_updater::init());
    }

    builder
        .build(tauri::generate_context!())
        .expect("error while building Fluxion")
        .run(|app_handle, event| {
            if let RunEvent::Exit = event {
                if let Some(state) = app_handle.try_state::<BackendState>() {
                    stop_sidecar(&state);
                }
            }
        });
}
