use agent_files::{
    config,
    storage::{bad, Result, Store},
};
use base64::{engine::general_purpose::STANDARD, Engine};
use serde_json::{json, Value};
use std::{collections::BTreeMap, path::PathBuf};

#[derive(Clone)]
pub struct Settings {
    pub instructions: config::Paths,
    pub data: PathBuf,
    pub configs: BTreeMap<String, PathBuf>,
    pub skills: BTreeMap<String, PathBuf>,
}
impl Settings {
    pub fn parse(raw: &[u8], id: &str) -> Result<Self> {
        let instructions = config::parse(raw).map_err(|e| bad(&e))?;
        let store = Store::discover(instructions.clone())?;
        let req: Value =
            serde_json::from_slice(raw).map_err(|_| bad("Invalid lifecycle request"))?;
        let bytes = match req["config_yaml"].as_str() {
            Some(s) => STANDARD
                .decode(s)
                .map_err(|_| bad("Invalid configuration encoding"))?,
            None => vec![],
        };
        let values: Value = if bytes.is_empty() {
            json!({})
        } else {
            serde_yaml_ng::from_slice(&bytes).map_err(|_| bad("Invalid configuration YAML"))?
        };
        let path = |key: &str, default: PathBuf, directory: bool| -> Result<PathBuf> {
            let value = values.get(key).filter(|v| !v.is_null());
            let text = match value {
                Some(v) => v
                    .as_str()
                    .ok_or_else(|| bad(&format!("{key} must be a string")))?,
                None => "",
            };
            let p = if text.trim().is_empty() {
                default
            } else {
                PathBuf::from(text)
            };
            if !p.is_absolute()
                || text.contains('\0')
                || (!directory && (p.file_name().is_none() || p.is_dir()))
                || (directory && p.is_file())
            {
                return Err(bad(&format!(
                    "{key} must be an absolute {} path",
                    if directory { "directory" } else { "file" }
                )));
            }
            Ok(p)
        };
        let data = path("data_dir", store.home.join(".ecpa-plugins").join(id), true)?;
        let configs = [
            (
                "claude-config".into(),
                path("claude_config_path", store.home.join(".claude.json"), false)?,
            ),
            (
                "codex-config".into(),
                path("codex_config_path", store.codex.join("config.toml"), false)?,
            ),
        ]
        .into_iter()
        .collect();
        let mut skills: BTreeMap<String, PathBuf> = [
            (
                "claude".into(),
                path("claude_skills_dir", store.claude.join("skills"), true)?,
            ),
            (
                "codex".into(),
                path("codex_skills_dir", store.home.join(".agents/skills"), true)?,
            ),
        ]
        .into_iter()
        .collect();
        if values
            .get("extra_skills_dir")
            .and_then(Value::as_str)
            .is_some_and(|s| !s.trim().is_empty())
        {
            skills.insert(
                "extra".into(),
                path("extra_skills_dir", store.home.clone(), true)?,
            );
        }
        Ok(Self {
            instructions,
            data,
            configs,
            skills,
        })
    }
    pub fn targets(&self, include_configs: bool) -> Result<BTreeMap<String, PathBuf>> {
        let store = Store::discover(self.instructions.clone())?;
        let mut paths = BTreeMap::new();
        for id in [
            "claude",
            "codex",
            "codex-override",
            "kimi",
            "grok",
            "zcode",
            "antigravity",
            "antigravity-agents",
        ] {
            paths.insert(id.into(), store.path(id)?);
        }
        if include_configs {
            paths.extend(self.configs.clone());
        }
        Ok(paths)
    }
}
pub fn fields(mode: crate::Mode) -> Value {
    use crate::Mode::*;
    let mut fields = if matches!(mode, Profiles | Diagnostics | Snapshots) {
        config::fields().as_array().unwrap().clone()
    } else {
        vec![]
    };
    let mut add = |key: &str, description: &str| {
        fields.push(json!({"Name":key,"Type":"string","Default":"","Description":description}))
    };
    if matches!(mode, Profiles | Prompts | Snapshots) {
        add("data_dir", "Absolute storage directory. Blank uses ~/.ecpa-plugins/<plugin-id>. Local data and backups are not encrypted.");
    }
    if matches!(mode, Mcp | Diagnostics | Snapshots) {
        add(
            "claude_config_path",
            "Claude Code user JSON file. Blank uses ~/.claude.json. Include the filename.",
        );
        add(
            "codex_config_path",
            "Codex TOML file. Blank uses CODEX_HOME/config.toml (default ~/.codex/config.toml).",
        );
    }
    if matches!(mode, Skills) {
        add(
            "claude_skills_dir",
            "Claude Code skills directory. Blank uses ~/.claude/skills.",
        );
        add(
            "codex_skills_dir",
            "Codex skills directory. Blank uses ~/.agents/skills.",
        );
        add("extra_skills_dir", "Optional additional skills root, e.g. a project's .agents/skills or legacy ~/.codex/skills.");
    }
    Value::Array(fields)
}
