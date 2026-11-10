"""Raw UTF-8 Credential Manager blobs, interoperable with the Rust helper."""
import ctypes
from ctypes import wintypes as w
from .security import SafeError


class Credential(ctypes.Structure):
    _fields_=[('Flags',w.DWORD),('Type',w.DWORD),('TargetName',w.LPWSTR),('Comment',w.LPWSTR),
        ('LastWritten',w.FILETIME),('CredentialBlobSize',w.DWORD),('CredentialBlob',ctypes.POINTER(ctypes.c_ubyte)),
        ('Persist',w.DWORD),('AttributeCount',w.DWORD),('Attributes',ctypes.c_void_p),('TargetAlias',w.LPWSTR),('UserName',w.LPWSTR)]


def api():
    dll=ctypes.WinDLL('advapi32',use_last_error=True)
    dll.CredWriteW.argtypes=[ctypes.POINTER(Credential),w.DWORD];dll.CredWriteW.restype=w.BOOL
    dll.CredReadW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,ctypes.POINTER(ctypes.POINTER(Credential))];dll.CredReadW.restype=w.BOOL
    dll.CredFree.argtypes=[ctypes.c_void_p];dll.CredFree.restype=None
    return dll


def put(target,value):
    raw=value.encode('utf-8')
    if not raw or len(raw)>2560:raise SafeError('Windows credential is empty or exceeds its supported blob size.')
    blob=(ctypes.c_ubyte*len(raw)).from_buffer_copy(raw)
    credential=Credential(Type=1,TargetName=target,CredentialBlobSize=len(raw),CredentialBlob=blob,Persist=2,UserName='ECPA MCP gateway')
    try:
        if not api().CredWriteW(ctypes.byref(credential),0):raise SafeError('Windows Credential Manager could not save this credential.')
    finally:ctypes.memset(blob,0,len(raw))


def get(target):
    dll=api();pointer=ctypes.POINTER(Credential)()
    if not dll.CredReadW(target,1,0,ctypes.byref(pointer)):raise SafeError('Credential is unavailable for this Windows user.')
    try:
        record=pointer.contents
        if not record.CredentialBlob or not 0<record.CredentialBlobSize<=8192:raise SafeError('Invalid stored credential.')
        return ctypes.string_at(record.CredentialBlob,record.CredentialBlobSize).decode('utf-8')
    except UnicodeError:raise SafeError('Stored credential encoding is incompatible; re-bootstrap under this identity.') from None
    finally:dll.CredFree(pointer)
