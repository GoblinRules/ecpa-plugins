use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::{Read, Write},
    path::{Path, PathBuf},
};

pub const LIMIT: usize = 1024 * 1024;
pub type Result<T> = std::result::Result<T, (u16, String)>;
fn io(e: std::io::Error) -> (u16, String) {
    (500, e.to_string())
}
pub fn bad(message: &str) -> (u16, String) {
    (400, message.into())
}
fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

pub struct Store {
    pub overrides: crate::config::Paths,
    pub claude: PathBuf,
    pub codex: PathBuf,
    pub home: PathBuf,
    pub kimi: PathBuf,
}
impl Store {
    pub fn discover(overrides: crate::config::Paths) -> Result<Self> {
        // Explicit plugin-level override supports portable profiles and isolated tests.
        let home = std::env::var_os("AGENT_INSTRUCTIONS_HOME")
            .filter(|v| !v.is_empty())
            .map(PathBuf::from)
            .or_else(dirs::home_dir)
            .ok_or_else(|| bad("Cannot determine the proxy user's home directory"))?;
        if !home.is_absolute() {
            return Err(bad("AGENT_INSTRUCTIONS_HOME must be an absolute path"));
        }
        let env_path = |name: &str, default: PathBuf| -> Result<PathBuf> {
            let p = std::env::var_os(name)
                .filter(|v| !v.is_empty())
                .map(PathBuf::from)
                .unwrap_or(default);
            if !p.is_absolute() {
                return Err(bad(
                    "Agent home environment variables must use absolute paths",
                ));
            }
            Ok(p)
        };
        Ok(Self {
            overrides,
            claude: env_path("CLAUDE_CONFIG_DIR", home.join(".claude"))?,
            codex: env_path("CODEX_HOME", home.join(".codex"))?,
            kimi: env_path("KIMI_CODE_HOME", home.join(".kimi-code"))?,
            home,
        })
    }
    pub fn path(&self, id: &str) -> Result<PathBuf> {
        if let Some(path) = self.overrides.get(id) {
            return Ok(path.clone());
        }
        match id {
            "claude" => Ok(self.claude.join("CLAUDE.md")),
            "codex" => Ok(self.codex.join("AGENTS.md")),
            "codex-override" => Ok(self.codex.join("AGENTS.override.md")),
            "kimi" => Ok(self.kimi.join("AGENTS.md")),
            "grok" => Ok(self.home.join(".grok/AGENTS.md")),
            "zcode" => Ok(self.home.join(".zcode/AGENTS.md")),
            "antigravity" => Ok(self.home.join(".gemini/GEMINI.md")),
            "antigravity-agents" => Ok(self.home.join(".gemini/AGENTS.md")),
            _ => Err(bad("Unknown instruction file")),
        }
    }
    pub fn backup_dir(&self, id: &str) -> Result<PathBuf> {
        let p = self.path(id)?;
        let namespace = if id == "document" {
            hash(p.to_string_lossy().as_bytes())
        } else {
            id.into()
        };
        Ok(p.parent()
            .unwrap()
            .join(".agent-instructions-backups")
            .join(namespace))
    }
    pub fn read(&self, id: &str) -> Result<Value> {
        let p = self.path(id)?;
        let bytes = read_file(&p)?;
        let content = String::from_utf8(bytes.clone().unwrap_or_default())
            .map_err(|_| bad("File is not UTF-8; edit it externally"))?;
        let override_state = if !matches!(id, "codex" | "codex-override") {
            Ok(None)
        } else {
            read_file(&self.path("codex-override")?)
        };
        let precedence_warning = override_state
            .as_ref()
            .err()
            .map(|(_, e)| format!("Cannot inspect Codex override: {e}"));
        let override_active = override_state
            .ok()
            .flatten()
            .is_some_and(|b| !String::from_utf8_lossy(&b).trim().is_empty());
        Ok(
            json!({"id": id, "path": p, "exists": bytes.is_some(), "content": content,
            "version": version(&p, bytes.as_deref()), "overrideActive": override_active, "precedenceWarning": precedence_warning}),
        )
    }
    pub fn list(&self) -> Result<Value> {
        let mut files = vec![];
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
            // A damaged file must not prevent access to the other agent's files.
            files.push(match self.read(id) {
                Ok(v) => v,
                Err((_, e)) => json!({"id": id, "path": self.path(id)?, "error": e}),
            });
        }
        Ok(json!({"files": files}))
    }
    pub fn backups(&self, id: &str) -> Result<Value> {
        let dir = self.backup_dir(id)?;
        check_links(&dir)?;
        let mut items = vec![];
        if dir.exists() {
            for entry in fs::read_dir(&dir).map_err(io)? {
                let entry = entry.map_err(io)?;
                let name = entry.file_name().to_string_lossy().into_owned();
                if valid_backup(&name) && entry.file_type().map_err(io)?.is_file() {
                    let meta = entry.metadata().map_err(io)?;
                    let modified = meta
                        .modified()
                        .ok()
                        .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
                        .map(|t| t.as_secs())
                        .unwrap_or(0);
                    items.push(json!({"name": name, "modified": modified, "bytes": meta.len()}));
                }
            }
        }
        items.sort_by_key(|v| std::cmp::Reverse(v["modified"].as_u64().unwrap_or(0)));
        Ok(json!({"backups": items}))
    }
    pub fn save(&self, id: &str, expected: &str, content: &str) -> Result<Value> {
        self.write(id, expected, content.as_bytes(), true)
    }
    fn write(
        &self,
        id: &str,
        expected: &str,
        content: &[u8],
        preserve_newlines: bool,
    ) -> Result<Value> {
        if content.len() > LIMIT {
            return Err((413, "Instruction file exceeds 1 MiB".into()));
        }
        let p = self.path(id)?;
        let before = read_file(&p)?;
        if version(&p, before.as_deref()) != expected {
            return Err((
                409,
                "File or configured location changed. Copy your draft, then reload before saving."
                    .into(),
            ));
        }
        let mut data = content.to_vec();
        if preserve_newlines
            && before
                .as_ref()
                .is_some_and(|b| b.windows(2).any(|w| w == b"\r\n"))
        {
            data = String::from_utf8_lossy(content)
                .replace("\r\n", "\n")
                .replace('\n', "\r\n")
                .into_bytes();
        }
        if data.len() > LIMIT {
            return Err((413, "Instruction file exceeds 1 MiB".into()));
        }
        if before.as_deref() == Some(data.as_slice()) {
            return self.read(id);
        }
        let parent = p.parent().unwrap();
        check_links(parent)?;
        fs::create_dir_all(parent).map_err(io)?;
        if let Some(old) = &before {
            let dir = self.backup_dir(id)?;
            check_links(&dir)?;
            fs::create_dir_all(&dir).map_err(io)?;
            let backup = dir.join(format!("{}.md", hash(old)));
            if !backup.exists() {
                let mut tmp = tempfile::NamedTempFile::new_in(&dir).map_err(io)?;
                tmp.write_all(old).map_err(io)?;
                tmp.as_file().sync_all().map_err(io)?;
                tmp.persist_noclobber(&backup).map_err(|e| io(e.error))?;
            }
        }
        let mut tmp = tempfile::NamedTempFile::new_in(parent).map_err(io)?;
        tmp.write_all(&data).map_err(io)?;
        if before.is_some() {
            tmp.as_file()
                .set_permissions(fs::metadata(&p).map_err(io)?.permissions())
                .map_err(io)?;
        }
        tmp.as_file().sync_all().map_err(io)?;
        if version(&p, read_file(&p)?.as_deref()) != expected {
            return Err((
                409,
                "File changed while saving; your draft has not been written".into(),
            ));
        }
        tmp.persist(&p).map_err(|e| io(e.error))?;
        self.read(id)
    }
    pub fn restore(&self, id: &str, expected: &str, name: &str) -> Result<Value> {
        if !valid_backup(name) {
            return Err(bad("Invalid backup identifier"));
        }
        let bytes =
            read_file(&self.backup_dir(id)?.join(name))?.ok_or((404, "Backup not found".into()))?;
        if format!("{}.md", hash(&bytes)) != name {
            return Err(bad("Backup checksum does not match"));
        }
        std::str::from_utf8(&bytes).map_err(|_| bad("Backup is not UTF-8"))?;
        self.write(id, expected, &bytes, false)
    }
}
fn valid_backup(s: &str) -> bool {
    s.len() == 67 && s.ends_with(".md") && s.as_bytes()[..64].iter().all(|b| b.is_ascii_hexdigit())
}
fn version(path: &Path, b: Option<&[u8]>) -> String {
    // Bind even a missing/empty file to its location, preventing stale drafts
    // from being written to a newly configured target with identical contents.
    hash(
        format!(
            "{}\0{}",
            path.display(),
            b.map(hash).unwrap_or_else(|| "missing".into())
        )
        .as_bytes(),
    )
}
pub fn check_links(p: &Path) -> Result<()> {
    for ancestor in p.ancestors() {
        match fs::symlink_metadata(ancestor) {
            Ok(m) => {
                #[cfg(windows)]
                {
                    use std::os::windows::fs::MetadataExt;
                    if m.file_attributes() & 0x400 != 0 {
                        return Err(bad("Linked files or directories are not supported"));
                    }
                }
                if m.file_type().is_symlink() {
                    return Err(bad("Linked files or directories are not supported"));
                }
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
            Err(e) => return Err(io(e)),
        }
    }
    Ok(())
}
fn read_file(p: &Path) -> Result<Option<Vec<u8>>> {
    check_links(p)?;
    let f = match fs::File::open(p) {
        Ok(f) => f,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(e) => return Err(io(e)),
    };
    if !f.metadata().map_err(io)?.is_file() {
        return Err(bad("Expected a regular instruction file"));
    }
    let mut bytes = vec![];
    f.take((LIMIT + 1) as u64)
        .read_to_end(&mut bytes)
        .map_err(io)?;
    if bytes.len() > LIMIT {
        return Err((413, "Instruction file exceeds 1 MiB".into()));
    }
    Ok(Some(bytes))
}

/// A single explicitly configured file, using the same backup/conflict protections.
pub fn single(path: PathBuf) -> Store {
    Store {
        overrides: [("document".into(), path)].into_iter().collect(),
        claude: PathBuf::new(),
        codex: PathBuf::new(),
        home: PathBuf::new(),
        kimi: PathBuf::new(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn setup() -> (tempfile::TempDir, Store) {
        let d = tempfile::tempdir().unwrap();
        let s = Store {
            overrides: crate::config::Paths::new(),
            claude: d.path().join("claude"),
            codex: d.path().join("codex"),
            home: d.path().to_path_buf(),
            kimi: d.path().join("kimi-code"),
        };
        (d, s)
    }
    #[test]
    fn create_conflict_backup_restore() {
        let (_d, s) = setup();
        let first = s
            .save(
                "claude",
                s.read("claude").unwrap()["version"].as_str().unwrap(),
                "original\r\n",
            )
            .unwrap();
        assert_eq!(s.save("claude", "missing", "bad").unwrap_err().0, 409);
        let second = s
            .save("claude", first["version"].as_str().unwrap(), "edited\n")
            .unwrap();
        assert_eq!(second["content"], "edited\r\n");
        let backups = s.backups("claude").unwrap();
        let restored = s
            .restore(
                "claude",
                second["version"].as_str().unwrap(),
                backups["backups"][0]["name"].as_str().unwrap(),
            )
            .unwrap();
        assert_eq!(restored["content"], "original\r\n");
        assert_eq!(
            s.backups("claude").unwrap()["backups"]
                .as_array()
                .unwrap()
                .len(),
            2
        );
    }
    #[test]
    fn changing_missing_target_rejects_stale_save() {
        let (d, mut s) = setup();
        let before = s.read("claude").unwrap();
        let target = d.path().join("alternate/rules.md");
        s.overrides.insert("claude".into(), target.clone());
        assert_eq!(
            s.save("claude", before["version"].as_str().unwrap(), "stale")
                .unwrap_err()
                .0,
            409
        );
        assert!(!target.exists());
        let current = s.read("claude").unwrap();
        s.save("claude", current["version"].as_str().unwrap(), "custom")
            .unwrap();
        assert_eq!(fs::read_to_string(target).unwrap(), "custom");
    }
    #[test]
    fn external_edit_and_missing_are_distinct() {
        let (_d, s) = setup();
        let v = s
            .save(
                "codex",
                s.read("codex").unwrap()["version"].as_str().unwrap(),
                "",
            )
            .unwrap();
        fs::write(s.path("codex").unwrap(), "external").unwrap();
        assert_eq!(
            s.save("codex", v["version"].as_str().unwrap(), "draft")
                .unwrap_err()
                .0,
            409
        );
        assert_eq!(
            fs::read_to_string(s.path("codex").unwrap()).unwrap(),
            "external"
        );
    }
    #[test]
    fn reject_paths_large_files_and_corrupt_backups() {
        let (_d, s) = setup();
        assert!(s.read("../secret").is_err());
        assert!(s
            .restore(
                "claude",
                s.read("claude").unwrap()["version"].as_str().unwrap(),
                "../../secret"
            )
            .is_err());
        assert_eq!(
            s.save(
                "claude",
                s.read("claude").unwrap()["version"].as_str().unwrap(),
                &"x".repeat(LIMIT + 1)
            )
            .unwrap_err()
            .0,
            413
        );
        let v = s
            .save(
                "claude",
                s.read("claude").unwrap()["version"].as_str().unwrap(),
                "a",
            )
            .unwrap();
        s.save("claude", v["version"].as_str().unwrap(), "b")
            .unwrap();
        let b = s.backups("claude").unwrap();
        let name = b["backups"][0]["name"].as_str().unwrap();
        fs::write(s.backup_dir("claude").unwrap().join(name), "tampered").unwrap();
        assert!(s.restore("claude", "anything", name).is_err());
    }
    #[test]
    fn override_and_invalid_utf8() {
        let (_d, s) = setup();
        s.save(
            "codex-override",
            s.read("codex-override").unwrap()["version"]
                .as_str()
                .unwrap(),
            "rules",
        )
        .unwrap();
        assert_eq!(s.read("codex").unwrap()["overrideActive"], true);
        fs::create_dir_all(&s.claude).unwrap();
        fs::write(s.path("claude").unwrap(), [255]).unwrap();
        assert!(s.read("claude").is_err());
        assert!(s.list().unwrap()["files"][0]["error"].is_string());
    }
    #[test]
    fn invalid_override_does_not_block_claude_or_saving_codex() {
        let (_d, s) = setup();
        fs::create_dir_all(s.path("codex-override").unwrap()).unwrap();
        assert!(s.read("claude").is_ok());
        let saved = s
            .save(
                "codex",
                s.read("codex").unwrap()["version"].as_str().unwrap(),
                "rules",
            )
            .unwrap();
        assert!(saved["precedenceWarning"].is_string());
        assert!(!valid_backup(&format!("{}é.md", "a".repeat(62))));
    }
}
