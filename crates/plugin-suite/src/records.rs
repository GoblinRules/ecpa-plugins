use super::*;
use std::collections::BTreeSet;
pub fn read(settings: &Settings) -> Result<Value> {
    let file = read_target("library", settings.data.join("records.json"))?;
    let records: Value = if file["exists"] == true {
        serde_json::from_str(text(&file, "content")?)
            .map_err(|_| bad("Library JSON is damaged; restore a library backup externally"))?
    } else {
        json!([])
    };
    if !records.is_array() {
        return Err(bad("Library must contain an array"));
    }
    Ok(json!({"version":file["version"],"records":records,"path":file["path"]}))
}
pub fn save(settings: &Settings, mode: Mode, body: &Value, delete: bool) -> Result<Value> {
    let current = read(settings)?;
    if current["version"] != body["version"] {
        return Err((409, "Library changed. Reload before saving.".into()));
    }
    let mut records = current["records"].as_array().unwrap().clone();
    let id = text(body, "id")?;
    if id.is_empty()
        || id.len() > 64
        || !id
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
    {
        return Err(bad(
            "Use a short ID with letters, numbers, hyphens or underscores",
        ));
    }
    let existing = records.iter().position(|r| r["id"] == id);
    if !delete && existing.is_some() && body["replace"] != true {
        return Err((
            409,
            "A record with that ID already exists. Select it to edit, or use a new ID.".into(),
        ));
    }
    if delete {
        let index = existing.ok_or_else(|| bad("Record not found"))?;
        records.remove(index);
    } else {
        let name = text(body, "name")?.trim();
        if name.is_empty() || name.len() > 120 {
            return Err(bad("Name must contain 1–120 bytes"));
        }
        let tags = body["tags"]
            .as_array()
            .ok_or_else(|| bad("Tags must be an array"))?;
        if tags.len() > 20 || tags.iter().any(|t| t.as_str().is_none_or(|s| s.len() > 60)) {
            return Err(bad("Use at most 20 short text tags"));
        }
        let mut content = BTreeMap::<String, String>::new();
        if mode == Mode::Prompts {
            content.insert("prompt".into(), text(body, "content")?.into());
        } else {
            let targets = settings.targets(mode == Mode::Snapshots)?;
            for (id, v) in body["files"]
                .as_object()
                .ok_or_else(|| bad("Select files to include"))?
            {
                if !targets.contains_key(id) {
                    return Err(bad("Unknown file slot"));
                }
                let s = v.as_str().ok_or_else(|| bad("File content must be text"))?;
                if mode == Mode::Snapshots {
                    tools::validate_config(id, s)?;
                }
                content.insert(id.clone(), s.into());
            }
            if content.is_empty() {
                return Err(bad("Include at least one file"));
            }
        }
        if content.values().any(|s| s.len() > storage::LIMIT) {
            return Err((413, "A file exceeds 1 MiB".into()));
        }
        let record = json!({"id":id,"name":name,"tags":tags,"files":content});
        if let Some(i) = existing {
            records[i] = record;
        } else {
            if records.len() >= 100 {
                return Err(bad("Library limit: 100 records"));
            }
            records.push(record);
        }
    }
    storage::single(settings.data.join("records.json")).save(
        "document",
        text(body, "version")?,
        &serde_json::to_string_pretty(&records).unwrap(),
    )?;
    read(settings)
}
pub fn preview(settings: &Settings, mode: Mode, body: &Value) -> Result<Vec<Value>> {
    let library = read(settings)?;
    if library["version"] != body["libraryVersion"] {
        return Err((409, "Library changed. Reload before previewing.".into()));
    }
    let record = library["records"]
        .as_array()
        .unwrap()
        .iter()
        .find(|r| r["id"] == body["id"])
        .ok_or_else(|| bad("Record not found"))?;
    let selected = body["selected"]
        .as_array()
        .ok_or_else(|| bad("Select targets"))?;
    if selected.is_empty() {
        return Err(bad("Select at least one target"));
    }
    let targets = settings.targets(mode == Mode::Snapshots)?;
    let mut seen = BTreeSet::new();
    let mut changes = vec![];
    for v in selected {
        let id = v.as_str().ok_or_else(|| bad("Invalid target"))?;
        if !seen.insert(id) {
            return Err(bad("Duplicate target"));
        }
        let after = record["files"][id]
            .as_str()
            .ok_or_else(|| bad("Target not present in this record"))?;
        let path = targets.get(id).ok_or_else(|| bad("Unknown target"))?;
        if mode == Mode::Snapshots {
            tools::validate_config(id, after)?;
        }
        changes.push(change(read_target(id, path.clone())?, after.into()));
    }
    Ok(changes)
}
