//! The plugin is a management surface; MCP sessions run in the separate SDK worker.
use crate::{
    store::Store,
    vault::{SystemVault, Vault},
};
use serde_json::{json, Value};
use std::{io::Read, time::Duration};

pub fn request(store: &Store, body: &Value) -> Result<Value, String> {
    let raw = std::fs::read(store.dir.join("gateway-runtime.json"))
        .map_err(|_| "MCP runtime is not configured. Run the gateway installer/setup; existing account connections are unchanged.")?;
    if raw.len() > 32768 {
        return Err("Invalid gateway runtime settings".into());
    }
    let config: Value =
        serde_json::from_slice(&raw).map_err(|_| "Invalid gateway runtime settings")?;
    let url = url::Url::parse(config["url"].as_str().ok_or("Missing runtime URL")?)
        .map_err(|_| "Invalid runtime URL")?;
    // A local plugin may not forward its admin credential to arbitrary hosts.
    if url.scheme() != "http"
        || url.host_str() != Some("127.0.0.1")
        || url.path() != "/mcp"
        || !url.username().is_empty()
        || url.password().is_some()
        || url.query().is_some()
        || url.fragment().is_some()
    {
        return Err("This plugin management bridge requires a local loopback worker. Use an explicit local tunnel for remote management.".into());
    }
    let target = config["identities"]["admin"]["vault_target"]
        .as_str()
        .ok_or("Missing runtime management credential reference")?;
    if !target.starts_with("ECPA/MCP/") || !target.ends_with("/admin") {
        return Err("Invalid runtime management credential reference".into());
    }
    let token = SystemVault.read(target)?;
    let client = ureq::AgentBuilder::new()
        .timeout(Duration::from_secs(55))
        .redirects(0)
        .build();
    let endpoint = format!(
        "http://127.0.0.1:{}/admin",
        url.port_or_known_default().ok_or("Missing runtime port")?
    );
    let response = match client.post(&endpoint).set("Authorization", &format!("Bearer {}", &*token)).send_json(body) {
        Ok(r) | Err(ureq::Error::Status(400, r)) => r,
        Err(_) => return Err("MCP runtime is unavailable or authentication failed. Start the configured worker and verify its status.".into()),
    };
    let mut bytes = Vec::new();
    response
        .into_reader()
        .take(2_097_153)
        .read_to_end(&mut bytes)
        .map_err(|_| "Cannot read runtime response")?;
    if bytes.len() > 2_097_152 {
        return Err("Runtime response exceeded its limit".into());
    }
    let result: Value = serde_json::from_slice(&bytes).map_err(|_| "Invalid runtime response")?;
    if let Some(e) = result["error"].as_str() {
        return Err(e.to_string());
    }
    Ok(result)
}

pub fn resource() -> Value {
    json!({"Path":"/gateway","Menu":"","Description":"Managed MCP services and agent gateway setup"})
}
