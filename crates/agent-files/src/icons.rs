pub fn plugin(id: &str) -> &'static str {
    match id {
        "agent-instructions" => include_str!("../../../assets/icons/agent-instructions.svg"),
        "agent-profiles" => include_str!("../../../assets/icons/agent-profiles.svg"),
        "mcp-manager" => include_str!("../../../assets/icons/mcp-manager.svg"),
        "agent-diagnostics" => include_str!("../../../assets/icons/agent-diagnostics.svg"),
        "prompt-library" => include_str!("../../../assets/icons/prompt-library.svg"),
        "config-snapshots" => include_str!("../../../assets/icons/config-snapshots.svg"),
        "agent-skills" => include_str!("../../../assets/icons/agent-skills.svg"),
        _ => "",
    }
}
