use super::*;
use std::fs;

fn fixture(mode: Mode) -> (tempfile::TempDir, App, Settings) {
    let dir = tempfile::tempdir().unwrap();
    let paths = [
        "claude",
        "codex",
        "codex-override",
        "kimi",
        "grok",
        "zcode",
        "antigravity",
        "antigravity-agents",
    ]
    .into_iter()
    .map(|id| (id.into(), dir.path().join(format!("{id}.md"))))
    .collect();
    let settings = Settings {
        instructions: paths,
        data: dir.path().join("data"),
        configs: [
            ("claude-config".into(), dir.path().join("claude.json")),
            ("codex-config".into(), dir.path().join("codex.toml")),
        ]
        .into_iter()
        .collect(),
        skills: [("codex".into(), dir.path().join("skills"))]
            .into_iter()
            .collect(),
    };
    let mut app = App::new("fixture", "Fixture", mode);
    app.settings = Some(settings.clone());
    (dir, app, settings)
}
#[test]
fn profiles_preview_all_targets_before_writing_and_consume_tokens() {
    let (_dir, mut app, settings) = fixture(Mode::Profiles);
    let targets = settings.targets(false).unwrap();
    fs::write(&targets["claude"], "before").unwrap();
    fs::write(&targets["codex"], "before").unwrap();
    let library = records::read(&settings).unwrap();
    let saved = records::save(&settings, Mode::Profiles, &json!({"id":"work","name":"Work","tags":[],"version":library["version"],"files":{"claude":"after","codex":"after"}}),false).unwrap();
    let body = json!({"id":"work","libraryVersion":saved["version"],"selected":["claude","codex"]});
    let preview = app.prepare(&settings, &body).unwrap();
    fs::write(&targets["codex"], "external").unwrap();
    assert_eq!(app.apply(&settings, &preview).unwrap_err().0, 409);
    assert_eq!(fs::read_to_string(&targets["claude"]).unwrap(), "before");
    let preview = app.prepare(&settings, &body).unwrap();
    assert_eq!(app.apply(&settings, &preview).unwrap()["status"], "applied");
    assert!(app.apply(&settings, &preview).is_err());
    for id in ["claude", "codex"] {
        assert_eq!(fs::read_to_string(&targets[id]).unwrap(), "after");
        assert_eq!(
            storage::single(targets[id].clone())
                .backups("document")
                .unwrap()["backups"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
    }
    assert_ne!(
        storage::single(targets["claude"].clone())
            .backup_dir("document")
            .unwrap(),
        storage::single(targets["codex"].clone())
            .backup_dir("document")
            .unwrap()
    );
}
#[test]
fn mcp_preserves_unrelated_json_and_toml_and_refuses_invalid_data() {
    let before = "# preferences\nmodel = \"fixture-model\"\n[other]\nflag = true\n[mcp_servers.old]\ncommand = \"old\"\n";
    let after = tools::merge_mcp(
        "codex-config",
        before,
        r#"{"docs":{"url":"https://example.test/mcp","enabled":false}}"#,
    )
    .unwrap();
    assert!(after.contains("# preferences"));
    assert!(after.contains("model = \"fixture-model\""));
    let parsed: Value = toml_edit::de::from_str(&after).unwrap();
    assert_eq!(parsed["other"]["flag"], true);
    assert_eq!(parsed["mcp_servers"]["docs"]["enabled"], false);
    assert!(parsed["mcp_servers"].get("old").is_none());
    let json = tools::merge_mcp(
        "claude-config",
        r#"{"projects":{"keep":1},"other":["untouched"]}"#,
        r#"{"docs":{"type":"http","url":"https://example.test/mcp"}}"#,
    )
    .unwrap();
    assert_eq!(
        serde_json::from_str::<Value>(&json).unwrap()["projects"]["keep"],
        1
    );
    assert!(tools::merge_mcp("claude-config", "broken", "{}").is_err());
    assert!(tools::merge_mcp(
        "claude-config",
        "{}",
        r#"{"bad":{"url":"https://example.test"}}"#
    )
    .is_err());
    assert!(tools::merge_mcp("codex-config", "", r#"{"bad":{"command":"x","args":42}}"#).is_err());
}
#[test]
fn library_conflicts_unknown_targets_and_diagnostics_are_read_only() {
    let (_dir, app, settings) = fixture(Mode::Diagnostics);
    let file = &settings.configs["codex-config"];
    fs::write(file, "secret = [INVALID").unwrap();
    let state = app.state(&settings).unwrap();
    assert!(!state.to_string().contains("INVALID"));
    assert!(!state.to_string().contains("content"));
    assert!(!settings.data.exists());
    assert_eq!(fs::read_to_string(file).unwrap(), "secret = [INVALID");
    let version = records::read(&settings).unwrap()["version"].clone();
    let body = json!({"id":"a","name":"A","tags":[],"version":version,"content":"prompt"});
    records::save(&settings, Mode::Prompts, &body, false).unwrap();
    assert_eq!(
        records::save(&settings, Mode::Prompts, &body, false)
            .unwrap_err()
            .0,
        409
    );
    let version = records::read(&settings).unwrap()["version"].clone();
    assert!(records::save(
        &settings,
        Mode::Profiles,
        &json!({"id":"a","name":"A","tags":[],"version":version,"files":{"../escape":"x"}}),
        false
    )
    .is_err());
}
#[test]
fn skills_validate_metadata_paths_and_preview_new_files() {
    let (_dir, mut app, settings) = fixture(Mode::Skills);
    assert!(tools::skill_path(&settings, "codex/../escape").is_err());
    assert!(tools::skill_path(&settings, "unknown/name").is_err());
    assert!(tools::validate_skill("# Missing metadata").is_err());
    assert!(tools::validate_skill("---\nname: a\ndescription: b\n---not-a-delimiter\n").is_err());
    let content = "---\nname: sample\ndescription: Sample workflow\n---\n\nDo the work.\n";
    let p = app
        .prepare(
            &settings,
            &json!({"id":"codex/sample","version":null,"content":content}),
        )
        .unwrap();
    assert!(!settings.skills["codex"].exists());
    assert_eq!(app.apply(&settings, &p).unwrap()["status"], "applied");
    assert_eq!(tools::skills(&settings).unwrap()[0]["content"], content);
    assert!(app
        .prepare(
            &settings,
            &json!({"id":"codex/sample","version":null,"content":content})
        )
        .is_err());
}

#[test]
fn expired_previews_and_duplicate_record_ids_do_not_write() {
    let (_dir, mut app, settings) = fixture(Mode::Skills);
    let preview = app
        .prepare(
            &settings,
            &json!({"id":"codex/sample","version":null,
        "content":"---\nname: sample\ndescription: Example\n---\nWork"}),
        )
        .unwrap();
    app.preview.as_mut().unwrap().created = Instant::now() - std::time::Duration::from_secs(301);
    assert!(app.apply(&settings, &preview).is_err());
    assert!(!settings.skills["codex"].exists());
    let original = records::read(&settings).unwrap();
    let mut body = json!({"id":"same","name":"First","tags":[],"content":"original","version":original["version"]});
    let saved = records::save(&settings, Mode::Prompts, &body, false).unwrap();
    body["version"] = saved["version"].clone();
    body["content"] = json!("replacement");
    assert_eq!(
        records::save(&settings, Mode::Prompts, &body, false)
            .unwrap_err()
            .0,
        409
    );
    assert_eq!(
        records::read(&settings).unwrap()["records"][0]["files"]["prompt"],
        "original"
    );
    body["replace"] = json!(true);
    assert_eq!(
        records::save(&settings, Mode::Prompts, &body, false).unwrap()["records"][0]["files"]
            ["prompt"],
        "replacement"
    );
}
#[test]
fn public_resource_and_unsupported_routes_never_reach_disk() {
    for mode in [
        Mode::Profiles,
        Mode::Mcp,
        Mode::Diagnostics,
        Mode::Prompts,
        Mode::Snapshots,
        Mode::Skills,
    ] {
        let (_dir, mut app, settings) = fixture(mode);
        assert_eq!(
            app.handle(&json!({"Method":"GET","Path":"/v0/resource/plugins/fixture/editor"}))
                ["StatusCode"],
            200
        );
        assert_eq!(
            app.handle(&json!({"Method":"POST","Path":"/v0/resource/plugins/fixture/apply"}))
                ["StatusCode"],
            404
        );
        assert_eq!(
            app.handle(&json!({"Method":"GET","Path":"/v0/management/fixture/../state"}))
                ["StatusCode"],
            404
        );
        assert!(!settings.data.exists());
    }
}
