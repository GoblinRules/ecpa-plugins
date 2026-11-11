use super::{dispatch, machines::*};
use base64::{engine::general_purpose::STANDARD, Engine};
use serde_json::json;

fn machine(root: &std::path::Path) -> Machine {
    let mut raw = vec![0, 0, 0, 11];
    raw.extend(b"ssh-ed25519");
    raw.extend([0, 0, 0, 32]);
    raw.extend([1u8; 32]);
    let file = root.join("selected.pub");
    std::fs::write(&file, "synthetic fixture; no private key").unwrap();
    Machine {
        id: "demo".into(),
        name: "Demo".into(),
        host: "example.test".into(),
        port: 22,
        user: "operator".into(),
        os: "linux".into(),
        auth: "agent".into(),
        identity_file: file.to_string_lossy().into(),
        host_key: format!("ssh-ed25519 {}", STANDARD.encode(raw)),
        labels: vec!["test".into()],
    }
}
#[test]
fn reject_injection_and_wrong_identity_selection() {
    let tmp = tempfile::tempdir().unwrap();
    let mut m = machine(tmp.path());
    assert!(validate(&m).is_ok());
    for host in [
        "-oProxyCommand=bad",
        "host;touch file",
        "user@host",
        "https://host",
        "host\nother",
    ] {
        m.host = host.into();
        assert!(validate(&m).is_err());
    }
    m.host = "host.example".into();
    m.user = "name;whoami".into();
    assert!(validate(&m).is_err());
    m.user = "operator".into();
    m.identity_file = tmp.path().join("not-private-key").to_string_lossy().into();
    std::fs::write(&m.identity_file, b"fixture").unwrap();
    assert!(validate(&m).is_err());
}
#[test]
fn stale_edits_and_fingerprint_confirmation_are_enforced() {
    let tmp = tempfile::tempdir().unwrap();
    let m = machine(tmp.path());
    let s = Store::new(tmp.path().join("data")).unwrap();
    let v = s.state().unwrap()["version"].as_str().unwrap().to_string();
    assert!(s.save(m.clone(), &v, "SHA256:unverified").is_err());
    s.save(m.clone(), &v, &fingerprint(&m.host_key).unwrap())
        .unwrap();
    assert!(s.remove(&m.id, &v).is_err());
    assert_eq!(s.selected(&m.id).unwrap().host, m.host);
}
#[test]
fn ssh_options_pin_one_identity_and_disable_implicit_execution() {
    let tmp = tempfile::tempdir().unwrap();
    let mut m = machine(tmp.path());
    m.auth = "key-file".into();
    let args = ssh_args(&m, &tmp.path().join("known_hosts"), false);
    for value in [
        "StrictHostKeyChecking=yes",
        "IdentitiesOnly=yes",
        "IdentityAgent=none",
        "ForwardAgent=no",
        "ProxyCommand=none",
        "BatchMode=yes",
        "ClearAllForwardings=yes",
        "PasswordAuthentication=no",
    ] {
        assert!(args.iter().any(|s| s == value));
    }
    assert_eq!(args.last().unwrap(), "uname -s; id -un");
    let interactive = ssh_args(&m, &tmp.path().join("known_hosts"), true);
    assert_eq!(interactive.last().unwrap(), &m.host);
}
#[test]
fn public_page_contains_no_machine_metadata() {
    let req = json!({"Path":"/v0/resource/plugins/ssh-machines/editor","Method":"GET"});
    let response = dispatch("management.handle", req.to_string().as_bytes());
    let bytes = STANDARD
        .decode(response["result"]["Body"].as_str().unwrap())
        .unwrap();
    let page = String::from_utf8(bytes).unwrap();
    assert!(page.contains("SSH and Machines"));
    assert!(!page.contains("example.test"));
}
