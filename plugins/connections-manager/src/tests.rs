use super::*;
use std::{cell::RefCell, collections::BTreeMap};
use zeroize::Zeroizing;
#[derive(Default)]
struct MemoryVault(RefCell<BTreeMap<String, String>>);
impl Vault for MemoryVault {
    fn read(&self, t: &str) -> Result<Zeroizing<String>, String> {
        self.0
            .borrow()
            .get(t)
            .cloned()
            .map(Zeroizing::new)
            .ok_or("missing".into())
    }
    fn write(&self, t: &str, s: &str) -> Result<(), String> {
        self.0.borrow_mut().insert(t.into(), s.into());
        Ok(())
    }
    fn delete(&self, t: &str) -> Result<(), String> {
        self.0.borrow_mut().remove(t);
        Ok(())
    }
}
fn add(s: &Store, v: &impl Vault, id: &str, service: &str) -> Value {
    s.mutate("save",&json!({"version":s.load().unwrap().1,"connection":{"id":id,"name":id,"service":service,"account_id":if service=="cloudflare"{"0123456789abcdef0123456789abcdef"}else{""}},"token":"fixture-secret"}),v).unwrap()
}
#[test]
fn tokens_stay_out_of_catalogue_and_responses_and_stale_edits_fail() {
    let dir = tempfile::tempdir().unwrap();
    let s = Store::new(dir.path().to_path_buf()).unwrap();
    let v = MemoryVault::default();
    let old = s.load().unwrap().1;
    let state = add(&s, &v, "personal", "github");
    assert!(!state.to_string().contains("fixture-secret"));
    assert!(
        !std::fs::read_to_string(dir.path().join("connections.json"))
            .unwrap()
            .contains("fixture-secret")
    );
    assert_eq!(state["connections"][0]["hasCredential"], true);
    assert!(s
        .mutate("delete", &json!({"version":old,"id":"personal"}), &v)
        .is_err());
    assert!(s.mutate("save",&json!({"version":state["version"],"connection":{"id":"personal","name":"renamed","service":"github","account_id":""},"token":""}),&v).is_ok());
    assert_eq!(&*v.read(&s.target("personal")).unwrap(), "fixture-secret");
    s.mutate(
        "delete",
        &json!({"version":s.load().unwrap().1,"id":"personal"}),
        &v,
    )
    .unwrap();
    assert!(v.read(&s.target("personal")).is_err());
}
#[test]
fn project_resolution_uses_nearest_parent_and_preserves_service_types() {
    let dir = tempfile::tempdir().unwrap();
    let s = Store::new(dir.path().join("data")).unwrap();
    let v = MemoryVault::default();
    add(&s, &v, "personal", "github");
    add(&s, &v, "work", "github");
    add(&s, &v, "cf-work", "cloudflare");
    let root = dir.path().join("repo");
    let child = root.join("child");
    std::fs::create_dir_all(&child).unwrap();
    for (path, gh) in [(&root, "personal"), (&child, "work")] {
        s.mutate("assign",&json!({"version":s.load().unwrap().1,"project":{"path":path,"github":gh,"cloudflare":"cf-work"}}),&v).unwrap();
    }
    let chosen = s.selected(None, child.to_str()).unwrap();
    assert_eq!(chosen[1].id, "work");
    let env = store::environment(&chosen, &s, &v).unwrap();
    assert_eq!(&*env["GH_TOKEN"], "fixture-secret");
    assert_eq!(
        &*env["CLOUDFLARE_ACCOUNT_ID"],
        "0123456789abcdef0123456789abcdef"
    );
    assert!(s
        .mutate(
            "delete",
            &json!({"version":s.load().unwrap().1,"id":"work"}),
            &v
        )
        .is_err());
    assert!(s.mutate("assign",&json!({"version":s.load().unwrap().1,"project":{"path":root,"github":"cf-work","cloudflare":null}}),&v).is_err());
    let adjacent = dir.path().join("repo-other");
    std::fs::create_dir(&adjacent).unwrap();
    assert!(s.selected(None, adjacent.to_str()).is_err());
}
#[test]
fn public_resource_never_exposes_connections() {
    let req = json!({"Method":"GET","Path":"/v0/resource/plugins/connections-manager/editor","Query":{"action":["delete"],"id":["personal"]}});
    let result = dispatch("management.handle", req.to_string().as_bytes());
    assert_eq!(result["result"]["StatusCode"], 200);
    for method in ["POST", "PUT", "DELETE"] {
        let req = json!({"Method":method,"Path":"/v0/resource/plugins/connections-manager/editor"});
        assert_eq!(
            dispatch("management.handle", req.to_string().as_bytes())["result"]["StatusCode"],
            404
        )
    }
    let r = dispatch("management.register", b"{}");
    for route in r["result"]["routes"].as_array().unwrap() {
        assert!(route["Path"].as_str().unwrap().starts_with(API));
        assert!(route.get("Menu").is_none())
    }
}
#[cfg(windows)]
#[test]
fn windows_vault_roundtrip() {
    let dir = tempfile::tempdir().unwrap();
    let s = Store::new(dir.path().to_path_buf()).unwrap();
    let target = s.target("fixture");
    let v = SystemVault;
    v.write(&target, "fake-test-token").unwrap();
    let read = v.read(&target);
    let deleted = v.delete(&target);
    assert_eq!(&*read.unwrap(), "fake-test-token");
    deleted.unwrap();
    assert!(v.read(&target).is_err());
    v.delete(&target).unwrap();
}

#[cfg(windows)]
fn legacy_target(path: &str, id: &str) -> String {
    use sha2::{Digest, Sha256};
    format!(
        "ECPA/Connections/{:x}/{id}",
        Sha256::digest(path.as_bytes())
    )
}
#[cfg(windows)]
#[test]
fn slash_spellings_read_legacy_tokens_and_share_new_writes() {
    let dir = tempfile::tempdir().unwrap();
    let back = dir.path().join("data").to_string_lossy().to_string();
    let forward = back.replace('\\', "/");
    let mixed = back.replacen('\\', "/", 1);
    let stores: Vec<_> = [&back, &forward, &mixed]
        .iter()
        .map(|p| Store::new(PathBuf::from(p)).unwrap())
        .collect();
    let v = MemoryVault::default();
    let state = add(&stores[0], &v, "work", "github");
    // Simulate v0.5.1 having saved under the forward-slash hash only.
    v.delete(&stores[0].target("work")).unwrap();
    let legacy = legacy_target(&forward, "work");
    v.write(&legacy, "legacy-fixture").unwrap();
    for s in &stores {
        assert_eq!(s.target("work"), stores[0].target("work"));
        assert_eq!(
            s.state(&v).unwrap()["connections"][0]["hasCredential"],
            true
        );
        let env = store::environment(&s.selected(Some("work"), None).unwrap(), s, &v).unwrap();
        assert_eq!(&*env["GH_TOKEN"], "legacy-fixture");
    }
    let connection = json!({"id":"work","name":"renamed","service":"github","account_id":""});
    stores[1]
        .mutate(
            "save",
            &json!({"version":state["version"],"connection":connection,"token":""}),
            &v,
        )
        .unwrap();
    // Replace both normalized and already-existing legacy credentials.
    stores[1].mutate("save", &json!({"version":stores[0].load().unwrap().1,"connection":connection,"token":"replacement-fixture"}), &v).unwrap();
    assert_eq!(&*v.read(&legacy).unwrap(), "replacement-fixture");
    for s in &stores {
        assert_eq!(&*s.credential("work", &v).unwrap(), "replacement-fixture");
    }
    let other = Store::new(dir.path().join("different")).unwrap();
    assert!(other.credential("work", &v).is_err());
    stores[2]
        .mutate(
            "delete",
            &json!({"version":stores[0].load().unwrap().1,"id":"work"}),
            &v,
        )
        .unwrap();
    assert!(v.0.borrow().is_empty());
    add(&stores[1], &v, "new", "github");
    assert_eq!(v.0.borrow().len(), 1);
    assert_eq!(&*stores[0].credential("new", &v).unwrap(), "fixture-secret");
}
#[cfg(windows)]
#[test]
fn conflicting_path_tokens_require_explicit_resolution() {
    let dir = tempfile::tempdir().unwrap();
    let s = Store::new(dir.path().to_path_buf()).unwrap();
    let v = MemoryVault::default();
    add(&s, &v, "work", "github");
    let legacy = legacy_target(&s.dir.to_string_lossy().replace('\\', "/"), "work");
    v.write(&legacy, "different-fixture").unwrap();
    assert!(s
        .credential("work", &v)
        .unwrap_err()
        .contains("Conflicting"));
    let c = json!({"id":"work","name":"work","service":"github","account_id":""});
    assert!(s
        .mutate(
            "save",
            &json!({"version":s.load().unwrap().1,"connection":c,"token":""}),
            &v
        )
        .is_err());
    s.mutate(
        "save",
        &json!({"version":s.load().unwrap().1,"connection":c,"token":"chosen-fixture"}),
        &v,
    )
    .unwrap();
    assert_eq!(&*s.credential("work", &v).unwrap(), "chosen-fixture");
}
#[cfg(windows)]
#[test]
fn failed_catalogue_save_restores_all_path_credentials() {
    let dir = tempfile::tempdir().unwrap();
    let s = Store::new(dir.path().to_path_buf()).unwrap();
    let v = MemoryVault::default();
    add(&s, &v, "work", "github");
    let legacy = legacy_target(&s.dir.to_string_lossy().replace('\\', "/"), "work");
    v.write(&legacy, "fixture-secret").unwrap();
    // Windows denies replacement while this handle disallows deletion.
    use std::os::windows::fs::OpenOptionsExt;
    let handle = std::fs::OpenOptions::new()
        .read(true)
        .share_mode(1)
        .open(s.dir.join("connections.json"))
        .unwrap();
    let version = s.load().unwrap().1;
    for (action, body) in [
        (
            "save",
            json!({"version":version,"connection":{"id":"work","name":"work","service":"github","account_id":""},"token":"replacement-fixture"}),
        ),
        ("delete", json!({"version":version,"id":"work"})),
    ] {
        assert!(s.mutate(action, &body, &v).is_err());
        assert_eq!(&*v.read(&legacy).unwrap(), "fixture-secret");
        assert_eq!(&*v.read(&s.target("work")).unwrap(), "fixture-secret");
    }
    drop(handle);
}
