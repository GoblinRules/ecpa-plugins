use connections_manager::{
    store::{self, environment, Store},
    vault::SystemVault,
};
use std::{path::PathBuf, process::Command};
const HELP:&str="ECPA Connections Manager\n\necpa-connect [--data-dir PATH] list\necpa-connect [--data-dir PATH] portainer-mcp CONNECTION\necpa-connect [--data-dir PATH] login-github ID NAME\necpa-connect [--data-dir PATH] import-github ID NAME\necpa-connect [--data-dir PATH] check CONNECTION\necpa-connect [--data-dir PATH] run (--connection ID | --project PATH) -- EXECUTABLE [ARGS...]\n\nProject selection includes parent directories (nearest assignment wins).\nFor Wrangler on Windows use node.exe and the absolute path to wrangler/bin/wrangler.js.\nBatch files and shell command strings are not supported. No global login is changed.\nUse an absolute executable path for MCP servers; stdin/stdout and exit status pass through.\n";
fn run() -> Result<i32, String> {
    let mut args = std::env::args().skip(1).peekable();
    let mut dir = None;
    if args.peek().map(String::as_str) == Some("--data-dir") {
        args.next();
        dir = Some(PathBuf::from(args.next().ok_or("Missing data directory")?));
    }
    let action = args.next().unwrap_or_else(|| "help".into());
    if ["help", "--help", "-h"].contains(&action.as_str()) {
        print!("{HELP}");
        return Ok(0);
    }
    let store = Store::new(match dir {
        Some(d) => d,
        None => store::default_dir()?,
    })?;
    match action.as_str() {
        "portainer-mcp" => {
            let id = args.next().ok_or("Supply a Portainer connection ID")?;
            if args.next().is_some() {
                return Err("Unexpected arguments".into());
            }
            connections_manager::portainer::serve(&store, &id, &SystemVault)?;
            Ok(0)
        }
        "login-github" | "import-github" => {
            let id = args.next().ok_or("Supply an account ID and display name")?;
            let name = args
                .next()
                .ok_or("Supply a display name (quote names with spaces)")?;
            if args.next().is_some() {
                return Err("Unexpected login arguments".into());
            }
            if action == "import-github" {
                import_github(&store, &id, &name)?;
            } else {
                login_github(&store, &id, &name)?;
            }
            Ok(0)
        }
        "list" => {
            println!(
                "{}",
                serde_json::to_string_pretty(&store.state(&SystemVault)?)
                    .map_err(|_| "Cannot encode list")?
            );
            Ok(0)
        }
        "check" => {
            let id = args.next().ok_or("Missing connection ID")?;
            println!(
                "{}",
                connections_manager::verify(&store, &id, &SystemVault)?
            );
            Ok(0)
        }
        "run" => {
            let selector = args.next().ok_or("Choose --connection or --project")?;
            let value = args.next().ok_or("Missing selection")?;
            let lock = store.lock(false)?;
            let selected = match selector.as_str() {
                "--connection" => store.selected(Some(&value), None)?,
                "--project" => store.selected(None, Some(&value))?,
                _ => return Err("Choose --connection or --project".into()),
            };
            if args.next().as_deref() != Some("--") {
                return Err("Use -- before the executable".into());
            }
            let exe = args.next().ok_or("Missing executable")?;
            let extension = PathBuf::from(&exe)
                .extension()
                .map(|s| s.to_string_lossy().to_lowercase())
                .unwrap_or_default();
            if ["cmd", "bat", "ps1"].contains(&extension.as_str()) {
                return Err("Use a native executable (for Wrangler: node.exe plus wrangler/bin/wrangler.js), not a shell script".into());
            }
            let env = environment(&selected, &store, &SystemVault)?;
            drop(lock);
            let mut child = Command::new(&exe);
            child.args(args);
            if selector == "--project" {
                child.current_dir(&value);
            }
            // Remove competing inherited credentials before adding this selection.
            for name in [
                "CLOUDFLARE_API_TOKEN",
                "CLOUDFLARE_ACCOUNT_ID",
                "CLOUDFLARE_API_KEY",
                "CLOUDFLARE_EMAIL",
                "CF_API_TOKEN",
                "CF_ACCOUNT_ID",
                "CF_API_KEY",
                "CF_EMAIL",
                "CLOUDFLARE_API_BASE_URL",
                "GH_TOKEN",
                "GITHUB_TOKEN",
                "GITHUB_PERSONAL_ACCESS_TOKEN",
                "GH_ENTERPRISE_TOKEN",
                "GITHUB_ENTERPRISE_TOKEN",
                "GH_HOST",
            ] {
                child.env_remove(name);
            }
            for (name, value) in &env {
                child.env(name, value.as_str());
            }
            eprintln!(
                "ECPA connections: {}",
                selected
                    .iter()
                    .map(|c| format!("{} ({})", c.name, c.id))
                    .collect::<Vec<_>>()
                    .join(", ")
            );
            let status = child
                .status()
                .map_err(|_| "Cannot start executable; check its path and installation")?;
            Ok(status.code().unwrap_or(1))
        }
        _ => Err("Unknown command. Use ecpa-connect --help".into()),
    }
}
fn main() {
    match run() {
        Ok(code) => std::process::exit(code),
        Err(e) => {
            eprintln!("{e}");
            std::process::exit(1)
        }
    }
}

// Use an ephemeral gh profile, never the user's global login or keychain entry.
fn github_command(profile: &std::path::Path) -> Command {
    let mut cmd = local_github_command();
    cmd.env("GH_CONFIG_DIR", profile);
    cmd
}
fn local_github_command() -> Command {
    let mut cmd = Command::new("gh.exe");
    cmd.env("GH_HOST", "github.com");
    for key in [
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "GH_ENTERPRISE_TOKEN",
        "GITHUB_ENTERPRISE_TOKEN",
        "GH_DEBUG",
        "DEBUG",
        "GH_PROMPT_DISABLED",
    ] {
        cmd.env_remove(key);
    }
    cmd
}
fn login_github(store: &Store, id: &str, name: &str) -> Result<(), String> {
    let connection = store::Connection {
        id: id.into(),
        name: name.into(),
        service: "github".into(),
        account_id: String::new(),
        base_url: String::new(),
    };
    store::validate(&connection)?;
    let version = {
        let _lock = store.lock(false)?;
        let (data, version) = store.load()?;
        if data.connections.iter().any(|c| c.id == id) {
            return Err(
                "This ID already exists. Use a new ID to avoid replacing an account.".into(),
            );
        }
        version
    };
    let profile = tempfile::Builder::new()
        .prefix("ecpa-github-login-")
        .tempdir()
        .map_err(|_| "Cannot create temporary login profile")?;
    eprintln!("Sign in to the intended GitHub account in your browser. Your normal gh login is unchanged.");
    // gh's credential-store keys are not namespaced by GH_CONFIG_DIR. A temporary
    // file avoids overwriting global keychain entries; it is removed after import.
    let status = github_command(profile.path())
        .args([
            "auth",
            "login",
            "--hostname",
            "github.com",
            "--web",
            "--git-protocol",
            "https",
            "--insecure-storage",
        ])
        .status()
        .map_err(|_| "Install GitHub CLI (gh.exe) before signing in")?;
    if !status.success() {
        return Err("GitHub sign-in was cancelled or failed; no connection saved".into());
    }
    let output = github_command(profile.path())
        .args(["auth", "token", "--hostname", "github.com"])
        .output()
        .map_err(|_| "Cannot retrieve GitHub login")?;
    let bytes = zeroize::Zeroizing::new(output.stdout);
    if !output.status.success() {
        return Err("GitHub login did not provide a credential".into());
    }
    let token = std::str::from_utf8(&bytes)
        .map_err(|_| "Invalid GitHub credential")?
        .trim();
    let identity = github_command(profile.path())
        .env("GH_TOKEN", token)
        .args(["api", "user", "--jq", ".login"])
        .output()
        .map_err(|_| "Cannot verify GitHub identity")?;
    if !identity.status.success() {
        return Err("GitHub identity verification failed; no connection saved".into());
    }
    let login = String::from_utf8_lossy(&identity.stdout).trim().to_string();
    if login.is_empty() {
        return Err("GitHub returned no identity".into());
    }
    eprintln!("Verified GitHub account: {login}. Type this username to save it as {name}:");
    let mut confirmation = String::new();
    std::io::stdin()
        .read_line(&mut confirmation)
        .map_err(|_| "Cannot read confirmation")?;
    if confirmation.trim() != login {
        return Err("Account was not confirmed; nothing saved".into());
    }
    let mut body = serde_json::json!({"version":version,"connection":connection,"token":token});
    let result = store.mutate("save", &body, &SystemVault);
    if let Some(serde_json::Value::String(secret)) = body.get_mut("token") {
        zeroize::Zeroize::zeroize(secret);
    }
    result?;
    profile
        .close()
        .map_err(|_| "Account saved, but temporary login cleanup failed")?;
    eprintln!("Saved {name} ({login}) in Windows Credential Manager. Refresh Connections Manager to use it.");
    Ok(())
}

/// Read saved accounts through gh's supported API, preserving its configured profile.
/// Never switch the active account or print the credential.
fn import_github(store: &Store, id: &str, name: &str) -> Result<(), String> {
    let connection = store::Connection {
        id: id.into(),
        name: name.into(),
        service: "github".into(),
        account_id: String::new(),
        base_url: String::new(),
    };
    store::validate(&connection)?;
    let version = {
        let _lock = store.lock(false)?;
        let (data, version) = store.load()?;
        if data.connections.iter().any(|c| c.id == id) {
            return Err("This ID already exists. Choose a new ID.".into());
        }
        version
    };
    let output = local_github_command()
        .args([
            "auth",
            "status",
            "--hostname",
            "github.com",
            "--json",
            "hosts",
            "--jq",
            "[.hosts[\"github.com\"][] | .login]",
        ])
        .output()
        .map_err(|_| "Install GitHub CLI (gh.exe) to discover saved logins")?;
    if !output.status.success() {
        return Err(
            "Cannot discover saved GitHub logins. Update GitHub CLI or use browser sign-in.".into(),
        );
    }
    let mut accounts: Vec<String> = serde_json::from_slice(&output.stdout)
        .map_err(|_| "GitHub CLI returned an unexpected account list")?;
    accounts.retain(|a| {
        !a.is_empty() && a.len() <= 100 && a.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'-')
    });
    accounts.sort();
    accounts.dedup();
    if accounts.is_empty() {
        return Err("No saved github.com accounts found for this Windows user and GH_CONFIG_DIR. Use browser sign-in first.".into());
    }
    eprintln!("Saved GitHub accounts (your active account will not change):");
    for (index, account) in accounts.iter().enumerate() {
        eprintln!("  {}. {}", index + 1, account);
    }
    eprintln!("Enter the account number to import, or press Enter to cancel:");
    let mut selection = String::new();
    std::io::stdin()
        .read_line(&mut selection)
        .map_err(|_| "Cannot read account selection")?;
    let index = selection
        .trim()
        .parse::<usize>()
        .ok()
        .and_then(|n| n.checked_sub(1))
        .ok_or("Import cancelled or invalid selection; nothing saved")?;
    let username = accounts
        .get(index)
        .ok_or("Invalid selection; nothing saved")?;
    let output = local_github_command()
        .args([
            "auth",
            "token",
            "--hostname",
            "github.com",
            "--user",
            username,
        ])
        .output()
        .map_err(|_| "Cannot read the selected GitHub login")?;
    let bytes = zeroize::Zeroizing::new(output.stdout);
    if !output.status.success() {
        return Err("Saved GitHub credential is unavailable; sign in again".into());
    }
    let token = std::str::from_utf8(&bytes)
        .map_err(|_| "Invalid credential")?
        .trim();
    if token.is_empty() {
        return Err("Saved GitHub credential is empty".into());
    }
    let identity = local_github_command()
        .env("GH_TOKEN", token)
        .args(["api", "user", "--jq", ".login"])
        .output()
        .map_err(|_| "Cannot verify selected account")?;
    if !identity.status.success() {
        return Err(
            "Saved login could not be verified. Check connectivity or sign in again.".into(),
        );
    }
    let login = String::from_utf8_lossy(&identity.stdout).trim().to_string();
    if !login.eq_ignore_ascii_case(username) {
        return Err(
            "Credential identity does not match the selected account; nothing saved".into(),
        );
    }
    eprintln!("Verified {login}. Type this username to save a credential copy as {name}:");
    let mut confirmation = String::new();
    std::io::stdin()
        .read_line(&mut confirmation)
        .map_err(|_| "Cannot read confirmation")?;
    if confirmation.trim() != login {
        return Err("Import cancelled; nothing saved".into());
    }
    let mut body = serde_json::json!({"version":version,"connection":connection,"token":token});
    let result = store.mutate("save", &body, &SystemVault);
    if let Some(serde_json::Value::String(secret)) = body.get_mut("token") {
        zeroize::Zeroize::zeroize(secret);
    }
    result?;
    eprintln!("Imported {login} into Windows Credential Manager. Refresh Connections Manager. This is a copy, not a live link to gh; revocation still applies.");
    Ok(())
}

#[cfg(test)]
mod login_tests {
    use super::*;
    #[test]
    fn login_isolates_config_and_removes_inherited_credentials_and_debug() {
        let cmd = github_command(std::path::Path::new("isolated-profile"));
        let env: std::collections::BTreeMap<_, _> = cmd.get_envs().collect();
        assert_eq!(
            env[std::ffi::OsStr::new("GH_CONFIG_DIR")],
            Some(std::ffi::OsStr::new("isolated-profile"))
        );
        for key in ["GH_TOKEN", "GITHUB_TOKEN", "GH_DEBUG", "DEBUG"] {
            assert_eq!(env[std::ffi::OsStr::new(key)], None);
        }
    }
}
