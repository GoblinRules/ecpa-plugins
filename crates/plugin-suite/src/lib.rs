mod abi;
mod mcp;
mod records;
mod settings;
mod tools;
use agent_files::storage::{self, bad, Result};
use base64::{engine::general_purpose::STANDARD, Engine};
use serde_json::{json, Value};
use settings::Settings;
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, path::PathBuf, time::Instant};

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum Mode {
    Profiles,
    Mcp,
    Diagnostics,
    Prompts,
    Snapshots,
    Skills,
}
struct Preview {
    token: String,
    created: Instant,
    changes: Vec<Value>,
}
pub struct App {
    id: &'static str,
    title: &'static str,
    version: &'static str,
    repository: &'static str,
    mode: Mode,
    settings: Option<Settings>,
    preview: Option<Preview>,
}
impl App {
    pub fn new(
        id: &'static str,
        title: &'static str,
        mode: Mode,
        version: &'static str,
        repository: &'static str,
    ) -> Self {
        Self {
            id,
            title,
            version,
            repository,
            mode,
            settings: None,
            preview: None,
        }
    }
    pub fn dispatch(&mut self, method: &str, raw: &[u8]) -> Value {
        let result = match method {
            "plugin.register" | "plugin.reconfigure" => {
                match Settings::parse(raw, self.id) {
                    Ok(settings) => {
                        self.settings = Some(settings);
                        self.preview = None;
                    }
                    Err((_, message)) => {
                        return json!({"ok":false,"error":{"code":"invalid_config","message":message}})
                    }
                }
                json!({"schema_version":6,"metadata":{"Name":self.title,"Version":self.version,"Author":"GoblinRules","Logo":format!("https://raw.githubusercontent.com/GoblinRules/ecpa-plugins/master/assets/icons/{}.svg",self.id),"GitHubRepository":self.repository,"ConfigFields":settings::fields(self.mode)},"capabilities":{"management_api":true}})
            }
            "management.register" => {
                let routes: Vec<_> = self.routes().iter().map(|(method, path)| json!({"Method":method,"Path":format!("/v0/management/{}/{path}",self.id)})).collect();
                json!({"resources":[{"Path":"/editor","Menu":self.title,"Description":self.title}],"routes":routes})
            }
            "management.handle" => match serde_json::from_slice(raw) {
                Ok(req) => self.handle(&req),
                Err(_) => http_json(400, json!({"error":"Invalid request"})),
            },
            _ => {
                return json!({"ok":false,"error":{"code":"unknown_method","message":"Unknown method"}})
            }
        };
        json!({"ok":true,"result":result})
    }
    fn routes(&self) -> Vec<(&'static str, &'static str)> {
        let mut routes = vec![("GET", "state")];
        match self.mode {
            Mode::Profiles | Mode::Snapshots => routes.extend([
                ("POST", "record"),
                ("DELETE", "record"),
                ("POST", "preview"),
                ("POST", "apply"),
            ]),
            Mode::Prompts => routes.extend([("POST", "record"), ("DELETE", "record")]),
            Mode::Mcp | Mode::Skills => routes.extend([
                ("POST", "preview"),
                ("POST", "apply"),
                ("GET", "backups"),
                ("POST", "restore-preview"),
            ]),
            Mode::Diagnostics => (),
        }
        routes
    }
    fn handle(&mut self, req: &Value) -> Value {
        let path = req["Path"].as_str().unwrap_or("");
        let method = req["Method"].as_str().unwrap_or("");
        if method == "GET" && path == format!("/v0/resource/plugins/{}/editor", self.id) {
            let template = if self.mode == Mode::Mcp {
                include_str!("../web/mcp.html")
            } else {
                include_str!("../web/app.html")
            };
            let html = template
                .replace("__MCP_STYLES__", include_str!("../web/mcp.css"))
                .replace("__PLUGIN_ID__", self.id)
                .replace("__PLUGIN_TITLE__", self.title)
                .replace("__PLUGIN_ICON__", agent_files::icons::plugin(self.id))
                .replace(
                    "__AGENT_ICONS__",
                    include_str!("../../../assets/agents/icons.js"),
                );
            return http(200, "text/html; charset=utf-8", html.as_bytes());
        }
        let endpoint = self
            .routes()
            .into_iter()
            .find(|(m, p)| method == *m && path == format!("/v0/management/{}/{p}", self.id));
        let Some((_, endpoint)) = endpoint else {
            return http_json(404, json!({"error":"Unknown route"}));
        };
        let result = (|| -> Result<Value> {
            let settings = self
                .settings
                .clone()
                .ok_or_else(|| bad("Plugin is not configured"))?;
            if method == "GET" {
                return if endpoint == "state" {
                    self.state(&settings)
                } else {
                    let id = req["Query"]["id"][0]
                        .as_str()
                        .ok_or_else(|| bad("Missing id"))?;
                    storage::single(self.target(&settings, id)?).backups("document")
                };
            }
            let encoded = req["Body"].as_str().ok_or_else(|| bad("Missing body"))?;
            if encoded.len() > 16 * storage::LIMIT {
                return Err((413, "Request too large".into()));
            }
            let bytes = STANDARD
                .decode(encoded)
                .map_err(|_| bad("Invalid body encoding"))?;
            let body: Value = serde_json::from_slice(&bytes).map_err(|_| bad("Invalid JSON"))?;
            match endpoint {
                "record" => records::save(&settings, self.mode, &body, method == "DELETE"),
                "preview" => self.prepare(&settings, &body),
                "restore-preview" => self.restore_preview(&settings, &body),
                "apply" => self.apply(&settings, &body),
                _ => Err(bad("Unknown action")),
            }
        })();
        match result {
            Ok(v) => http_json(200, v),
            Err((status, error)) => http_json(status, json!({"error":error})),
        }
    }
    fn state(&self, settings: &Settings) -> Result<Value> {
        let mut state = json!({"title":self.title,"mode":match self.mode {Mode::Profiles=>"profiles",Mode::Mcp=>"mcp",Mode::Diagnostics=>"diagnostics",Mode::Prompts=>"prompts",Mode::Snapshots=>"snapshots",Mode::Skills=>"skills"}});
        match self.mode {
            Mode::Profiles | Mode::Snapshots => {
                state["files"] = files(settings.targets(self.mode == Mode::Snapshots)?);
                state["library"] = records::read(settings)?;
            }
            Mode::Prompts => state["library"] = records::read(settings)?,
            Mode::Mcp => state["files"] = tools::mcp_files(settings),
            Mode::Diagnostics => state["files"] = tools::diagnose(settings)?,
            Mode::Skills => {
                state["files"] = tools::skills(settings)?;
                state["roots"] = json!(settings.skills);
            }
        }
        Ok(state)
    }
    fn target(&self, settings: &Settings, id: &str) -> Result<PathBuf> {
        if self.mode == Mode::Skills {
            return tools::skill_path(settings, id);
        }
        let paths = if self.mode == Mode::Mcp {
            settings.configs.clone()
        } else {
            settings.targets(self.mode == Mode::Snapshots)?
        };
        paths.get(id).cloned().ok_or_else(|| bad("Unknown target"))
    }
    fn prepare(&mut self, settings: &Settings, body: &Value) -> Result<Value> {
        self.preview = None;
        let changes = if matches!(self.mode, Mode::Profiles | Mode::Snapshots) {
            records::preview(settings, self.mode, body)?
        } else if self.mode == Mode::Mcp && body.get("operation").is_some() {
            mcp::preview(settings, body)?
        } else {
            let id = text(body, "id")?;
            let current = read_target(id, self.target(settings, id)?)?;
            if current["version"] != body["version"]
                && !(self.mode == Mode::Skills
                    && current["exists"] == false
                    && body["version"].is_null())
            {
                return Err((
                    409,
                    "File or location changed. Reload before preparing a preview.".into(),
                ));
            }
            let content = text(body, "content")?;
            let after = if self.mode == Mode::Mcp {
                tools::merge_mcp(id, text(&current, "content")?, content)?
            } else {
                tools::validate_skill(content)?;
                content.into()
            };
            vec![change(current, after)]
        };
        self.set_preview(changes)
    }
    fn set_preview(&mut self, changes: Vec<Value>) -> Result<Value> {
        let nonce = tempfile::NamedTempFile::new().map_err(|e| (500, e.to_string()))?;
        let token = format!(
            "{:x}",
            Sha256::digest(format!("{}{:?}", json!(changes), nonce.path()).as_bytes())
        );
        self.preview = Some(Preview {
            token: token.clone(),
            created: Instant::now(),
            changes: changes.clone(),
        });
        Ok(json!({"token":token,"changes":changes,"expiresInSeconds":300}))
    }
    fn restore_preview(&mut self, settings: &Settings, body: &Value) -> Result<Value> {
        self.preview = None;
        let id = text(body, "id")?;
        let path = self.target(settings, id)?;
        let current = read_target(id, path.clone())?;
        if current["version"] != body["version"] {
            return Err((409, "File changed. Reload first.".into()));
        }
        let backup = text(body, "backup")?;
        if backup.len() != 67
            || !backup.ends_with(".md")
            || !backup.as_bytes()[..64]
                .iter()
                .all(|c| c.is_ascii_hexdigit())
        {
            return Err(bad("Invalid backup"));
        }
        let backup_path = storage::single(path).backup_dir("document")?.join(backup);
        let saved = read_target(id, backup_path)?;
        let content = text(&saved, "content")?;
        if !saved["exists"].as_bool().unwrap_or(false)
            || format!("{:x}.md", Sha256::digest(content.as_bytes())) != backup
        {
            return Err(bad("Backup missing or checksum mismatch"));
        }
        if self.mode == Mode::Skills {
            tools::validate_skill(content)?;
        } else {
            tools::validate_config(id, content)?;
        }
        self.set_preview(vec![change(current, content.into())])
    }
    fn apply(&mut self, settings: &Settings, body: &Value) -> Result<Value> {
        let token = text(body, "token")?;
        let preview = self
            .preview
            .take()
            .ok_or_else(|| bad("Preview expired or already used. Preview again."))?;
        if token != preview.token || preview.created.elapsed().as_secs() > 300 {
            return Err(bad("Preview expired or invalid. Preview again."));
        }
        // Validate every target before starting a batch. Each write rechecks its version.
        for item in &preview.changes {
            let id = text(item, "id")?;
            let current = read_target(id, self.target(settings, id)?)?;
            if current["version"] != item["version"] {
                return Err((
                    409,
                    "A target changed since preview. No files were written; preview again.".into(),
                ));
            }
        }
        let mut results = vec![];
        for item in &preview.changes {
            let id = text(item, "id")?;
            let path = self.target(settings, id)?;
            match storage::single(path).save(
                "document",
                text(item, "version")?,
                text(item, "after")?,
            ) {
                Ok(_) => results.push(json!({"id":id,"saved":true})),
                Err((_, error)) => {
                    results.push(json!({"id":id,"saved":false,"error":error}));
                    return Ok(
                        json!({"status":"partial","results":results,"message":"Stopped after a write failed. Review saved files and their backups before retrying."}),
                    );
                }
            }
        }
        Ok(json!({"status":"applied","results":results}))
    }
}
fn text<'a>(v: &'a Value, key: &str) -> Result<&'a str> {
    v[key]
        .as_str()
        .ok_or_else(|| bad(&format!("Missing {key}")))
}
fn read_target(id: &str, path: PathBuf) -> Result<Value> {
    let mut v = storage::single(path).read("document")?;
    v["id"] = json!(id);
    Ok(v)
}
fn files(paths: BTreeMap<String, PathBuf>) -> Value {
    json!(paths
        .into_iter()
        .map(|(id, path)| read_target(&id, path.clone())
            .unwrap_or_else(|(_, error)| json!({"id":id,"path":path,"error":error})))
        .collect::<Vec<_>>())
}
fn change(current: Value, after: String) -> Value {
    json!({"id":current["id"],"path":current["path"],"version":current["version"],"exists":current["exists"],"before":current["content"],"after":after})
}
fn http(status: u16, mime: &str, body: &[u8]) -> Value {
    json!({"StatusCode":status,"Headers":{"Content-Type":[mime],"Cache-Control":["no-store"],"X-Content-Type-Options":["nosniff"],"Referrer-Policy":["no-referrer"],"Content-Security-Policy":["default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src data:; base-uri 'none'; form-action 'none'"]},"Body":STANDARD.encode(body)})
}
fn http_json(status: u16, value: Value) -> Value {
    http(
        status,
        "application/json; charset=utf-8",
        value.to_string().as_bytes(),
    )
}

#[cfg(test)]
mod tests;
