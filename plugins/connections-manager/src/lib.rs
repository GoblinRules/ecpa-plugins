mod native;
pub mod store;
pub mod vault;
use base64::{engine::general_purpose::STANDARD, Engine};
use serde_json::{json, Value};
use std::{
    path::PathBuf,
    sync::{Mutex, OnceLock},
    time::Duration,
};
use store::Store;
use vault::{SystemVault, Vault};
static DATA: OnceLock<Mutex<Option<PathBuf>>> = OnceLock::new();
const API: &str = "/v0/management/connections-manager";
fn configured() -> Result<Store, String> {
    let guard = DATA
        .get_or_init(|| Mutex::new(None))
        .lock()
        .map_err(|_| "Restart the core")?;
    Store::new(guard.clone().ok_or("Plugin is not configured")?)
}
pub fn verify(store: &Store, id: &str, vault: &impl Vault) -> Result<Value, String> {
    let lock = store.lock(false)?;
    let c = store.selected(Some(id), None)?.remove(0);
    let token = vault.read(&store.target(id))?;
    drop(lock);
    let client = ureq::AgentBuilder::new()
        .timeout(Duration::from_secs(15))
        .redirects(0)
        .build();
    let url = if c.service == "github" {
        "https://api.github.com/user".to_string()
    } else {
        format!(
            "https://api.cloudflare.com/client/v4/accounts/{}",
            c.account_id
        )
    };
    let response=client.get(&url).set("Authorization",&format!("Bearer {}",&*token)).set("User-Agent","ECPA-Connections-Manager/0.1").set("Accept","application/json").call().map_err(|e|match e{ureq::Error::Status(401,_)=>"Token was rejected".to_string(),ureq::Error::Status(403,_)=>"Account check was denied. Check account ID and token permissions (Cloudflare Account Settings: Read is needed for this check).".into(),_=>"Account check failed; check connectivity and token permissions".into()})?;
    let data: Value = response
        .into_json()
        .map_err(|_| "Unexpected service response")?;
    let identity = if c.service == "github" {
        data["login"].as_str()
    } else if data["success"] == true {
        data["result"]["name"].as_str()
    } else {
        None
    }
    .ok_or("Service did not confirm account identity")?;
    Ok(
        json!({"id":c.id,"service":c.service,"identity":identity,"accountId":if c.service=="github"{data["id"].to_string()}else{c.account_id},"message":"Account identity confirmed. Deployment/repository permissions depend on the token's scope."}),
    )
}
fn http(status: u16, mime: &str, bytes: &[u8]) -> Value {
    json!({"StatusCode":status,"Headers":{"Content-Type":[mime],"Cache-Control":["no-store"],"X-Content-Type-Options":["nosniff"],"Referrer-Policy":["no-referrer"],"Content-Security-Policy":["default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'"]},"Body":STANDARD.encode(bytes)})
}
fn response(result: Result<Value, String>) -> Value {
    let (status, body) = match result {
        Ok(v) => (200, v),
        Err(e) => (400, json!({"error":e})),
    };
    http(
        status,
        "application/json; charset=utf-8",
        body.to_string().as_bytes(),
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
                    .map_err(|_| "Invalid config encoding")?;
                let values: Value = if bytes.is_empty() {
                    json!({})
                } else {
                    serde_yaml_ng::from_slice(&bytes).map_err(|_| "Invalid config YAML")?
                };
                let dir = match values.get("data_dir") {
                    None | Some(Value::Null) => store::default_dir()?,
                    Some(Value::String(s)) if s.trim().is_empty() => store::default_dir()?,
                    Some(Value::String(s)) => PathBuf::from(s),
                    _ => return Err("data_dir must be a string".into()),
                };
                let store = Store::new(dir)?;
                *DATA
                    .get_or_init(|| Mutex::new(None))
                    .lock()
                    .map_err(|_| "Restart the core")? = Some(store.dir);
                json!({"schema_version":6,"metadata":{"Name":"Connections Manager","Version":env!("CARGO_PKG_VERSION"),"Author":"GoblinRules","GitHubRepository":env!("CARGO_PKG_REPOSITORY"),"Logo":"https://raw.githubusercontent.com/GoblinRules/ecpa-plugins/master/assets/icons/connections-manager.svg","ConfigFields":[{"Name":"data_dir","Type":"string","Description":"Absolute catalogue directory. Leave blank for LocalAppData/ECPA/connections-manager. The helper must use the same directory and Windows user. Never put tokens here."}]},"capabilities":{"management_api":true}})
            }
            "plugin.quiesce" => json!({}),
            "plugin.shutdown" => {
                *DATA
                    .get_or_init(|| Mutex::new(None))
                    .lock()
                    .map_err(|_| "Restart the core")? = None;
                json!({})
            }
            "management.register" => {
                json!({"resources":[{"Path":"/editor","Menu":"Connections Manager","Description":"Named accounts and project connections"}],"routes":[{"Method":"GET","Path":format!("{API}/state")},{"Method":"POST","Path":format!("{API}/save")},{"Method":"POST","Path":format!("{API}/delete")},{"Method":"POST","Path":format!("{API}/assign")},{"Method":"POST","Path":format!("{API}/verify")}]})
            }
            "management.handle" => {
                let req: Value = serde_json::from_slice(raw).map_err(|_| "Invalid request")?;
                let path = req["Path"].as_str().unwrap_or("");
                let verb = req["Method"].as_str().unwrap_or("");
                if verb == "GET" && path == "/v0/resource/plugins/connections-manager/editor" {
                    http(
                        200,
                        "text/html; charset=utf-8",
                        include_bytes!("../web/editor.html"),
                    )
                } else if verb == "GET" && path == format!("{API}/state") {
                    response(configured().and_then(|s| s.state(&SystemVault)))
                } else if verb == "POST"
                    && ["save", "delete", "assign", "verify"]
                        .iter()
                        .any(|p| path == format!("{API}/{p}"))
                {
                    response((|| {
                        let s = configured()?;
                        let bytes = zeroize::Zeroizing::new(
                            STANDARD
                                .decode(req["Body"].as_str().unwrap_or(""))
                                .map_err(|_| "Invalid body")?,
                        );
                        if bytes.len() > 16384 {
                            return Err("Request too large".into());
                        }
                        let mut body: Value =
                            serde_json::from_slice(&bytes).map_err(|_| "Invalid JSON")?;
                        let action = path.rsplit('/').next().unwrap_or("");
                        let result = if action == "verify" {
                            verify(
                                &s,
                                body["id"].as_str().ok_or("Missing connection ID")?,
                                &SystemVault,
                            )
                        } else {
                            s.mutate(action, &body, &SystemVault)
                        };
                        if let Some(Value::String(token)) = body.get_mut("token") {
                            zeroize::Zeroize::zeroize(token)
                        }
                        result
                    })())
                } else {
                    http(404, "application/json", b"{\"error\":\"Unknown route\"}")
                }
            }
            _ => return Err("Unknown method".into()),
        })
    })();
    match result {
        Ok(v) => json!({"ok":true,"result":v}),
        Err(e) => json!({"ok":false,"error":{"code":"plugin_error","message":e}}),
    }
}
#[cfg(test)]
mod tests;
