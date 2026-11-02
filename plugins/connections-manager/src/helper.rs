//! The DLL owns a matching helper; no network download or shell installer is used.
use fs2::FileExt;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs::{self, OpenOptions},
    io::{Read, Write},
    path::{Path, PathBuf},
};

#[cfg(feature = "bundled-helper")]
const PAYLOAD: &[u8] = include_bytes!(env!(
    "ECPA_HELPER_BINARY",
    "Use python scripts/package.py --plugin connections-manager to bundle the helper"
));
#[cfg(not(feature = "bundled-helper"))]
const PAYLOAD: &[u8] = &[];

fn path() -> Result<PathBuf, String> {
    let root =
        PathBuf::from(std::env::var_os("LOCALAPPDATA").ok_or("LOCALAPPDATA is unavailable")?);
    if !root.is_absolute() {
        return Err("LOCALAPPDATA must be an absolute directory".into());
    }
    Ok(root
        .join("ECPA")
        .join("helpers")
        .join("connections-manager")
        .join("ecpa-connect.exe"))
}

fn matches(path: &Path, payload: &[u8]) -> Result<bool, String> {
    let mut file = match fs::File::open(path) {
        Ok(file) => file,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(false),
        Err(_) => return Err("Cannot read the managed helper; check file permissions".into()),
    };
    if file.metadata().map_err(|_| "Cannot inspect helper")?.len() != payload.len() as u64 {
        return Ok(false);
    }
    let mut hash = Sha256::new();
    let mut buffer = [0u8; 65536];
    loop {
        let count = file.read(&mut buffer).map_err(|_| "Cannot read helper")?;
        if count == 0 {
            break;
        }
        hash.update(&buffer[..count]);
    }
    Ok(hash.finalize() == Sha256::digest(payload))
}

fn install_at(path: &Path, payload: &[u8]) -> Result<(), String> {
    if payload.is_empty() {
        return Err("This development build has no bundled helper. Package the release or select a custom helper.".into());
    }
    let parent = path.parent().ok_or("Invalid helper directory")?;
    fs::create_dir_all(parent).map_err(|_| "Cannot create the managed helper directory")?;
    let lock = OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(parent.join("install.lock"))
        .map_err(|_| "Cannot open helper installation lock")?;
    lock.try_lock_exclusive()
        .map_err(|_| "Another helper installation is running. Retry shortly.")?;
    if matches(path, payload)? {
        return Ok(());
    }
    let mut pending =
        tempfile::NamedTempFile::new_in(parent).map_err(|_| "Cannot stage helper update")?;
    pending
        .write_all(payload)
        .map_err(|_| "Cannot write helper update")?;
    pending
        .as_file()
        .sync_all()
        .map_err(|_| "Cannot flush helper update")?;
    if !matches(pending.path(), payload)? {
        return Err(
            "Helper checksum verification failed; the existing helper was preserved".into(),
        );
    }
    // Atomic replacement: a running Windows executable can prevent replacement.
    // Do not remove the old helper first, kill processes, or write partial bytes.
    pending.persist(path).map_err(|_| "Cannot replace the helper. Stop agents/tools using it, then click Install / repair. The existing file was preserved.")?;
    Ok(())
}

pub fn install() -> Result<Value, String> {
    if !cfg!(windows) {
        return Err("The managed helper requires Windows".into());
    }
    install_at(&path()?, PAYLOAD)?;
    Ok(status())
}

pub fn status() -> Value {
    let available = cfg!(windows) && !PAYLOAD.is_empty();
    let target = path();
    let result = target.as_ref().map_err(Clone::clone).and_then(|p| {
        if available {
            matches(p, PAYLOAD)
        } else {
            Ok(false)
        }
    });
    json!({"available":available,"path":target.ok(),"ready":matches!(result, Ok(true)),
        "version":env!("CARGO_PKG_VERSION"),"sha256":if available {format!("{:x}",Sha256::digest(PAYLOAD))} else {String::new()},
        "error":result.err()})
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn installs_updates_and_repairs_without_touching_other_files() {
        let dir = tempfile::tempdir().unwrap();
        let exe = dir.path().join("helpers/ecpa-connect.exe");
        install_at(&exe, b"version-one").unwrap();
        assert!(matches(&exe, b"version-one").unwrap());
        let modified = fs::metadata(&exe).unwrap().modified().unwrap();
        install_at(&exe, b"version-one").unwrap();
        assert_eq!(modified, fs::metadata(&exe).unwrap().modified().unwrap());
        install_at(&exe, b"version-two").unwrap();
        fs::write(&exe, b"tampered!!!").unwrap();
        assert!(!matches(&exe, b"version-two").unwrap());
        install_at(&exe, b"version-two").unwrap();
        assert!(matches(&exe, b"version-two").unwrap());
        assert!(install_at(&exe, b"").is_err());
        assert!(matches(&exe, b"version-two").unwrap());
    }

    #[test]
    fn installation_lock_preserves_existing_helper() {
        let dir = tempfile::tempdir().unwrap();
        let exe = dir.path().join("ecpa-connect.exe");
        install_at(&exe, b"old").unwrap();
        let lock = OpenOptions::new()
            .read(true)
            .write(true)
            .open(dir.path().join("install.lock"))
            .unwrap();
        lock.lock_exclusive().unwrap();
        assert!(install_at(&exe, b"new").is_err());
        assert_eq!(fs::read(&exe).unwrap(), b"old");
    }

    #[cfg(windows)]
    #[test]
    fn locked_destination_preserves_previous_bytes_and_cleans_staging() {
        use std::os::windows::fs::OpenOptionsExt;
        let dir = tempfile::tempdir().unwrap();
        let exe = dir.path().join("ecpa-connect.exe");
        install_at(&exe, b"old").unwrap();
        let held = OpenOptions::new()
            .read(true)
            .share_mode(1)
            .open(&exe)
            .unwrap();
        assert!(install_at(&exe, b"new").unwrap_err().contains("preserved"));
        assert_eq!(fs::read(&exe).unwrap(), b"old");
        assert_eq!(fs::read_dir(dir.path()).unwrap().count(), 2);
        drop(held);
        install_at(&exe, b"new").unwrap();
        assert_eq!(fs::read(&exe).unwrap(), b"new");
    }
}
