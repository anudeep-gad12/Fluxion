//! Fluxion Tauri shell: spawns the packaged API sidecar and hosts the UI in a WebView.

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use base64::{engine::general_purpose, Engine as _};
use serde::{Deserialize, Serialize};
use tauri::menu::MenuBuilder;
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{
    AppHandle, Emitter, LogicalSize, Manager, RunEvent, WebviewUrl, WebviewWindowBuilder, WindowEvent,
};
use tauri_plugin_opener::OpenerExt;
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;
use tauri_plugin_global_shortcut::ShortcutState;
use url::Url;

#[cfg(target_os = "macos")]
use objc2::MainThreadMarker;
#[cfg(target_os = "macos")]
use objc2_app_kit::{
    NSApplication, NSApplicationActivationPolicy, NSEvent, NSScreen, NSStatusWindowLevel, NSWindow,
    NSWindowCollectionBehavior,
};
#[cfg(target_os = "macos")]
use objc2_core_graphics::{CGPreflightScreenCaptureAccess, CGRequestScreenCaptureAccess};

const APP_NAME: &str = "Fluxion";
const APP_LABEL: &str = "io.fluxion.local";
const DEFAULT_HOST: &str = "127.0.0.1";
const DEFAULT_PORT: u16 = 9000;
const FLOATING_WINDOW_LABEL: &str = "floating";
const FLOATING_WIDTH: f64 = 920.0;
const FLOATING_HEIGHT: f64 = 360.0;
const FLOATING_HOTKEY: &str = "ctrl+alt+f";
static SCREEN_CAPTURE_PERMISSION_REQUESTED: AtomicBool = AtomicBool::new(false);

#[derive(Default)]
struct BackendState {
    child: Mutex<Option<CommandChild>>,
}

#[derive(Debug, Clone, Serialize)]
struct CapturePayload {
    name: String,
    mime_type: String,
    data_url: String,
}

#[derive(Debug, Deserialize)]
struct HealthPayload {
    status: String,
    app: Option<String>,
    packaged: Option<bool>,
    version: Option<String>,
    build_id: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
struct BrowserNewWindowPayload {
    source_label: String,
    url: String,
}

const BROWSER_NEW_TAB_INIT_SCRIPT: &str = r#"
(() => {
  if (window.__fluxionNewTabInterceptorInstalled) return;
  window.__fluxionNewTabInterceptorInstalled = true;

  const NEW_TAB_SCHEME = 'fluxion-new-tab://open?url=';
  const sendNewTab = (rawUrl) => {
    try {
      if (!rawUrl || /^javascript:/i.test(rawUrl)) return false;
      const resolved = new URL(rawUrl, window.location.href).href;
      window.location.href = NEW_TAB_SCHEME + encodeURIComponent(resolved);
      return true;
    } catch {
      return false;
    }
  };

  const anchorFrom = (target) => {
    if (!target || typeof target.closest !== 'function') return null;
    return target.closest('a[href]');
  };

  document.addEventListener('click', (event) => {
    if (event.defaultPrevented || event.button !== 0) return;
    const anchor = anchorFrom(event.target);
    if (!anchor) return;
    const target = (anchor.getAttribute('target') || '').toLowerCase();
    if (target === '_blank' || event.metaKey || event.ctrlKey || event.shiftKey) {
      if (sendNewTab(anchor.getAttribute('href'))) {
        event.preventDefault();
        event.stopPropagation();
      }
    }
  }, true);

  document.addEventListener('auxclick', (event) => {
    if (event.defaultPrevented || event.button !== 1) return;
    const anchor = anchorFrom(event.target);
    if (!anchor) return;
    if (sendNewTab(anchor.getAttribute('href'))) {
      event.preventDefault();
      event.stopPropagation();
    }
  }, true);

  const originalOpen = window.open;
  window.open = function(url, target, features) {
    if (url && sendNewTab(url)) return null;
    return originalOpen.call(window, url, target, features);
  };
})();
"#;

fn app_version() -> &'static str {
    env!("FLUXION_APP_VERSION")
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

fn floating_query(capture: bool) -> String {
    let nonce = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or_default();
    format!(
        "floating=1&new=1&capture={}&nonce={nonce}",
        if capture { "1" } else { "0" }
    )
}

fn floating_webview_url(capture: bool) -> Result<WebviewUrl, String> {
    let query = floating_query(capture);
    if cfg!(debug_assertions) {
        let url = format!("{}/?{query}", service_url())
            .parse()
            .map_err(|error| format!("invalid floating URL: {error}"))?;
        Ok(WebviewUrl::External(url))
    } else {
        Ok(WebviewUrl::App(format!("index.html?{query}").into()))
    }
}

fn home_dir_string() -> Result<String, String> {
    dirs::home_dir()
        .map(|path| path.to_string_lossy().into_owned())
        .ok_or_else(|| "Home directory not available".to_string())
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
        (
            "DATABASE_PATH".to_string(),
            var_dir.join("traces.sqlite").to_string_lossy().into_owned(),
        ),
        (
            "LOG_DIR".to_string(),
            log_dir.to_string_lossy().into_owned(),
        ),
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

fn emit_browser_new_tab(app: &AppHandle, source_label: &str, url: String) {
    let _ = app.emit(
        "fluxion-browser-new-window",
        BrowserNewWindowPayload {
            source_label: source_label.to_string(),
            url,
        },
    );
}

#[tauri::command]
fn fluxion_browser_create(
    app: AppHandle,
    label: String,
    url: String,
    x: f64,
    y: f64,
    width: f64,
    height: f64,
) -> Result<(), String> {
    let window = app
        .get_window("main")
        .ok_or_else(|| "main window missing".to_string())?;
    let parsed = Url::parse(&url).map_err(|error| error.to_string())?;
    let source_label = label.clone();
    let app_for_new_window = app.clone();
    let navigation_source_label = label.clone();
    let app_for_navigation = app.clone();
    let webview_builder = tauri::WebviewBuilder::new(label, tauri::WebviewUrl::External(parsed))
        .accept_first_mouse(true)
        .initialization_script(BROWSER_NEW_TAB_INIT_SCRIPT)
        .on_navigation(move |navigation_url| {
            if navigation_url.scheme() != "fluxion-new-tab" {
                return true;
            }
            if let Some((_, value)) = navigation_url
                .query_pairs()
                .find(|(key, _)| key.as_ref() == "url")
            {
                emit_browser_new_tab(
                    &app_for_navigation,
                    &navigation_source_label,
                    value.into_owned(),
                );
            }
            false
        })
        .on_new_window(move |new_url, _features| {
            emit_browser_new_tab(&app_for_new_window, &source_label, new_url.to_string());
            tauri::webview::NewWindowResponse::Deny
        });

    window
        .add_child(
            webview_builder,
            tauri::LogicalPosition::new(x, y),
            tauri::LogicalSize::new(width, height),
        )
        .map(|_| ())
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn fluxion_browser_navigate(app: AppHandle, label: String, url: String) -> Result<(), String> {
    let webview = app
        .get_webview(&label)
        .ok_or_else(|| format!("Browser webview not found: {label}"))?;
    let parsed = Url::parse(&url).map_err(|error| error.to_string())?;
    webview.navigate(parsed).map_err(|error| error.to_string())
}

#[tauri::command]
fn fluxion_browser_reload(app: AppHandle, label: String) -> Result<(), String> {
    let webview = app
        .get_webview(&label)
        .ok_or_else(|| format!("Browser webview not found: {label}"))?;
    webview.reload().map_err(|error| error.to_string())
}

#[tauri::command]
fn fluxion_browser_go_back(app: AppHandle, label: String) -> Result<(), String> {
    let webview = app
        .get_webview(&label)
        .ok_or_else(|| format!("Browser webview not found: {label}"))?;
    webview
        .eval("history.back()")
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn fluxion_browser_go_forward(app: AppHandle, label: String) -> Result<(), String> {
    let webview = app
        .get_webview(&label)
        .ok_or_else(|| format!("Browser webview not found: {label}"))?;
    webview
        .eval("history.forward()")
        .map_err(|error| error.to_string())
}

fn show_floating_overlay(app: &AppHandle, capture: bool) -> Result<(), String> {
    // A regular app with a hidden main window is anchored to that window's
    // Space. Activating it would switch Spaces before MoveToActiveSpace can
    // move the overlay. Spotify Tray avoids this by presenting its panel as an
    // accessory app; do the same for every overlay presentation.
    configure_menu_bar_app_activation_policy();

    if let Some(window) = app.get_webview_window(FLOATING_WINDOW_LABEL) {
        window
            .set_size(LogicalSize::new(FLOATING_WIDTH, FLOATING_HEIGHT))
            .map_err(|error| error.to_string())?;
        if cfg!(debug_assertions) {
            let url: Url = format!("{}/?{}", service_url(), floating_query(capture))
                .parse()
                .map_err(|error| format!("invalid floating URL: {error}"))?;
            window
                .navigate(url)
                .map_err(|error| format!("failed to navigate floating window: {error}"))?;
        } else {
            let script = format!("window.location.replace('index.html?{}')", floating_query(capture));
            window
                .eval(&script)
                .map_err(|error| format!("failed to reset floating window: {error}"))?;
        }
        configure_floating_window_for_spaces(&window);
        window.show().map_err(|error| error.to_string())?;
        // Tauri/winit can restore a cached primary-display frame during show.
        // Reapply both the active-Space behavior and mouse-display position
        // after the native window is visible.
        configure_floating_window_for_spaces(&window);
        present_floating_window_on_active_space(&window);
        return Ok(());
    }

    let window = WebviewWindowBuilder::new(app, FLOATING_WINDOW_LABEL, floating_webview_url(capture)?)
        .title("Fluxion")
        .inner_size(FLOATING_WIDTH, FLOATING_HEIGHT)
        .min_inner_size(520.0, 180.0)
        .decorations(false)
        .transparent(true)
        .always_on_top(true)
        .skip_taskbar(true)
        .resizable(true)
        .focused(false)
        .visible(false)
        .build()
        .map_err(|error| format!("failed to create floating window: {error}"))?;
    configure_floating_window_for_spaces(&window);
    window.show().map_err(|error| error.to_string())?;
    configure_floating_window_for_spaces(&window);
    present_floating_window_on_active_space(&window);
    Ok(())
}

fn show_floating_overlay_on_main_thread(app: AppHandle, capture: bool) {
    let target = app.clone();
    let _ = app.run_on_main_thread(move || {
        if let Err(error) = show_floating_overlay(&target, capture) {
            eprintln!("[fluxion] failed to show floating overlay: {error}");
        }
    });
}

fn show_main_window_on_main_thread(app: AppHandle) {
    let target = app.clone();
    let _ = app.run_on_main_thread(move || {
        if let Some(window) = target.get_webview_window("main") {
            activate_fluxion_for_full_window();
            let _ = window.show();
            let _ = window.set_focus();
        }
    });
}

#[cfg(target_os = "macos")]
fn configure_floating_window_for_spaces(window: &tauri::WebviewWindow) {
    if let Ok(ns_window_ptr) = window.ns_window() {
        if ns_window_ptr.is_null() {
            return;
        }
        let ns_window: &NSWindow = unsafe { &*ns_window_ptr.cast() };
        // Match a native command-palette panel: move the existing window to
        // whichever Space is active instead of pinning it to every Space.
        // FullScreenAuxiliary allows that active Space to belong to a
        // full-screen application.
        let behavior = NSWindowCollectionBehavior::MoveToActiveSpace
            | NSWindowCollectionBehavior::Transient
            | NSWindowCollectionBehavior::IgnoresCycle
            | NSWindowCollectionBehavior::FullScreenAuxiliary;
        ns_window.setCollectionBehavior(behavior);
        ns_window.setLevel(NSStatusWindowLevel);
        ns_window.setCanHide(false);
        ns_window.setHidesOnDeactivate(false);
        // WKWebView windows retain a rectangular AppKit shadow even when the
        // page itself has rounded transparent corners. The card draws its own
        // alpha-aware shadow inside the transparent window instead.
        ns_window.setHasShadow(false);
        position_native_floating_window(ns_window);
    }
}

#[cfg(not(target_os = "macos"))]
fn configure_floating_window_for_spaces(_window: &tauri::WebviewWindow) {}

#[cfg(target_os = "macos")]
fn present_floating_window_on_active_space(window: &tauri::WebviewWindow) {
    let Some(mtm) = MainThreadMarker::new() else {
        return;
    };
    let app = NSApplication::sharedApplication(mtm);
    app.activate();

    if let Ok(ns_window_ptr) = window.ns_window() {
        if ns_window_ptr.is_null() {
            return;
        }
        let ns_window: &NSWindow = unsafe { &*ns_window_ptr.cast() };
        // makeKeyAndOrderFront is the operation that applies
        // MoveToActiveSpace. orderFrontRegardless alone can leave a reused
        // window attached to the Space where it was originally created.
        ns_window.makeKeyAndOrderFront(None);
    }
}

#[cfg(not(target_os = "macos"))]
fn present_floating_window_on_active_space(_window: &tauri::WebviewWindow) {}

#[cfg(target_os = "macos")]
fn configure_menu_bar_app_activation_policy() {
    let Some(mtm) = MainThreadMarker::new() else {
        return;
    };
    let app = NSApplication::sharedApplication(mtm);
    let _ = app.setActivationPolicy(NSApplicationActivationPolicy::Accessory);
}

#[cfg(not(target_os = "macos"))]
fn configure_menu_bar_app_activation_policy() {}

#[cfg(target_os = "macos")]
fn restore_activation_policy_after_overlay(app_handle: &AppHandle) {
    let main_is_visible = app_handle
        .get_webview_window("main")
        .and_then(|window| window.is_visible().ok())
        .unwrap_or(false);
    if main_is_visible {
        let Some(mtm) = MainThreadMarker::new() else {
            return;
        };
        let app = NSApplication::sharedApplication(mtm);
        let _ = app.setActivationPolicy(NSApplicationActivationPolicy::Regular);
    } else {
        configure_menu_bar_app_activation_policy();
    }
}

#[cfg(not(target_os = "macos"))]
fn restore_activation_policy_after_overlay(_app_handle: &AppHandle) {}

#[cfg(target_os = "macos")]
fn activate_fluxion_for_full_window() {
    let Some(mtm) = MainThreadMarker::new() else {
        return;
    };
    let app = NSApplication::sharedApplication(mtm);
    // Fluxion starts as an accessory/menu-bar app. Promote it while the full
    // window is in use so the Dock can deliver applicationShouldHandleReopen
    // after the user closes (hides) that window.
    let _ = app.setActivationPolicy(NSApplicationActivationPolicy::Regular);
    app.activate();
}

#[cfg(not(target_os = "macos"))]
fn activate_fluxion_for_full_window() {}

#[cfg(target_os = "macos")]
fn position_native_floating_window(ns_window: &NSWindow) {
    let Some(mtm) = MainThreadMarker::new() else {
        return;
    };
    let mouse = NSEvent::mouseLocation();
    let screens = NSScreen::screens(mtm);
    let mut selected = None;
    for index in 0..screens.count() {
        let screen = screens.objectAtIndex(index);
        let frame = screen.frame();
        let within_x = mouse.x >= frame.origin.x && mouse.x <= frame.origin.x + frame.size.width;
        let within_y = mouse.y >= frame.origin.y && mouse.y <= frame.origin.y + frame.size.height;
        if within_x && within_y {
            selected = Some(screen);
            break;
        }
    }
    let screen = selected
        .or_else(|| NSScreen::mainScreen(mtm))
        .or_else(|| {
            if screens.count() > 0 {
                Some(screens.objectAtIndex(0))
            } else {
                None
            }
        });
    let Some(screen) = screen else {
        return;
    };

    let visible = screen.frame();
    let margin = 16.0;
    let width = FLOATING_WIDTH;
    let height = FLOATING_HEIGHT;
    let max_x = visible.origin.x + visible.size.width - width - margin;
    let min_x = visible.origin.x + margin;
    let max_y = visible.origin.y + visible.size.height - height - margin;
    let min_y = visible.origin.y + margin;
    let mut frame = visible;
    frame.size.width = width;
    frame.size.height = height;
    frame.origin.x = (mouse.x - width / 2.0).clamp(min_x, max_x.max(min_x));
    frame.origin.y = (mouse.y - height / 2.0).clamp(min_y, max_y.max(min_y));
    ns_window.setFrame_display(frame, true);
}

#[tauri::command]
fn fluxion_show_floating_overlay(app: AppHandle, capture: Option<bool>) -> Result<(), String> {
    show_floating_overlay_on_main_thread(app, capture.unwrap_or(false));
    Ok(())
}

#[tauri::command]
fn fluxion_hide_floating_overlay(app: AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window(FLOATING_WINDOW_LABEL) {
        window.hide().map_err(|error| error.to_string())?;
    }
    restore_activation_policy_after_overlay(&app);
    Ok(())
}

#[tauri::command]
fn fluxion_home_dir() -> Result<String, String> {
    home_dir_string()
}

#[tauri::command]
fn fluxion_capture_area(app: AppHandle) -> Result<Option<CapturePayload>, String> {
    #[cfg(target_os = "macos")]
    {
        if !CGPreflightScreenCaptureAccess() {
            let newly_granted = if !SCREEN_CAPTURE_PERMISSION_REQUESTED.swap(true, Ordering::SeqCst)
            {
                CGRequestScreenCaptureAccess()
            } else {
                false
            };
            if !newly_granted && !CGPreflightScreenCaptureAccess() {
                return Err(
                    "Screen Recording access is required. Enable Fluxion in System Settings > Privacy & Security > Screen & System Audio Recording, then choose Quit Fluxion from the menu bar and reopen this same app build once."
                        .to_string(),
                );
            }
        }
    }

    if let Some(window) = app.get_webview_window(FLOATING_WINDOW_LABEL) {
        let _ = window.hide();
    }
    std::thread::sleep(Duration::from_millis(180));

    let output_path = std::env::temp_dir().join(format!(
        "fluxion-capture-{}-{}.png",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|duration| duration.as_millis())
            .unwrap_or_default()
    ));

    let status = std::process::Command::new("/usr/sbin/screencapture")
        .args(["-i", "-x", &output_path.to_string_lossy()])
        .status()
        .map_err(|error| format!("failed to start screencapture: {error}"))?;

    if !status.success() || !output_path.exists() {
        let _ = std::fs::remove_file(&output_path);
        return Ok(None);
    }

    let bytes = std::fs::read(&output_path).map_err(|error| error.to_string())?;
    let _ = std::fs::remove_file(&output_path);
    if bytes.is_empty() {
        return Ok(None);
    }

    Ok(Some(CapturePayload {
        name: "screenshot.png".to_string(),
        mime_type: "image/png".to_string(),
        data_url: format!(
            "data:image/png;base64,{}",
            general_purpose::STANDARD.encode(bytes)
        ),
    }))
}

fn strip_terminal_path_suffix(value: &str) -> String {
    let mut cleaned = value
        .trim()
        .trim_matches(|ch| matches!(ch, '"' | '\'' | '`' | '<' | '>'))
        .trim_end_matches(|ch| matches!(ch, '.' | ',' | ';' | ')' | ']' | '}'))
        .to_string();

    for _ in 0..2 {
        let Some((head, tail)) = cleaned.rsplit_once(':') else {
            break;
        };
        if !tail.is_empty() && tail.chars().all(|ch| ch.is_ascii_digit()) {
            cleaned = head.to_string();
        } else {
            break;
        }
    }

    cleaned
}

#[tauri::command]
fn fluxion_open_terminal_path(
    app: AppHandle,
    path: String,
    workspace_path: Option<String>,
) -> Result<(), String> {
    let cleaned = strip_terminal_path_suffix(&path);
    if cleaned.is_empty() || cleaned.contains('\0') {
        return Err("Invalid terminal path".to_string());
    }

    let path_buf = if let Some(rest) = cleaned.strip_prefix("file://") {
        Url::parse(&cleaned)
            .ok()
            .and_then(|url| url.to_file_path().ok())
            .unwrap_or_else(|| PathBuf::from(rest))
    } else if cleaned == "~" {
        dirs::home_dir().ok_or_else(|| "Home directory not available".to_string())?
    } else if let Some(rest) = cleaned.strip_prefix("~/") {
        dirs::home_dir()
            .ok_or_else(|| "Home directory not available".to_string())?
            .join(rest)
    } else {
        let raw = PathBuf::from(&cleaned);
        if raw.is_absolute() {
            raw
        } else {
            let workspace = workspace_path
                .filter(|value| !value.trim().is_empty())
                .map(PathBuf::from)
                .unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));
            workspace.join(raw)
        }
    };

    let resolved = path_buf.canonicalize().unwrap_or(path_buf);
    app.opener()
        .open_path(resolved.to_string_lossy().into_owned(), None::<&str>)
        .map_err(|error| error.to_string())
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

fn navigate_main_to_app_index(handle: &AppHandle) -> Result<(), String> {
    let window = handle
        .get_webview_window("main")
        .ok_or_else(|| "main window missing".to_string())?;
    window
        .eval("window.location.replace('index.html')")
        .map_err(|error| format!("failed to navigate main window to app assets: {error}"))
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
        let _ = handle.run_on_main_thread(move || match result {
            Ok(Ok(())) => {
                let navigation_result = if cfg!(debug_assertions) {
                    navigate_main_to_service(&handle_for_ui)
                } else {
                    navigate_main_to_app_index(&handle_for_ui)
                };
                if let Err(error) = navigation_result {
                    let _ = show_splash_window(&handle_for_ui);
                    show_splash_error(&handle_for_ui, &error);
                } else {
                    show_main_window_on_main_thread(handle_for_ui.clone());
                }
            }
            Ok(Err(message)) => {
                eprintln!("[fluxion] backend startup failed: {message}");
                let _ = show_splash_window(&handle_for_ui);
                show_splash_error(&handle_for_ui, &message);
            }
            Err(join_error) => {
                let message = format!("Startup failed: {join_error}");
                let _ = show_splash_window(&handle_for_ui);
                show_splash_error(&handle_for_ui, &message);
            }
        });
    });
}

fn install_tray(handle: &AppHandle) -> Result<(), String> {
    let menu = MenuBuilder::new(handle)
        .text("new-floating", "New Floating Chat")
        .text("open-main", "Open Full Fluxion")
        .separator()
        .text("quit", "Quit Fluxion")
        .build()
        .map_err(|error| error.to_string())?;

    let mut builder = TrayIconBuilder::new()
        .tooltip("Fluxion")
        .menu(&menu)
        .icon_as_template(false)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "new-floating" => {
                show_floating_overlay_on_main_thread(app.clone(), false);
            }
            "open-main" => {
                show_main_window_on_main_thread(app.clone());
            }
            "quit" => {
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show_floating_overlay_on_main_thread(tray.app_handle().clone(), false);
            }
        });

    if let Some(icon) = handle.default_window_icon() {
        builder = builder.icon(icon.clone());
    } else {
        builder = builder.title("Fluxion");
    }

    builder.build(handle).map_err(|error| error.to_string())?;
    Ok(())
}

fn install_global_shortcut(handle: &AppHandle) -> Result<(), String> {
    handle
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_shortcut(FLOATING_HOTKEY)
                .map_err(|error| error.to_string())?
                .with_handler(move |app, _shortcut, event| {
                    if event.state == ShortcutState::Pressed {
                        show_floating_overlay_on_main_thread(app.clone(), false);
                    }
                })
                .build(),
        )
        .map_err(|error| error.to_string())?;
    Ok(())
}

#[cfg(target_os = "macos")]
fn check_sparkle_updates(handle: &AppHandle) {
    use tauri_plugin_sparkle_updater::SparkleUpdaterExt;

    if cfg!(debug_assertions) || build_id() == "source" || build_id().contains("-dirty-") {
        return;
    }

    if let Some(updater) = handle.sparkle_updater() {
        let _ = updater.check_for_updates_in_background();
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let mut builder = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            show_main_window_on_main_thread(app.clone());
        }))
        .manage(BackendState::default())
        .setup(|app| {
            let handle = app.handle().clone();
            configure_menu_bar_app_activation_policy();
            if let Err(error) = install_tray(&handle) {
                eprintln!("[fluxion] failed to install menu bar icon: {error}");
            }
            if let Err(error) = install_global_shortcut(&handle) {
                eprintln!("[fluxion] failed to register {FLOATING_HOTKEY}: {error}");
            }
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
        .invoke_handler(tauri::generate_handler![
            fluxion_browser_create,
            fluxion_browser_navigate,
            fluxion_browser_reload,
            fluxion_browser_go_back,
            fluxion_browser_go_forward,
            fluxion_open_terminal_path,
            fluxion_show_floating_overlay,
            fluxion_hide_floating_overlay,
            fluxion_home_dir,
            fluxion_capture_area,
        ])
        .build(tauri::generate_context!())
        .expect("error while building Fluxion")
        .run(|app_handle, event| {
            match event {
                RunEvent::WindowEvent {
                    label,
                    event: WindowEvent::CloseRequested { api, .. },
                    ..
                } => {
                    api.prevent_close();
                    if let Some(window) = app_handle.get_webview_window(&label) {
                        let _ = window.hide();
                    }
                    if label == "main" {
                        configure_menu_bar_app_activation_policy();
                    } else if label == FLOATING_WINDOW_LABEL {
                        restore_activation_policy_after_overlay(app_handle);
                    }
                }
                RunEvent::ExitRequested {
                    code: None, api, ..
                } => {
                    api.prevent_exit();
                    for label in ["main", FLOATING_WINDOW_LABEL] {
                        if let Some(window) = app_handle.get_webview_window(label) {
                            let _ = window.hide();
                        }
                    }
                }
                RunEvent::Reopen { .. } => {
                    show_main_window_on_main_thread(app_handle.clone());
                }
                RunEvent::Exit => {
                    if let Some(state) = app_handle.try_state::<BackendState>() {
                        stop_sidecar(&state);
                    }
                }
                _ => {}
            }
        });
}
