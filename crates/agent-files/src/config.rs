use base64::{engine::general_purpose::STANDARD, Engine};
use serde_json::{json, Value};
use std::{collections::BTreeMap, path::PathBuf};

pub type Paths = BTreeMap<String, PathBuf>;
const FILES: [(&str, &str, &str); 8] = [
    ("claude", "claude_path", "Claude Code CLAUDE.md"),
    ("codex", "codex_path", "Codex AGENTS.md"),
    (
        "codex-override",
        "codex_override_path",
        "Codex AGENTS.override.md",
    ),
    ("kimi", "kimi_path", "Kimi Code AGENTS.md"),
    ("grok", "grok_path", "Grok Build AGENTS.md"),
    ("zcode", "zcode_path", "Z.ai / ZCode AGENTS.md"),
    ("antigravity", "antigravity_path", "Antigravity GEMINI.md"),
    (
        "antigravity-agents",
        "antigravity_agents_path",
        "Antigravity AGENTS.md",
    ),
];

pub fn fields() -> Value {
    Value::Array(FILES.iter().map(|(_, key, label)| json!({
        "Name": key, "Type": "string", "Default": "",
        "Description": format!("{label}: absolute file path on the core machine. Leave blank for the default location. Does not move files or configure the agent.")
    })).collect())
}

pub fn parse(raw: &[u8]) -> Result<Paths, String> {
    let request: Value = serde_json::from_slice(raw).map_err(|_| "Invalid lifecycle request")?;
    let Some(encoded) = request.get("config_yaml").filter(|v| !v.is_null()) else {
        return Ok(Paths::new());
    };
    let bytes = STANDARD
        .decode(encoded.as_str().ok_or("Invalid configuration encoding")?)
        .map_err(|_| "Invalid configuration encoding")?;
    if bytes.is_empty() {
        return Ok(Paths::new());
    }
    let value: Value =
        serde_yaml_ng::from_slice(&bytes).map_err(|_| "Invalid plugin configuration YAML")?;
    let object = value
        .as_object()
        .ok_or("Plugin configuration must be a mapping")?;
    let mut paths = Paths::new();
    for (id, key, _) in FILES {
        let Some(value) = object.get(key).filter(|v| !v.is_null()) else {
            continue;
        };
        let text = value
            .as_str()
            .ok_or_else(|| format!("{key} must be a string"))?;
        if text.trim().is_empty() {
            continue;
        }
        let path = PathBuf::from(text);
        if !path.is_absolute() || path.file_name().is_none() || text.contains('\0') || path.is_dir()
        {
            return Err(format!(
                "{key} must be an absolute file path, including the filename"
            ));
        }
        paths.insert(id.to_owned(), path);
    }
    Ok(paths)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn config(yaml: &str) -> Result<Paths, String> {
        parse(
            json!({"config_yaml": STANDARD.encode(yaml)})
                .to_string()
                .as_bytes(),
        )
    }
    #[test]
    fn defaults_and_invalid_values() {
        assert!(config("enabled: true\nclaude_path: ''\ncodex_path: null")
            .unwrap()
            .is_empty());
        for yaml in ["claude_path: relative.md", "codex_path: 42", "[]", "bad: ["] {
            assert!(config(yaml).is_err(), "{yaml}");
        }
    }
    #[test]
    fn all_overrides_and_paths_with_spaces() {
        let temp = tempfile::tempdir().unwrap();
        let path = temp.path().join("custom folder/my rules.md");
        let mut object = serde_json::Map::new();
        for (_, key, _) in FILES {
            object.insert(key.into(), json!(path));
        }
        let result = config(&Value::Object(object).to_string()).unwrap();
        assert_eq!(result.len(), 8);
        assert!(result.values().all(|p| p == &path));
        assert!(config(&json!({"claude_path": temp.path()}).to_string()).is_err());
    }
}
