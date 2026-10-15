//! Per-server edits. Translation is deliberately limited to fields with known equivalents.
use super::*;
use std::collections::BTreeSet;

fn translate(definition: &Value, source: &str, target: &str) -> Result<Value> {
    let map = definition
        .as_object()
        .ok_or_else(|| bad("Server settings must be an object"))?;
    if source == target {
        return Ok(definition.clone());
    }
    let remote = definition.get("url").is_some();
    let allowed: &[&str] = if source == "claude-config" {
        if remote {
            &["type", "url", "headers"]
        } else {
            &["type", "command", "args", "env"]
        }
    } else if remote {
        &["url", "http_headers"]
    } else {
        &["command", "args", "env"]
    };
    let unsupported: Vec<_> = map
        .keys()
        .filter(|key| !allowed.contains(&key.as_str()))
        .cloned()
        .collect();
    if !unsupported.is_empty() {
        return Err(bad(&format!("Cannot translate these client-specific fields: {}. Edit this agent alone, or create a separate definition for the other agent.", unsupported.join(", "))));
    }
    if source == "claude-config" {
        let kind = definition["type"].as_str();
        if remote && !matches!(kind, Some("http" | "streamable-http")) {
            return Err(bad("Only Streamable HTTP remote servers can be copied to Codex. SSE and WebSocket are not translated."));
        }
        if !remote && kind.is_some() && kind != Some("stdio") {
            return Err(bad("Local servers must use stdio transport"));
        }
    }
    let mut result = map.clone();
    result.remove("type");
    if target == "claude-config" {
        result.insert("type".into(), json!(if remote { "http" } else { "stdio" }));
        if let Some(headers) = result.remove("http_headers") {
            result.insert("headers".into(), headers);
        }
    } else if let Some(headers) = result.remove("headers") {
        result.insert("http_headers".into(), headers);
    }
    Ok(Value::Object(result))
}

fn validate_fields(server: &Value) -> Result<()> {
    for field in ["env", "headers", "http_headers", "env_http_headers"] {
        if let Some(value) = server.get(field) {
            if value
                .as_object()
                .is_none_or(|map| map.values().any(|v| !v.is_string()))
            {
                return Err(bad(&format!("{field} must be an object of string values")));
            }
        }
    }
    Ok(())
}

pub fn preview(settings: &Settings, body: &Value) -> Result<Vec<Value>> {
    let operation = text(body, "operation")?;
    if !matches!(operation, "upsert" | "delete") {
        return Err(bad("Unknown server operation"));
    }
    let source = text(body, "source")?;
    let path = settings
        .configs
        .get(source)
        .ok_or_else(|| bad("Unknown source agent"))?;
    let current_source = read_target(source, path.clone())?;
    if current_source["version"] != body["sourceVersion"] {
        return Err((
            409,
            "Source configuration changed. Reload before previewing.".into(),
        ));
    }
    let original = body["originalName"].as_str().unwrap_or("");
    let source_servers = tools::mcp_value(source, text(&current_source, "content")?)?;
    if !original.is_empty() && source_servers.get(original).is_none() {
        return Err(bad("The original server no longer exists"));
    }
    let name = text(body, "name")?;
    if name.trim().is_empty() || name.len() > 128 || name.chars().any(char::is_control) {
        return Err(bad(
            "Server name must be 1–128 bytes without control characters",
        ));
    }
    let targets = body["targets"]
        .as_array()
        .ok_or_else(|| bad("Select at least one agent"))?;
    if targets.is_empty() || targets.len() > settings.configs.len() {
        return Err(bad("Select at least one supported agent"));
    }
    if operation == "delete"
        && (targets.len() != 1 || targets[0]["id"] != source || name != original)
    {
        return Err(bad("Remove a server from its source agent only"));
    }
    if operation == "upsert" {
        validate_fields(&body["definition"])?;
        // Check the definition in its source format before any translation.
        tools::merge_mcp(source, "", &json!({name:body["definition"]}).to_string())?;
    }
    let mut seen = BTreeSet::new();
    let mut changes = vec![];
    for target in targets {
        let id = text(target, "id")?;
        if !seen.insert(id) {
            return Err(bad("Duplicate target agent"));
        }
        let path = settings
            .configs
            .get(id)
            .ok_or_else(|| bad("Unknown target agent"))?;
        let current = read_target(id, path.clone())?;
        if current["version"] != target["version"] {
            return Err((
                409,
                "A target configuration changed. Reload before previewing.".into(),
            ));
        }
        let mut servers = tools::mcp_value(id, text(&current, "content")?)?;
        let map = servers.as_object_mut().unwrap();
        if operation == "delete" {
            map.remove(name);
        } else {
            let definition = translate(&body["definition"], source, id)?;
            let editing_original = id == source && name == original;
            if let Some(existing) = map.get(name) {
                if !editing_original && existing != &definition && body["replaceExisting"] != true {
                    return Err((409, format!("Server '{name}' already exists in {id}. Enable replacement to preview overwriting it.")));
                }
            }
            if id == source && !original.is_empty() && original != name {
                map.remove(original);
            }
            map.insert(name.into(), definition);
        }
        let after = tools::merge_mcp(id, text(&current, "content")?, &servers.to_string())?;
        if after != text(&current, "content")? {
            changes.push(change(current, after));
        }
    }
    if changes.is_empty() {
        return Err(bad("No changes to apply"));
    }
    Ok(changes)
}
