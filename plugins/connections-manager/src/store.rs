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
    #[serde(default)]
    pub base_url: String,
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
    if c.service != "portainer" && !c.base_url.is_empty() {
        return Err("URL is only supported for Portainer".into());
    }
    match c.service.as_str() {
        "cloudflare"
            if c.account_id.len() == 32 && c.account_id.bytes().all(|b| b.is_ascii_hexdigit()) =>
        {
            Ok(())
        }
        "github" if c.account_id.is_empty() => Ok(()),
        "portainer" if c.account_id.is_empty() => crate::portainer::validate_url(&c.base_url),
        _ => Err("Choose GitHub, Portainer with a server URL, or Cloudflare with a 32-character account ID".into()),
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
        let path = self.dir.to_string_lossy();
        let path = if cfg!(windows) {
            path.replace('/', "\\")
        } else {
            path.into_owned()
        };
        credential_target(&path, id)
    }
    // Keep old slash-only and exact input spellings readable. Do not enumerate
    // unrelated vault entries or merge different catalogue directories.
    fn targets(&self, id: &str) -> Vec<String> {
        let mut targets = vec![self.target(id)];
        if cfg!(windows) {
            let path = self.dir.to_string_lossy();
            for spelling in [path.to_string(), path.replace('\\', "/")] {
                let target = credential_target(&spelling, id);
                if !targets.contains(&target) {
                    targets.push(target);
                }
            }
        }
        targets
    }
    pub fn credential(&self, id: &str, vault: &impl Vault) -> Result<Zeroizing<String>, String> {
        let mut found: Option<Zeroizing<String>> = None;
        for target in self.targets(id) {
            if let Ok(token) = vault.read(&target) {
                if found.as_ref().is_some_and(|old| **old != *token) {
                    return Err("Conflicting credentials for Windows path spellings. Re-save the intended token in Connections Manager before using this account.".into());
                }
                found = Some(token);
            }
        }
        found.ok_or("Credential unavailable for this Windows user and catalogue directory. Check --data-dir and the helper's Windows user before re-saving the token.".into())
    }
    fn change_credentials(
        &self,
        id: &str,
        token: Option<&str>,
        vault: &impl Vault,
    ) -> Result<Vec<CredentialBackup>, String> {
        let targets = self.targets(id);
        let backups: Vec<_> = targets
            .into_iter()
            .map(|target| {
                let old = vault.read(&target).ok();
                (target, old)
            })
            .collect();
        for (index, (target, old)) in backups.iter().enumerate() {
            // Refresh existing legacy entries too so older helpers cannot read
            // stale tokens. Only create the normalized entry for new accounts.
            let result = match token {
                Some(token) if index == 0 || old.is_some() => vault.write(target, token),
                Some(_) => Ok(()),
                None => vault.delete(target),
            };
            if let Err(error) = result {
                restore_credentials(&backups, vault)?;
                return Err(error);
            }
        }
        Ok(backups)
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
            json!({"connections":data.connections.iter().map(|c|{let mut v=serde_json::to_value(c).unwrap();v["hasCredential"]=json!(self.credential(&c.id, vault).is_ok());v}).collect::<Vec<_>>(),"projects":data.projects,"version":version,"dataDir":self.dir,"platformSupported":cfg!(windows)}),
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
        let mut rollback = Vec::new();

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
                if data
                    .connections
                    .iter()
                    .any(|old| old.id == c.id && old.base_url != c.base_url)
                    && body["token"].as_str().unwrap_or("").trim().is_empty()
                {
                    return Err("Re-enter the token when changing the Portainer URL".into());
                }
                let token = body["token"].as_str().unwrap_or("").trim();
                if !token.is_empty() {
                    if token.len() > 2500 || token.chars().any(char::is_control) {
                        return Err("Invalid token".into());
                    }
                    rollback = self.change_credentials(&c.id, Some(token), vault)?;
                } else {
                    self.credential(&c.id, vault)?;
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
                rollback = self.change_credentials(id, None, vault)?;
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
            restore_credentials(&rollback, vault)?;
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
        let token = store.credential(&c.id, vault)?;
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

type CredentialBackup = (String, Option<Zeroizing<String>>);
fn credential_target(path: &str, id: &str) -> String {
    format!(
        "ECPA/Connections/{:x}/{id}",
        Sha256::digest(path.as_bytes())
    )
}
fn restore_credentials(backups: &[CredentialBackup], vault: &impl Vault) -> Result<(), String> {
    let mut failed = false;
    for (target, old) in backups {
        let result = match old {
            Some(token) => vault.write(target, token),
            None => vault.delete(target),
        };
        failed |= result.is_err();
    }
    if failed {
        Err("Credential rollback failed; re-save the intended connection token".into())
    } else {
        Ok(())
    }
}
