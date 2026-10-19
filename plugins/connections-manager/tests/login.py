"""Exercise CLI OAuth orchestration using a native fake gh; no network or real credentials."""
import ctypes, hashlib, json, os, pathlib, subprocess, tempfile
ROOT = pathlib.Path(__file__).resolve().parents[3]
with tempfile.TemporaryDirectory(prefix="ecpa-login-test-") as temp:
    root = pathlib.Path(temp)
    data = root / "catalogue"
    source = root / "gh.rs"
    source.write_text(r'''fn main() {
        for key in ["GH_DEBUG", "DEBUG", "GITHUB_TOKEN"] { assert!(std::env::var_os(key).is_none()); }
        let args: Vec<String> = std::env::args().skip(1).collect();
        let profile = std::env::var("GH_CONFIG_DIR").unwrap();
        std::fs::write(std::env::var("PROFILE_RECORD").unwrap(), &profile).unwrap();
        if args[0] == "auth" && args[1] == "login" {
            assert!(std::env::var_os("GH_TOKEN").is_none());
            assert!(args.contains(&"--insecure-storage".to_string()));
            std::fs::write(std::path::Path::new(&profile).join("hosts.yml"), "synthetic-oauth-secret").unwrap();
        } else if args[0] == "auth" && args[1] == "token" { println!("synthetic-oauth-secret"); }
        else if args[0] == "api" { assert_eq!(std::env::var("GH_TOKEN").unwrap(), "synthetic-oauth-secret"); println!("fixture-user"); }
        else { panic!("unexpected command"); }
    }''')
    subprocess.run(["rustc", str(source), "-o", str(root / "gh.exe")], check=True)
    env = dict(os.environ, PATH=str(root)+os.pathsep+os.environ["PATH"], GH_TOKEN="inherited", GITHUB_TOKEN="inherited", GH_DEBUG="api", DEBUG="true", PROFILE_RECORD=str(root / "profile.txt"))
    helper = ROOT / "target/release/ecpa-connect.exe"
    def login(id, confirmation):
        result = subprocess.run([str(helper), "--data-dir", str(data), "login-github", id, "Test account"], env=env, input=confirmation, text=True, capture_output=True)
        assert "synthetic-oauth-secret" not in result.stdout + result.stderr
        assert not pathlib.Path((root / "profile.txt").read_text()).exists(), "Temporary credential profile leaked"
        return result
    target = "ECPA/Connections/"+hashlib.sha256(str(data).encode()).hexdigest()+"/oauth-test"
    try:
        assert login("cancelled", "wrong-user\n").returncode != 0
        assert not (data / "connections.json").exists()
        result = login("oauth-test", "fixture-user\n")
        assert result.returncode == 0, result.stderr
        catalogue = (data / "connections.json").read_text()
        assert "synthetic-oauth-secret" not in catalogue
        assert json.loads(catalogue)["connections"][0]["id"] == "oauth-test"
        assert login("oauth-test", "fixture-user\n").returncode != 0
        print("PASS: isolated OAuth CLI flow, username confirmation, vault import, duplicate protection, secret-free output and temporary profile cleanup")
    finally:
        vault = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        vault.CredDeleteW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32]
        vault.CredDeleteW(target, 1, 0)
