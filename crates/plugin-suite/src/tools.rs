use super::*;
use std::fs;
use toml_edit::{DocumentMut, Item};

pub fn validate_config(id: &str, content: &str) -> Result<()> {
    if id == "claude-config" {
        let v: Value =
            serde_json::from_str(content).map_err(|e| bad(&format!("Invalid JSON: {e}")))?;
        if !v.is_object() {
            return Err(bad("Claude configuration must be an object"));
        }
    } else if id == "codex-config" {
        content
            .parse::<DocumentMut>()
            .map_err(|_| bad("Invalid TOML syntax"))?;
    }
    Ok(())
}
fn mcp_value(id: &str, content: &str) -> Result<Value> {
    if content.is_empty() {
        return Ok(json!({}));
    }
    validate_config(id, content)?;
    let v: Value = if id == "claude-config" {
        serde_json::from_str(content).unwrap()
    } else {
        toml_edit::de::from_str(content).map_err(|e| bad(&e.to_string()))?
    };
    let key = if id == "claude-config" {
        "mcpServers"
    } else {
        "mcp_servers"
    };
    let value = v.get(key).cloned().unwrap_or(json!({}));
    if !value.is_object() {
        return Err(bad("MCP servers must be a mapping"));
    }
    Ok(value)
}
pub fn merge_mcp(id: &str, before: &str, content: &str) -> Result<String> {
    // Validate the old document as well: never replace a damaged config with defaults.
    mcp_value(id, before)?;
    let servers: Value =
        serde_json::from_str(content).map_err(|e| bad(&format!("Invalid server JSON: {e}")))?;
    let map = servers
        .as_object()
        .ok_or_else(|| bad("Enter an object mapping server names to their settings"))?;
    for (name, server) in map {
        if name.trim().is_empty() || !server.is_object() {
            return Err(bad("Each server needs a name and settings object"));
        }
        let command = server["command"]
            .as_str()
            .is_some_and(|s| !s.trim().is_empty());
        let url = server["url"].as_str().is_some_and(|s| {
            s.starts_with("https://")
                || s.starts_with("http://")
                || (id == "claude-config" && (s.starts_with("wss://") || s.starts_with("ws://")))
        });
        if command == url {
            return Err(bad(
                "Each server must have exactly one non-empty command or supported URL",
            ));
        }
        if id == "claude-config"
            && url
            && !matches!(
                server["type"].as_str(),
                Some("http" | "streamable-http" | "sse" | "ws")
            )
        {
            return Err(bad("Claude remote servers need type http, sse, or ws"));
        }
        if let Some(args) = server.get("args") {
            if args
                .as_array()
                .is_none_or(|a| a.iter().any(|v| !v.is_string()))
            {
                return Err(bad("Server args must be an array of strings"));
            }
        }
    }
    if id == "claude-config" {
        let mut root: Value = if before.is_empty() {
            json!({})
        } else {
            serde_json::from_str(before).unwrap()
        };
        root["mcpServers"] = servers;
        Ok(format!(
            "{}\n",
            serde_json::to_string_pretty(&root).unwrap()
        ))
    } else {
        let mut doc = before
            .parse::<DocumentMut>()
            .map_err(|e| bad(&e.to_string()))?;
        let new = toml_edit::ser::to_document(&servers)
            .map_err(|e| bad(&format!("Server values cannot be represented as TOML: {e}")))?;
        doc["mcp_servers"] = Item::Table(new.as_table().clone());
        Ok(doc.to_string())
    }
}
pub fn mcp_files(settings: &Settings) -> Value {
    json!(settings
        .configs
        .iter()
        .map(|(id, path)| {
            match read_target(id, path.clone()) {
                Ok(mut v) => match mcp_value(id, v["content"].as_str().unwrap()) {
                    Ok(servers) => {
                        v["content"] = json!(serde_json::to_string_pretty(&servers).unwrap());
                        v["serverCount"] = json!(servers.as_object().unwrap().len());
                        v
                    }
                    Err((_, error)) => json!({"id":id,"path":path,"error":error}),
                },
                Err((_, error)) => json!({"id":id,"path":path,"error":error}),
            }
        })
        .collect::<Vec<_>>())
}
pub fn diagnose(settings: &Settings) -> Result<Value> {
    let mut rows = vec![];
    for (id, path) in settings.targets(true)? {
        match read_target(&id, path.clone()) {
            Ok(file) => {
                let content = text(&file, "content")?;
                let issue = if file["exists"] == true {
                    validate_config(&id, content).err().map(|(_, e)| e)
                } else {
                    None
                };
                let readonly = fs::metadata(&path)
                    .ok()
                    .is_some_and(|m| m.permissions().readonly());
                rows.push(json!({"id":id,"path":path,"exists":file["exists"],"bytes":content.len(),"status":if issue.is_some(){"invalid"}else if file["exists"]!=true{"missing"}else if readonly{"read-only"}else{"readable"},"message":issue.unwrap_or_else(|| if id=="codex-override"&&!content.trim().is_empty(){"Non-empty override takes precedence over Codex AGENTS.md.".into()}else{"Read checks only; write access and agent loading are not tested.".into()})}));
            }
            Err((_, error)) => {
                rows.push(json!({"id":id,"path":path,"status":"error","message":error}))
            }
        }
    }
    Ok(json!(rows))
}
pub fn skill_path(settings: &Settings, id: &str) -> Result<PathBuf> {
    let (root, name) = id
        .split_once('/')
        .ok_or_else(|| bad("Select a skills root and folder name"))?;
    if name.is_empty()
        || name.len() > 64
        || name.starts_with('.')
        || !name
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || c == b'-' || c == b'_')
    {
        return Err(bad(
            "Skill folder name must use letters, numbers, hyphens or underscores",
        ));
    }
    let base = settings
        .skills
        .get(root)
        .ok_or_else(|| bad("Unknown skills root"))?;
    let path = base.join(name).join("SKILL.md");
    storage::check_links(&path)?;
    Ok(path)
}
pub fn validate_skill(content: &str) -> Result<()> {
    let normalized = content.replace("\r\n", "\n");
    let source = normalized
        .strip_prefix("---\n")
        .ok_or_else(|| bad("SKILL.md needs YAML frontmatter between --- lines"))?;
    let mut lines = vec![];
    let mut closed = false;
    for line in source.lines() {
        if line == "---" {
            closed = true;
            break;
        }
        lines.push(line);
    }
    if !closed {
        return Err(bad("Skill frontmatter needs a closing --- line"));
    }
    let front = lines.join("\n");
    let meta: Value = serde_yaml_ng::from_str(&front)
        .map_err(|e| bad(&format!("Invalid skill frontmatter: {e}")))?;
    for key in ["name", "description"] {
        if meta[key].as_str().is_none_or(|s| s.trim().is_empty()) {
            return Err(bad(&format!("Skill frontmatter needs {key}")));
        }
    }
    Ok(())
}
pub fn skills(settings: &Settings) -> Result<Value> {
    let mut rows = vec![];
    for (root, base) in &settings.skills {
        if let Err((_, error)) = storage::check_links(base) {
            rows.push(json!({"id":root,"path":base,"error":error}));
            continue;
        }
        let entries = match fs::read_dir(base) {
            Ok(v) => v,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => continue,
            Err(e) => {
                rows.push(json!({"id":root,"path":base,"error":e.to_string()}));
                continue;
            }
        };
        for entry in entries {
            if rows.len() >= 500 {
                return Err(bad(
                    "Too many skills; configure a smaller skills root (maximum 500 entries)",
                ));
            }
            let entry = entry.map_err(|e| (500, e.to_string()))?;
            let name = entry.file_name().to_string_lossy().into_owned();
            if name.starts_with('.') {
                continue;
            }
            let id = format!("{root}/{name}");
            let path = entry.path().join("SKILL.md");
            match skill_path(settings, &id).and_then(|p| read_target(&id, p)) {
                Ok(mut v) if v["exists"] == true => {
                    v["validation"] =
                        json!(validate_skill(text(&v, "content")?).err().map(|(_, e)| e));
                    rows.push(v);
                }
                Ok(_) => (),
                Err((_, error)) => rows.push(json!({"id":id,"path":path,"error":error})),
            }
        }
    }
    rows.sort_by_key(|v| v["id"].as_str().unwrap_or("").to_owned());
    Ok(json!(rows))
}
