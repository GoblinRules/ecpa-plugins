use base64::{
    engine::general_purpose::{STANDARD, STANDARD_NO_PAD},
    Engine,
};
use fs2::FileExt;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::{Read, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::{Duration, Instant},
};

#[derive(Clone, Serialize, Deserialize, Debug)]
#[serde(deny_unknown_fields)]
pub struct Machine {
    pub id: String,
    pub name: String,
    pub host: String,
    pub port: u16,
    pub user: String,
    pub os: String,
    pub auth: String,
    pub identity_file: String,
    pub host_key: String,
    #[serde(default)]
    pub labels: Vec<String>,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Catalogue {
    schema_version: u8,
    machines: Vec<Machine>,
}

pub fn id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 48
        && value
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
}
pub fn target(host: &str, user: &str, port: u16) -> Result<(), String> {
    if host.is_empty()
        || host.len() > 253
        || !host.as_bytes()[0].is_ascii_alphanumeric()
        || !host
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b".-:".contains(&b))
        || user.is_empty()
        || user.len() > 80
        || !user.as_bytes()[0].is_ascii_alphanumeric()
        || !user
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"._-\\".contains(&b))
        || port == 0
    {
        return Err(
            "Use a hostname/IP, SSH username and port; no URLs, options or shell syntax.".into(),
        );
    }
    Ok(())
}
pub fn fingerprint(key: &str) -> Result<String, String> {
    let parts: Vec<_> = key.split_whitespace().collect();
    if parts.len() != 2 || !["ssh-ed25519", "ecdsa-sha2-nistp256", "ssh-rsa"].contains(&parts[0]) {
        return Err("Use one OpenSSH public host key: key-type and base64 only.".into());
    }
    let raw = STANDARD
        .decode(parts[1])
        .map_err(|_| "Invalid host-key encoding")?;
    if raw.len() < 32 || raw.len() > 2048 {
        return Err("Invalid host-key size".into());
    }
    let n = u32::from_be_bytes(raw[..4].try_into().unwrap()) as usize;
    if n > raw.len() - 4 || raw[4..4 + n] != *parts[0].as_bytes() {
        return Err("Host-key type does not match its encoded payload".into());
    }
    Ok(format!(
        "SHA256:{}",
        STANDARD_NO_PAD.encode(Sha256::digest(&raw))
    ))
}
pub fn validate(m: &Machine) -> Result<(), String> {
    target(&m.host, &m.user, m.port)?;
    if !id(&m.id)
        || m.name.trim().is_empty()
        || m.name.len() > 100
        || !["linux", "windows"].contains(&m.os.as_str())
        || !["key-file", "agent"].contains(&m.auth.as_str())
    {
        return Err(
            "Choose a stable profile ID, display name, remote OS and supported key method.".into(),
        );
    }
    if m.labels.len() > 12 || m.labels.iter().any(|s| !id(s)) {
        return Err("Use up to twelve short lowercase labels.".into());
    }
    let path = Path::new(&m.identity_file);
    if !path.is_absolute() || !path.is_file() || m.identity_file.contains(['\n', '\r', '\0']) {
        return Err("Select an existing absolute key file on the ECPA host. Private key contents are never sent to this page.".into());
    }
    if m.auth == "agent" && path.extension().and_then(|s| s.to_str()) != Some("pub") {
        return Err(
            "Agent mode requires the matching .pub file to select exactly one identity.".into(),
        );
    }
    fingerprint(&m.host_key)?;
    Ok(())
}
fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn write(path: &Path, bytes: &[u8]) -> Result<(), String> {
    let mut temp = tempfile::NamedTempFile::new_in(path.parent().ok_or("Missing parent")?)
        .map_err(|_| "Cannot prepare file")?;
    temp.write_all(bytes)
        .and_then(|_| temp.as_file().sync_all())
        .map_err(|_| "Cannot save file")?;
    temp.persist(path)
        .map_err(|_| "Cannot replace file; check permissions")?;
    Ok(())
}
pub struct Store {
    pub dir: PathBuf,
}
impl Store {
    pub fn new(dir: PathBuf) -> Result<Self, String> {
        if !dir.is_absolute() {
            return Err("Use an absolute machine catalogue directory".into());
        }
        fs::create_dir_all(&dir).map_err(|_| "Cannot create catalogue directory")?;
        Ok(Self {
            dir: fs::canonicalize(dir).map_err(|_| "Cannot resolve catalogue directory")?,
        })
    }
    fn load(&self) -> Result<(Catalogue, String), String> {
        let path = self.dir.join("machines.json");
        let raw = if path.exists() {
            fs::read(path).map_err(|_| "Cannot read machine catalogue")?
        } else {
            b"{\"schema_version\":1,\"machines\":[]}".to_vec()
        };
        if raw.len() > 512 * 1024 {
            return Err("Machine catalogue exceeds size limit".into());
        }
        let data: Catalogue = serde_json::from_slice(&raw)
            .map_err(|_| "Invalid machine catalogue; restore its backup")?;
        if data.schema_version != 1 {
            return Err("Unsupported machine catalogue version".into());
        }
        Ok((data, hash(&raw)))
    }
    pub fn state(&self) -> Result<Value, String> {
        let (data, version) = self.load()?;
        Ok(
            json!({"machines":data.machines,"version":version,"executionHost":std::env::var("COMPUTERNAME").unwrap_or_else(|_|"this ECPA host".into()),"sshAvailable":ssh_path("ssh").is_file(),"runnerIntegration":"SSH profiles do not register T3 runners or grant agent execution permissions."}),
        )
    }
    pub fn selected(&self, selected: &str) -> Result<Machine, String> {
        self.load()?
            .0
            .machines
            .into_iter()
            .find(|m| m.id == selected)
            .ok_or("Machine profile not found".into())
    }
    pub fn save(&self, m: Machine, version: &str, reviewed: &str) -> Result<Value, String> {
        validate(&m)?;
        if fingerprint(&m.host_key)? != reviewed {
            return Err(
                "Independently verify and enter the exact SHA256 host fingerprint before saving."
                    .into(),
            );
        }
        let lock = fs::OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(self.dir.join("machines.lock"))
            .map_err(|_| "Cannot lock catalogue")?;
        lock.lock_exclusive().map_err(|_| "Cannot lock catalogue")?;
        let (mut data, current) = self.load()?;
        if current != version {
            return Err("Machine catalogue changed; refresh and review again.".into());
        }
        data.machines.retain(|old| old.id != m.id);
        data.machines.push(m);
        self.commit(&data)?;
        self.state()
    }
    fn commit(&self, data: &Catalogue) -> Result<(), String> {
        let path = self.dir.join("machines.json");
        if path.exists() {
            write(
                &self.dir.join("machines.before.json"),
                &fs::read(&path).map_err(|_| "Cannot back up catalogue")?,
            )?;
        }
        write(
            &path,
            &serde_json::to_vec_pretty(data).map_err(|_| "Cannot encode catalogue")?,
        )
    }
    pub fn remove(&self, selected: &str, version: &str) -> Result<Value, String> {
        let lock = fs::OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(self.dir.join("machines.lock"))
            .map_err(|_| "Cannot lock catalogue")?;
        lock.lock_exclusive().map_err(|_| "Cannot lock catalogue")?;
        let (mut data, current) = self.load()?;
        if current != version {
            return Err("Machine catalogue changed; refresh first.".into());
        }
        data.machines.retain(|m| m.id != selected);
        self.commit(&data)?;
        self.state()
    }
    pub fn export(&self) -> Result<Value, String> {
        Ok(
            json!({"catalogue":self.load()?.0,"warning":"Private machine metadata and key paths: save locally, never publish this export. Private key bytes and passwords are not included."}),
        )
    }
    pub fn terminal(&self, selected: &str) -> Result<Value, String> {
        let m = self.selected(selected)?;
        validate(&m)?;
        let keys = self.dir.join("terminal-host-keys");
        fs::create_dir_all(&keys).map_err(|_| "Cannot create host-key directory")?;
        let path = keys.join(format!("{}.known_hosts", m.id));
        write(&path, format!("ecpa-{} {}\n", m.id, m.host_key).as_bytes())?;
        let args = ssh_args(&m, &path, true);
        let quote = |s: &str| format!("'{}'", s.replace('\'', "''"));
        let command = format!(
            "& {} {}",
            quote(&ssh_path("ssh").to_string_lossy()),
            args.iter().map(|s| quote(s)).collect::<Vec<_>>().join(" ")
        );
        Ok(
            json!({"command":command,"message":"Run this command on the ECPA host under its key-owning Windows identity. A terminal is unrestricted SSH access; it is not an agent permission or a read-only session."}),
        )
    }
}
pub fn ssh_path(name: &str) -> PathBuf {
    #[cfg(windows)]
    {
        PathBuf::from(std::env::var_os("SYSTEMROOT").unwrap_or_else(|| "C:\\Windows".into()))
            .join("System32/OpenSSH")
            .join(format!("{name}.exe"))
    }
    #[cfg(not(windows))]
    {
        PathBuf::from("/usr/bin").join(name)
    }
}
pub fn ssh_args(m: &Machine, known: &Path, interactive: bool) -> Vec<String> {
    let null = if cfg!(windows) { "NUL" } else { "/dev/null" };
    let mut args = vec!["-F".into(), null.into()];
    for option in [
        "StrictHostKeyChecking=yes",
        "UpdateHostKeys=no",
        "PasswordAuthentication=no",
        "KbdInteractiveAuthentication=no",
        "PreferredAuthentications=publickey",
        "IdentitiesOnly=yes",
        "ForwardAgent=no",
        "ClearAllForwardings=yes",
        "PermitLocalCommand=no",
        "ControlMaster=no",
        "ControlPath=none",
        "ProxyCommand=none",
        "ProxyJump=none",
        "CanonicalizeHostname=no",
        "ConnectTimeout=5",
        "ConnectionAttempts=1",
        "ServerAliveInterval=5",
        "ServerAliveCountMax=1",
    ] {
        args.extend(["-o".into(), option.into()]);
    }
    for option in [
        format!("UserKnownHostsFile=\"{}\"", ssh_file(known)),
        format!("GlobalKnownHostsFile={null}"),
        format!("HostKeyAlias=ecpa-{}", m.id),
        format!("BatchMode={}", if interactive { "no" } else { "yes" }),
        format!("RequestTTY={}", if interactive { "force" } else { "no" }),
    ] {
        args.extend(["-o".into(), option]);
    }
    if m.auth == "key-file" {
        args.extend(["-o".into(), "IdentityAgent=none".into()]);
    }
    args.extend([
        "-i".into(),
        ssh_file(Path::new(&m.identity_file)),
        "-p".into(),
        m.port.to_string(),
        "-l".into(),
        m.user.clone(),
        m.host.clone(),
    ]);
    if !interactive {
        args.push(
            if m.os == "windows" {
                "cmd.exe /d /c ver & whoami"
            } else {
                "uname -s; id -un"
            }
            .into(),
        );
    }
    args
}
fn ssh_file(path: &Path) -> String {
    // std::fs::canonicalize returns Windows verbatim paths; Win32 OpenSSH rejects them.
    let raw = path.to_string_lossy();
    let normal = if let Some(value) = raw.strip_prefix(r"\\?\UNC\") {
        format!("//{value}")
    } else {
        raw.strip_prefix(r"\\?\").unwrap_or(&raw).to_string()
    };
    normal.replace('\\', "/").replace('"', "\\\"")
}
fn run(executable: &Path, args: &[String]) -> Result<String, String> {
    if !executable.is_file() {
        return Err("Install Windows OpenSSH Client on the ECPA host first.".into());
    }
    let mut command = Command::new(executable);
    command
        .args(args)
        .env_clear()
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    for name in [
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "HOME",
        "SSH_AUTH_SOCK",
        "PROGRAMDATA",
        "ALLUSERSPROFILE",
        "SYSTEMDRIVE",
        "LOCALAPPDATA",
        "APPDATA",
        "PATH",
        "USERNAME",
        "USERDOMAIN",
        "HOMEDRIVE",
        "HOMEPATH",
        "COMSPEC",
    ] {
        if let Some(value) = std::env::var_os(name) {
            command.env(name, value);
        }
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let mut child = command
        .spawn()
        .map_err(|_| "Cannot start Windows OpenSSH")?;
    let mut stdout = child.stdout.take().ok_or("Missing SSH output")?;
    let reader = std::thread::spawn(move || {
        let mut bytes = Vec::new();
        let result = stdout.by_ref().take(16385).read_to_end(&mut bytes);
        (result, bytes)
    });
    let start = Instant::now();
    let success = loop {
        match child.try_wait() {
            Ok(Some(status)) => break status.success(),
            Ok(None) => {}
            Err(_) => {
                let _ = child.kill();
                let _ = child.wait();
                break false;
            }
        }
        if start.elapsed() > Duration::from_secs(15) {
            let _ = child.kill();
            let _ = child.wait();
            break false;
        }
        std::thread::sleep(Duration::from_millis(25));
    };
    let (result, bytes) = reader.join().map_err(|_| "Cannot read SSH result")?;
    if result.is_err() || bytes.len() > 16384 {
        return Err("SSH output exceeded the diagnostic limit.".into());
    }
    if !success {
        return Err("SSH check failed. Verify reachability, the pinned host key, username and selected key/agent. Password fallback is disabled; upstream diagnostics are suppressed.".into());
    }
    Ok(String::from_utf8_lossy(&bytes)
        .chars()
        .filter(|c| !c.is_control() || *c == '\n' || *c == '\t')
        .take(2048)
        .collect())
}
pub fn scan(host: &str, user: &str, port: u16) -> Result<Value, String> {
    target(host, user, port)?;
    let output = run(
        &ssh_path("ssh-keyscan"),
        &[
            "-T".into(),
            "5".into(),
            "-p".into(),
            port.to_string(),
            "-t".into(),
            "ed25519,ecdsa,rsa".into(),
            host.into(),
        ],
    )?;
    let mut keys = Vec::new();
    for line in output.lines() {
        let words: Vec<_> = line.split_whitespace().collect();
        if words.len() == 3 {
            let key = format!("{} {}", words[1], words[2]);
            if let Ok(fp) = fingerprint(&key) {
                keys.push(json!({"key":key,"fingerprint":fp}));
            }
        }
    }
    if keys.is_empty() {
        return Err(
            "No supported SSH host keys found. Confirm the address, port and SSH server.".into(),
        );
    }
    Ok(
        json!({"keys":keys,"warning":"Keyscan is unauthenticated. Compare the fingerprint using the machine console or another trusted channel before pinning it."}),
    )
}
pub fn test(store: &Store, selected: &str) -> Result<Value, String> {
    let m = store.selected(selected)?;
    validate(&m)?;
    let mut keyfile = tempfile::NamedTempFile::new_in(&store.dir)
        .map_err(|_| "Cannot prepare isolated host-key file")?;
    writeln!(keyfile, "ecpa-{} {}", m.id, m.host_key).map_err(|_| "Cannot write host-key file")?;
    // Close the handle before Win32 OpenSSH opens it; retain path cleanup ownership.
    let keypath = keyfile.into_temp_path();
    let started = Instant::now();
    let output = run(&ssh_path("ssh"), &ssh_args(&m, &keypath, false))?;
    Ok(
        json!({"id":m.id,"connected":true,"host":m.host,"user":m.user,"fingerprint":fingerprint(&m.host_key)?,"elapsedMs":started.elapsed().as_millis(),"diagnostic":output,"message":"Pinned host key and public-key authentication succeeded. Fixed OS/user read only; no runner installed or machine changed."}),
    )
}
