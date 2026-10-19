use crate::vault::Vault;
use fs2::FileExt;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs::{self, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
};
use zeroize::Zeroizing;

#[derive(Clone, Serialize, Deserialize, Debug)]
#[serde(deny_unknown_fields)]
pub struct Connection {
    pub id: String,
    pub name: String,
    pub service: String,
    pub account_id: String,
}
#[derive(Clone, Serialize, Deserialize, Debug)]
#[serde(deny_unknown_fields)]
pub struct Assignment {
    pub path: String,
    pub cloudflare: Option<String>,
    pub github: Option<String>,
}
#[derive(Default, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Catalogue {
    pub connections: Vec<Connection>,
    pub projects: Vec<Assignment>,
}
pub struct Store {
    pub dir: PathBuf,
}
pub fn default_dir() -> Result<PathBuf, String> {
    std::env::var_os("LOCALAPPDATA")
        .map(|p| PathBuf::from(p).join("ECPA").join("connections-manager"))
        .ok_or("LOCALAPPDATA is unavailable; specify an absolute data directory".into())
}
pub fn valid_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= 64
        && id
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
}
pub fn validate(c: &Connection) -> Result<(), String> {
    if !valid_id(&c.id) || c.name.trim().is_empty() || c.name.len() > 100 {
        return Err("Use a lowercase connection ID (letters, digits, hyphens) and a name up to 100 characters".into());
    }
    match c.service.as_str() {
        "cloudflare"
            if c.account_id.len() == 32 && c.account_id.bytes().all(|b| b.is_ascii_hexdigit()) =>
        {
            Ok(())
        }
        "github" if c.account_id.is_empty() => Ok(()),
        _ => Err("Choose GitHub or supply a 32-character Cloudflare account ID".into()),
    }
}
pub fn project_path(path: &str) -> Result<String, String> {
    let p = Path::new(path);
    if !p.is_absolute() || !p.is_dir() {
        return Err("Project must be an existing absolute directory on this device".into());
    }
    let value = fs::canonicalize(p)
        .map_err(|_| "Cannot resolve project directory")?
        .to_string_lossy()
        .into_owned();
    Ok(if cfg!(windows) {
        value.to_lowercase()
    } else {
        value
    })
}
impl Store {
    pub fn new(dir: PathBuf) -> Result<Self, String> {
        if !dir.is_absolute() {
            return Err("data_dir must be absolute".into());
        }
        Ok(Self { dir })
    }
    pub fn target(&self, id: &str) -> String {
        format!(
            "ECPA/Connections/{:x}/{id}",
            Sha256::digest(self.dir.to_string_lossy().as_bytes())
        )
    }
    pub fn load(&self) -> Result<(Catalogue, String), String> {
        let bytes = match fs::read(self.dir.join("connections.json")) {
            Ok(b) => b,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                b"{\"connections\":[],\"projects\":[]}".to_vec()
            }
            Err(_) => return Err("Cannot read connection catalogue".into()),
        };
        if bytes.len() > 1024 * 1024 {
            return Err("Connection catalogue is too large".into());
        }
        let data: Catalogue = serde_json::from_slice(&bytes)
            .map_err(|_| "Invalid connection catalogue; restore a valid copy before editing")?;
        let mut ids = std::collections::HashSet::new();
        for c in &data.connections {
            validate(c)?;
            if !ids.insert(&c.id) {
                return Err("Duplicate connection IDs".into());
            }
        }
        Ok((data, format!("{:x}", Sha256::digest(&bytes))))
    }
    pub fn state(&self, vault: &impl Vault) -> Result<Value, String> {
        let (data, version) = self.load()?;
        Ok(
            json!({"connections":data.connections.iter().map(|c|{let mut v=serde_json::to_value(c).unwrap();v["hasCredential"]=json!(vault.read(&self.target(&c.id)).is_ok());v}).collect::<Vec<_>>(),"projects":data.projects,"version":version,"dataDir":self.dir,"platformSupported":cfg!(windows)}),
        )
    }
    pub fn lock(&self, exclusive: bool) -> Result<std::fs::File, String> {
        fs::create_dir_all(&self.dir).map_err(|_| "Cannot create data directory")?;
        let lock = OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(self.dir.join("catalogue.lock"))
            .map_err(|_| "Cannot lock catalogue")?;
        (if exclusive {
            lock.try_lock_exclusive()
        } else {
            FileExt::try_lock_shared(&lock)
        })
        .map_err(|_| "Another connection operation is in progress; retry")?;
        Ok(lock)
    }
    pub fn mutate(&self, action: &str, body: &Value, vault: &impl Vault) -> Result<Value, String> {
        let _lock = self.lock(true)?;
        let (mut data, version) = self.load()?;
        if body["version"].as_str() != Some(&version) {
            return Err("Connections changed. Reload before saving.".into());
        }
        let mut rollback: Option<(String, Option<Zeroizing<String>>)> = None;

        match action {
            "save" => {
                let c: Connection = serde_json::from_value(body["connection"].clone())
                    .map_err(|_| "Invalid connection fields")?;
                validate(&c)?;
                if let Some(old) = data.connections.iter().find(|old| old.id == c.id) {
                    if old.service != c.service {
                        return Err(
                            "A connection's service cannot change; create another connection"
                                .into(),
                        );
                    }
                }
                let token = body["token"].as_str().unwrap_or("").trim();
                let target = self.target(&c.id);
                if !token.is_empty() {
                    if token.len() > 2500 || token.chars().any(char::is_control) {
                        return Err("Invalid token".into());
                    }
                    rollback = Some((target.clone(), vault.read(&target).ok()));
                    vault.write(&target, token)?;
                } else if vault.read(&target).is_err() {
                    return Err("Enter a token for this connection".into());
                }
                data.connections.retain(|old| old.id != c.id);
                data.connections.push(c);
            }
            "delete" => {
                let id = body["id"].as_str().ok_or("Missing connection ID")?;
                if !valid_id(id) {
                    return Err("Invalid connection ID".into());
                }
                if data
                    .projects
                    .iter()
                    .any(|p| p.cloudflare.as_deref() == Some(id) || p.github.as_deref() == Some(id))
                {
                    return Err("Remove this connection from project assignments first".into());
                }
                if !data.connections.iter().any(|c| c.id == id) {
                    return Err("Connection not found".into());
                }
                data.connections.retain(|c| c.id != id);
                let target = self.target(id);
                rollback = Some((target.clone(), vault.read(&target).ok()));
                vault.delete(&target)?;
            }
            "assign" => {
                let mut p: Assignment = serde_json::from_value(body["project"].clone())
                    .map_err(|_| "Invalid project assignment")?;
                p.path = project_path(&p.path)?;
                for (service, id) in [("cloudflare", &p.cloudflare), ("github", &p.github)] {
                    if let Some(id) = id {
                        if !data
                            .connections
                            .iter()
                            .any(|c| c.id == *id && c.service == service)
                        {
                            return Err(
                                "Project references a missing connection or wrong service".into()
                            );
                        }
                    }
                }
                data.projects.retain(|old| old.path != p.path);
                if p.cloudflare.is_some() || p.github.is_some() {
                    data.projects.push(p)
                }
            }
            _ => return Err("Unknown operation".into()),
        }
        let save = (|| -> Result<(), String> {
            let mut f = tempfile::NamedTempFile::new_in(&self.dir)
                .map_err(|_| "Cannot create catalogue")?;
            f.write_all(&serde_json::to_vec_pretty(&data).map_err(|_| "Cannot encode catalogue")?)
                .map_err(|_| "Cannot write catalogue")?;
            f.as_file()
                .sync_all()
                .map_err(|_| "Cannot flush catalogue")?;
            f.persist(self.dir.join("connections.json"))
                .map_err(|_| "Cannot replace catalogue")?;
            Ok(())
        })();
        if let Err(e) = save {
            if let Some((target, old)) = rollback {
                let restored = match old {
                    Some(secret) => vault.write(&target, &secret),
                    None => vault.delete(&target),
                };
                if restored.is_err() {
                    return Err("Catalogue write and credential rollback failed; re-save the connection token".into());
                }
            }
            return Err(e);
        }
        self.state(vault)
    }
    pub fn selected(
        &self,
        connection: Option<&str>,
        project: Option<&str>,
    ) -> Result<Vec<Connection>, String> {
        let (data, _) = self.load()?;
        if let Some(id) = connection {
            return data
                .connections
                .into_iter()
                .find(|c| c.id == id)
                .map(|c| vec![c])
                .ok_or("Connection not found".into());
        }
        let cwd = project_path(project.ok_or("Choose --connection or --project")?)?;
        let p = data
            .projects
            .iter()
            .filter(|p| Path::new(&cwd).starts_with(&p.path))
            .max_by_key(|p| p.path.len())
            .ok_or("No project assignment matches this directory")?;
        let mut selected = vec![];
        for (service, id) in [("cloudflare", &p.cloudflare), ("github", &p.github)] {
            if let Some(id) = id {
                selected.push(
                    data.connections
                        .iter()
                        .find(|c| c.id == *id && c.service == service)
                        .ok_or("Broken project assignment")?
                        .clone(),
                )
            }
        }
        if selected.is_empty() {
            return Err("Project has no connections".into());
        }
        Ok(selected)
    }
}
pub fn environment(
    connections: &[Connection],
    store: &Store,
    vault: &impl Vault,
) -> Result<BTreeMap<String, Zeroizing<String>>, String> {
    let mut result = BTreeMap::new();
    for c in connections {
        let token = vault.read(&store.target(&c.id))?;
        match c.service.as_str() {
            "cloudflare" => {
                result.insert("CLOUDFLARE_API_TOKEN".into(), token);
                result.insert(
                    "CLOUDFLARE_ACCOUNT_ID".into(),
                    Zeroizing::new(c.account_id.clone()),
                );
            }
            "github" => {
                result.insert("GH_TOKEN".into(), token.clone());
                result.insert("GITHUB_TOKEN".into(), token.clone());
                result.insert("GITHUB_PERSONAL_ACCESS_TOKEN".into(), token);
                result.insert("GH_HOST".into(), Zeroizing::new("github.com".into()));
            }
            _ => return Err("Unsupported service".into()),
        }
    }
    Ok(result)
}
