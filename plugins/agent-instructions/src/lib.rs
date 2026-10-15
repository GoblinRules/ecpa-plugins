use agent_files::{config, storage};
use base64::{engine::general_purpose::STANDARD, Engine};
use serde_json::{json, Value};
use std::{
    ffi::{c_char, c_void, CStr},
    ptr,
    sync::Mutex,
};

const API: &str = "/v0/management/agent-instructions";
const PAGE: &str = "/v0/resource/plugins/agent-instructions/editor";
static IO_LOCK: Mutex<config::Paths> = Mutex::new(config::Paths::new());

#[repr(C)]
pub struct Buffer {
    ptr: *mut u8,
    len: usize,
}
type HostCall =
    unsafe extern "C" fn(*mut c_void, *const c_char, *const u8, usize, *mut Buffer) -> i32;
#[repr(C)]
pub struct HostApi {
    abi_version: u32,
    host_ctx: *mut c_void,
    call: Option<HostCall>,
    free_buffer: Option<unsafe extern "C" fn(*mut c_void, usize)>,
}
#[repr(C)]
pub struct PluginApi {
    abi_version: u32,
    call: Option<unsafe extern "C" fn(*const c_char, *const u8, usize, *mut Buffer) -> i32>,
    free_buffer: Option<unsafe extern "C" fn(*mut c_void, usize)>,
    shutdown: Option<unsafe extern "C" fn()>,
}

/// Initialize the CLIProxyAPI v1 native ABI.
///
/// # Safety
/// The host must provide valid, aligned ABI structures for the duration of this call.
#[no_mangle]
pub unsafe extern "C" fn cliproxy_plugin_init(host: *const HostApi, plugin: *mut PluginApi) -> i32 {
    if host.is_null() || plugin.is_null() || (*host).abi_version != 1 {
        return 1;
    }
    ptr::write(
        plugin,
        PluginApi {
            abi_version: 1,
            call: Some(call),
            free_buffer: Some(free),
            shutdown: Some(shutdown),
        },
    );
    0
}
unsafe extern "C" fn call(
    method: *const c_char,
    request: *const u8,
    len: usize,
    response: *mut Buffer,
) -> i32 {
    if response.is_null() {
        return 1;
    }
    ptr::write(
        response,
        Buffer {
            ptr: ptr::null_mut(),
            len: 0,
        },
    );
    if method.is_null() || len > 8 * storage::LIMIT || (request.is_null() && len != 0) {
        return 1;
    }
    let result = std::panic::catch_unwind(|| {
        let method = CStr::from_ptr(method).to_str().unwrap_or("");
        let bytes = if len == 0 { &[] } else { std::slice::from_raw_parts(request, len) };
        dispatch(method, bytes)
    }).unwrap_or_else(|_| json!({"ok": false, "error": {"code": "plugin_error", "message": "Plugin operation failed"}}));
    let bytes = result.to_string().into_bytes().into_boxed_slice();
    let len = bytes.len();
    ptr::write(
        response,
        Buffer {
            ptr: Box::into_raw(bytes) as *mut u8,
            len,
        },
    );
    0
}
unsafe extern "C" fn free(p: *mut c_void, len: usize) {
    if !p.is_null() {
        drop(Box::from_raw(ptr::slice_from_raw_parts_mut(
            p as *mut u8,
            len,
        )));
    }
}
unsafe extern "C" fn shutdown() {}

fn dispatch(method: &str, raw: &[u8]) -> Value {
    let result = match method {
        "plugin.register" | "plugin.reconfigure" => {
            let paths = match config::parse(raw) {
                Ok(paths) => paths,
                Err(message) => {
                    return json!({"ok": false, "error": {"code": "invalid_config", "message": message}})
                }
            };
            match IO_LOCK.lock() {
                Ok(mut current) => *current = paths,
                Err(_) => {
                    return json!({"ok": false, "error": {"code": "plugin_error", "message": "Restart the proxy"}})
                }
            }
            json!({"schema_version": 6,
                "metadata": {"Name": "Agent Instructions", "Version": env!("CARGO_PKG_VERSION"), "Author": "GoblinRules",
                    "Logo": "https://raw.githubusercontent.com/GoblinRules/ecpa-plugins/master/assets/icons/agent-instructions.svg",
                    "GitHubRepository": "https://github.com/GoblinRules/ecpa-plugins", "ConfigFields": config::fields()},
                "capabilities": {"management_api": true}})
        }
        "management.register" => {
            json!({"resources": [{"Path": "/editor", "Menu": "Agent Instructions", "Description": "Edit global agent instructions"}],
            "routes": [
                {"Method": "GET", "Path": format!("{API}/files")},
                {"Method": "GET", "Path": format!("{API}/backups")},
                {"Method": "PUT", "Path": format!("{API}/file")},
                {"Method": "POST", "Path": format!("{API}/restore")}
            ]})
        }
        "management.handle" => match serde_json::from_slice::<Value>(raw) {
            Ok(req) => handle(&req),
            Err(_) => http_json(400, json!({"error": "Invalid ABI request"})),
        },
        _ => {
            return json!({"ok": false, "error": {"code": "unknown_method", "message": "Unknown plugin method"}})
        }
    };
    json!({"ok": true, "result": result})
}
fn http(status: u16, mime: &str, body: &[u8]) -> Value {
    json!({"StatusCode": status, "Headers": {"Content-Type": [mime], "Cache-Control": ["no-store"],
        "X-Content-Type-Options": ["nosniff"], "Referrer-Policy": ["no-referrer"],
        "Content-Security-Policy": ["default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'"]},
        "Body": STANDARD.encode(body)})
}
fn http_json(status: u16, value: Value) -> Value {
    http(
        status,
        "application/json; charset=utf-8",
        value.to_string().as_bytes(),
    )
}
fn field<'a>(v: &'a Value, key: &str) -> storage::Result<&'a str> {
    v[key]
        .as_str()
        .ok_or_else(|| storage::bad(&format!("Missing {key}")))
}
fn handle(req: &Value) -> Value {
    let path = req["Path"].as_str().unwrap_or("");
    let method = req["Method"].as_str().unwrap_or("");
    if path == PAGE && method == "GET" {
        return http(
            200,
            "text/html; charset=utf-8",
            include_bytes!("../web/editor.html"),
        );
    }
    // Only exact authenticated management routes can reach disk operations. The public resource
    // handler cannot be turned into a file endpoint using query strings or request bodies.
    let allowed = [
        ("GET", "files"),
        ("GET", "backups"),
        ("PUT", "file"),
        ("POST", "restore"),
    ];
    if !allowed
        .iter()
        .any(|(m, p)| method == *m && path == format!("{API}/{p}"))
    {
        return http_json(404, json!({"error": "Unknown route"}));
    }
    let result = (|| -> storage::Result<Value> {
        let _lock = IO_LOCK
            .lock()
            .map_err(|_| (500, "File service unavailable; restart the proxy".into()))?;
        let store = storage::Store::discover(_lock.clone())?;
        if method == "GET" {
            return if path.ends_with("/files") {
                store.list()
            } else {
                let id = req["Query"]["id"][0]
                    .as_str()
                    .ok_or_else(|| storage::bad("Missing file id"))?;
                store.backups(id)
            };
        }
        let encoded = field(req, "Body")?;
        if encoded.len() > 8 * storage::LIMIT {
            return Err((413, "Request too large".into()));
        }
        let bytes = STANDARD
            .decode(encoded)
            .map_err(|_| storage::bad("Invalid body encoding"))?;
        let body: Value =
            serde_json::from_slice(&bytes).map_err(|_| storage::bad("Invalid JSON body"))?;
        let id = field(&body, "id")?;
        let expected = field(&body, "version")?;
        if method == "PUT" {
            store.save(id, expected, field(&body, "content")?)
        } else {
            store.restore(id, expected, field(&body, "backup")?)
        }
    })();
    match result {
        Ok(v) => http_json(200, v),
        Err((code, msg)) => http_json(code, json!({"error": msg})),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn lifecycle_publishes_fields_and_rejects_invalid_reconfiguration() {
        let dir = tempfile::tempdir().unwrap();
        let target = dir.path().join("rules.md");
        let raw =
            json!({"config_yaml": STANDARD.encode(json!({"claude_path": target}).to_string())})
                .to_string();
        let registered = dispatch("plugin.register", raw.as_bytes());
        assert_eq!(registered["ok"], true);
        assert_eq!(
            registered["result"]["metadata"]["ConfigFields"]
                .as_array()
                .unwrap()
                .len(),
            8
        );
        let invalid =
            json!({"config_yaml": STANDARD.encode("claude_path: relative.md")}).to_string();
        assert_eq!(
            dispatch("plugin.reconfigure", invalid.as_bytes())["ok"],
            false
        );
        assert_eq!(IO_LOCK.lock().unwrap().get("claude"), Some(&target));
        assert_eq!(dispatch("plugin.reconfigure", b"{}")["ok"], true);
        assert!(IO_LOCK.lock().unwrap().is_empty());
    }
    #[test]
    fn public_page_cannot_access_files() {
        let page = handle(&json!({"Method": "GET", "Path": PAGE, "Query": {"id": ["claude"]}}));
        assert_eq!(page["StatusCode"], 200);
        assert!(
            String::from_utf8(STANDARD.decode(page["Body"].as_str().unwrap()).unwrap())
                .unwrap()
                .contains("<!doctype html>")
        );
        for path in [
            format!("{PAGE}/file"),
            "/v0/resource/plugins/agent-instructions/files".into(),
            format!("{API}/file/../files"),
        ] {
            assert_eq!(
                handle(&json!({"Method":"GET", "Path": path}))["StatusCode"],
                404
            );
        }
        assert_eq!(
            handle(&json!({"Method":"PUT", "Path":PAGE}))["StatusCode"],
            404
        );
    }
    #[test]
    fn registration_separates_public_and_authenticated_routes() {
        let r = dispatch("management.register", b"{}");
        assert_eq!(r["result"]["resources"].as_array().unwrap().len(), 1);
        for route in r["result"]["routes"].as_array().unwrap() {
            assert!(route["Path"].as_str().unwrap().starts_with(API));
            assert!(route.get("Menu").is_none());
        }
        assert_eq!(dispatch("unknown", b"{}")["ok"], false);
        assert_eq!(
            dispatch("management.handle", b"no")["result"]["StatusCode"],
            400
        );
    }
}
