use super::dispatch;
use serde_json::json;
use std::{
    ffi::{c_char, c_void, CStr},
    ptr,
};
#[repr(C)]
pub struct Buffer {
    ptr: *mut u8,
    len: usize,
}
type HostCall =
    unsafe extern "C" fn(*mut c_void, *const c_char, *const u8, usize, *mut Buffer) -> i32;
#[repr(C)]
pub struct HostApi {
    abi_version: u32,
    host_ctx: *mut c_void,
    call: Option<HostCall>,
    free_buffer: Option<unsafe extern "C" fn(*mut c_void, usize)>,
}
#[repr(C)]
pub struct PluginApi {
    abi_version: u32,
    call: Option<unsafe extern "C" fn(*const c_char, *const u8, usize, *mut Buffer) -> i32>,
    free_buffer: Option<unsafe extern "C" fn(*mut c_void, usize)>,
    shutdown: Option<unsafe extern "C" fn()>,
}

/// Initialize the CLIProxyAPI v1 native ABI.
///
/// # Safety
/// The host must provide valid, aligned ABI structures for the duration of this call.
#[no_mangle]
pub unsafe extern "C" fn cliproxy_plugin_init(host: *const HostApi, plugin: *mut PluginApi) -> i32 {
    if host.is_null() || plugin.is_null() || (*host).abi_version != 1 {
        return 1;
    }
    ptr::write(
        plugin,
        PluginApi {
            abi_version: 1,
            call: Some(call),
            free_buffer: Some(free),
            shutdown: Some(shutdown),
        },
    );
    0
}
unsafe extern "C" fn call(
    method: *const c_char,
    request: *const u8,
    len: usize,
    response: *mut Buffer,
) -> i32 {
    if response.is_null() {
        return 1;
    }
    ptr::write(
        response,
        Buffer {
            ptr: ptr::null_mut(),
            len: 0,
        },
    );
    if method.is_null() || len > 64 * 1024 || (request.is_null() && len != 0) {
        return 1;
    }
    let result = std::panic::catch_unwind(|| {
        let method = CStr::from_ptr(method).to_str().unwrap_or("");
        let bytes = if len == 0 { &[] } else { std::slice::from_raw_parts(request, len) };
        dispatch(method, bytes)
    }).unwrap_or_else(|_| json!({"ok": false, "error": {"code": "plugin_error", "message": "Plugin operation failed"}}));
    let bytes = result.to_string().into_bytes().into_boxed_slice();
    let len = bytes.len();
    ptr::write(
        response,
        Buffer {
            ptr: Box::into_raw(bytes) as *mut u8,
            len,
        },
    );
    0
}
unsafe extern "C" fn free(p: *mut c_void, len: usize) {
    if !p.is_null() {
        drop(Box::from_raw(ptr::slice_from_raw_parts_mut(
            p as *mut u8,
            len,
        )));
    }
}
unsafe extern "C" fn shutdown() {
    let _ = std::panic::catch_unwind(|| dispatch("plugin.shutdown", b"{}"));
}
