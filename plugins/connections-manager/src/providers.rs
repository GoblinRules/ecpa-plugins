//! The core owns frontend authentication/protocol translation; the worker resolves keys.
use crate::{gateway, native, store::Store};
use base64::{engine::general_purpose::STANDARD, Engine};
use serde_json::{json, Value};
use std::{
    io::{BufRead, BufReader, Read},
    sync::{
        atomic::{AtomicBool, Ordering},
        Mutex,
    },
    thread::JoinHandle,
    time::{Duration, Instant},
};

static STOP: AtomicBool = AtomicBool::new(false);
static STREAMS: Mutex<Vec<JoinHandle<()>>> = Mutex::new(Vec::new());

pub fn start() {
    STOP.store(false, Ordering::SeqCst);
}
pub fn stop() {
    STOP.store(true, Ordering::SeqCst);
    if let Ok(mut streams) = STREAMS.lock() {
        for handle in streams.drain(..) {
            let _ = handle.join();
        }
    }
}

pub fn execute(store: &Store, request: &Value, stream: bool) -> Result<Value, String> {
    if STOP.load(Ordering::SeqCst) {
        return Err("Provider executor is stopping".into());
    }
    let model = request["Model"].as_str().ok_or("Missing model alias")?;
    if !model.starts_with("ecpa-") || model.len() > 128 {
        return Err("Unknown managed model alias".into());
    }
    let raw = STANDARD
        .decode(
            request["Payload"]
                .as_str()
                .ok_or("Missing translated payload")?,
        )
        .map_err(|_| "Invalid provider payload")?;
    if raw.len() > 240 * 1024 {
        return Err("Provider payload exceeds limit".into());
    }
    let payload: Value = serde_json::from_slice(&raw).map_err(|_| "Invalid provider JSON")?;
    let response = gateway::open(
        store,
        &json!({"model":model,"format":request["Format"],"payload":payload,"stream":stream}),
        "/provider",
    )?;
    if response.status() != 200 {
        return Err("Managed provider rejected the request; no fallback was attempted".into());
    }
    if !stream {
        let mut bytes = Vec::new();
        response
            .into_reader()
            .take(2_097_153)
            .read_to_end(&mut bytes)
            .map_err(|_| "Provider response interrupted")?;
        if bytes.len() > 2_097_152 {
            return Err("Provider response exceeds limit".into());
        }
        return Ok(
            json!({"Payload":STANDARD.encode(bytes),"Headers":{"Content-Type":["application/json"]}}),
        );
    }
    let id = request["stream_id"]
        .as_str()
        .filter(|s| !s.is_empty() && s.len() < 256)
        .ok_or("Missing host stream ID")?
        .to_string();
    let mut streams = STREAMS
        .lock()
        .map_err(|_| "Provider stream state unavailable")?;
    // stop() holds the same lock while joining. Never spawn after quiescing,
    // even if an upstream connection was still opening when shutdown started.
    if STOP.load(Ordering::SeqCst) {
        return Err("Provider executor is stopping".into());
    }
    streams.retain(|handle| !handle.is_finished());
    if streams.len() >= 8 {
        return Err("Provider concurrency limit reached".into());
    }
    let handle = std::thread::spawn(move || {
        let mut reader = BufReader::new(response.into_reader());
        let mut total = 0;
        let start = Instant::now();
        let mut error = None;
        loop {
            if STOP.load(Ordering::SeqCst) || start.elapsed() > Duration::from_secs(300) {
                error = Some("Provider stream stopped");
                break;
            }
            let mut line = Vec::new();
            match reader.by_ref().take(2_097_153).read_until(b'\n', &mut line) {
                Ok(0) => break,
                Ok(n) if n <= 2_097_152 => {
                    total += n;
                }
                _ => {
                    error = Some("Provider stream interrupted");
                    break;
                }
            }
            if total > 16 * 1024 * 1024 {
                error = Some("Provider stream exceeds limit");
                break;
            }
            if !native::host(
                "host.stream.emit",
                &json!({"stream_id":id,"payload":STANDARD.encode(line)}),
            ) {
                error = Some("Client stream closed");
                break;
            }
        }
        let _ = native::host("host.stream.close", &json!({"stream_id":id,"error":error}));
    });
    streams.push(handle);
    Ok(json!({"headers":{"Content-Type":["text/event-stream"]}}))
}
