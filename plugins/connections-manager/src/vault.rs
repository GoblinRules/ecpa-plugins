use zeroize::Zeroizing;
pub trait Vault {
    fn read(&self, target: &str) -> Result<Zeroizing<String>, String>;
    fn write(&self, target: &str, secret: &str) -> Result<(), String>;
    fn delete(&self, target: &str) -> Result<(), String>;
}
pub struct SystemVault;
#[cfg(windows)]
mod windows {
    use super::*;
    use windows_sys::Win32::{
        Foundation::{GetLastError, ERROR_NOT_FOUND},
        Security::Credentials::*,
    };
    fn wide(s: &str) -> Vec<u16> {
        s.encode_utf16().chain(Some(0)).collect()
    }
    impl Vault for SystemVault {
        fn read(&self, target: &str) -> Result<Zeroizing<String>, String> {
            let name = wide(target);
            let mut credential = std::ptr::null_mut();
            unsafe {
                if CredReadW(name.as_ptr(), CRED_TYPE_GENERIC, 0, &mut credential) == 0 {
                    return Err(
                        "Credential unavailable for this Windows user. Save the token again."
                            .into(),
                    );
                }
                if (*credential).CredentialBlobSize == 0 || (*credential).CredentialBlob.is_null() {
                    CredFree(credential.cast());
                    return Err("Stored token is empty; save it again".into());
                }
                let bytes = std::slice::from_raw_parts(
                    (*credential).CredentialBlob,
                    (*credential).CredentialBlobSize as usize,
                );
                let result = String::from_utf8(bytes.to_vec())
                    .map(Zeroizing::new)
                    .map_err(|_| "Invalid stored credential".into());
                CredFree(credential.cast());
                result
            }
        }
        fn write(&self, target: &str, secret: &str) -> Result<(), String> {
            let mut name = wide(target);
            let mut user = wide("ECPA Connections");
            let credential = CREDENTIALW {
                Type: CRED_TYPE_GENERIC,
                TargetName: name.as_mut_ptr(),
                CredentialBlobSize: secret.len() as u32,
                CredentialBlob: secret.as_ptr() as *mut u8,
                Persist: CRED_PERSIST_LOCAL_MACHINE,
                UserName: user.as_mut_ptr(),
                ..unsafe { std::mem::zeroed() }
            };
            if unsafe { CredWriteW(&credential, 0) } == 0 {
                Err("Windows Credential Manager could not save the token".into())
            } else {
                Ok(())
            }
        }
        fn delete(&self, target: &str) -> Result<(), String> {
            if unsafe { CredDeleteW(wide(target).as_ptr(), CRED_TYPE_GENERIC, 0) } == 0
                && unsafe { GetLastError() } != ERROR_NOT_FOUND
            {
                Err("Windows Credential Manager could not remove the token".into())
            } else {
                Ok(())
            }
        }
    }
}
#[cfg(not(windows))]
impl Vault for SystemVault {
    fn read(&self, _: &str) -> Result<Zeroizing<String>, String> {
        Err("This release requires Windows Credential Manager".into())
    }
    fn write(&self, _: &str, _: &str) -> Result<(), String> {
        Err("This release requires Windows Credential Manager".into())
    }
    fn delete(&self, _: &str) -> Result<(), String> {
        Err("This release requires Windows Credential Manager".into())
    }
}
