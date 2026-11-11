use machine_access as machines;
mod native;
use base64::{engine::general_purpose::STANDARD, Engine};
use serde_json::{json, Value};
use std::{
    path::PathBuf,
    sync::{Mutex, OnceLock},
};
static DATA: OnceLock<Mutex<Option<PathBuf>>> = OnceLock::new();
const API: &str = "/v0/management/ssh-machines";
fn store() -> Result<machines::Store, String> {
    let guard = DATA
        .get_or_init(|| Mutex::new(None))
        .lock()
        .map_err(|_| "Restart plugin")?;
    machines::Store::new(guard.clone().ok_or("Plugin is not configured")?)
}
fn http(status: u16, mime: &str, bytes: &[u8]) -> Value {
    json!({"StatusCode":status,"Headers":{"Content-Type":[mime],"Cache-Control":["no-store"],"X-Content-Type-Options":["nosniff"],"Referrer-Policy":["no-referrer"],"Content-Security-Policy":["default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'"]},"Body":STANDARD.encode(bytes)})
}
fn response(result: Result<Value, String>) -> Value {
    let (status, value) = match result {
        Ok(v) => (200, v),
        Err(e) => (400, json!({"error":e})),
    };
    http(
        status,
        "application/json; charset=utf-8",
        value.to_string().as_bytes(),
    )
}
fn dispatch(method: &str, raw: &[u8]) -> Value {
    let result = (|| -> Result<Value, String> {
        Ok(match method {
            "plugin.register" | "plugin.reconfigure" => {
                let request: Value =
                    serde_json::from_slice(raw).map_err(|_| "Invalid lifecycle request")?;
                let bytes = STANDARD
                    .decode(request["config_yaml"].as_str().unwrap_or(""))
                    .map_err(|_| "Invalid configuration")?;
                let config: Value = if bytes.is_empty() {
                    json!({})
                } else {
                    serde_yaml_ng::from_slice(&bytes).map_err(|_| "Invalid configuration")?
                };
                let dir = match config["data_dir"].as_str().filter(|s| !s.trim().is_empty()) {
                    Some(path) => PathBuf::from(path),
                    None => PathBuf::from(
                        std::env::var_os("LOCALAPPDATA").ok_or("Configure an absolute data_dir")?,
                    )
                    .join("ECPA/ssh-machines"),
                };
                let s = machines::Store::new(dir)?;
                *DATA
                    .get_or_init(|| Mutex::new(None))
                    .lock()
                    .map_err(|_| "Restart plugin")? = Some(s.dir);
                json!({"schema_version":6,"metadata":{"Name":"SSH and Machines","Version":env!("CARGO_PKG_VERSION"),"Author":"GoblinRules","GitHubRepository":env!("CARGO_PKG_REPOSITORY"),"Logo":"https://raw.githubusercontent.com/GoblinRules/ecpa-plugins/master/assets/icons/ssh-machines.svg","ConfigFields":[{"Name":"data_dir","Type":"string","Description":"Private machine catalogue directory on the ECPA host. Defaults to LocalAppData/ECPA/ssh-machines. Do not put keys or passwords in plugin settings."}]},"capabilities":{"management_api":true}})
            }
            "plugin.quiesce" => json!({}),
            "plugin.shutdown" => {
                *DATA
                    .get_or_init(|| Mutex::new(None))
                    .lock()
                    .map_err(|_| "Restart plugin")? = None;
                json!({})
            }
            "management.register" => {
                json!({"resources":[{"Path":"/editor","Menu":"SSH and Machines","Description":"Machine profiles, pinned host keys and connection diagnostics"}],"routes":[{"Method":"GET","Path":format!("{API}/state")},{"Method":"POST","Path":format!("{API}/action")}]})
            }
            "management.handle" => {
                let req: Value = serde_json::from_slice(raw).map_err(|_| "Invalid request")?;
                let path = req["Path"].as_str().unwrap_or("");
                let verb = req["Method"].as_str().unwrap_or("");
                if verb == "GET" && path == "/v0/resource/plugins/ssh-machines/editor" {
                    http(
                        200,
                        "text/html; charset=utf-8",
                        include_bytes!("../web/editor.html"),
                    )
                } else if verb == "GET" && path == format!("{API}/state") {
                    response(store()?.state())
                } else if verb == "POST" && path == format!("{API}/action") {
                    response((|| {
                        let bytes = STANDARD
                            .decode(req["Body"].as_str().unwrap_or(""))
                            .map_err(|_| "Invalid body")?;
                        if bytes.len() > 16384 {
                            return Err("Request too large".into());
                        }
                        let body: Value =
                            serde_json::from_slice(&bytes).map_err(|_| "Invalid JSON")?;
                        let s = store()?;
                        match body["action"].as_str().unwrap_or(""){
                        "save"=>s.save(serde_json::from_value(body["machine"].clone()).map_err(|_|"Invalid machine fields; passwords/private keys are not accepted")?,body["version"].as_str().unwrap_or(""),body["reviewed_fingerprint"].as_str().unwrap_or("")),
                        "delete"=>s.remove(body["id"].as_str().unwrap_or(""),body["version"].as_str().unwrap_or("")),
                        "scan"=>machines::scan(body["host"].as_str().unwrap_or(""),body["user"].as_str().unwrap_or(""),body["port"].as_u64().and_then(|n|u16::try_from(n).ok()).unwrap_or(0)),
                        "test"=>machines::test(&s,body["id"].as_str().unwrap_or("")),
                        "terminal"=>s.terminal(body["id"].as_str().unwrap_or("")),
                        "export"=>s.export(),
                        _=>Err("Unknown action; remote command execution is not an API capability.".into())
                    }
                    })())
                } else {
                    http(404, "application/json", b"{\"error\":\"Unknown route\"}")
                }
            }
            _ => return Err("Unknown plugin method".into()),
        })
    })();
    match result {
        Ok(value) => json!({"ok":true,"result":value}),
        Err(message) => json!({"ok":false,"error":{"code":"plugin_error","message":message}}),
    }
}

#[cfg(test)]
mod tests;
