"""Windows reparse-safe staging using handle-relative NT file operations."""
import ctypes
import os
from ctypes import wintypes

if os.name == "nt":
    import msvcrt

    ntdll=ctypes.WinDLL("ntdll",use_last_error=True)
    kernel32=ctypes.WinDLL("kernel32",use_last_error=True)
    ULONG_PTR=wintypes.WPARAM

    class IO_STATUS_BLOCK(ctypes.Structure):
        _fields_=[("Status",wintypes.LONG),("Information",ULONG_PTR)]
    class UNICODE_STRING(ctypes.Structure):
        _fields_=[("Length",wintypes.USHORT),("MaximumLength",wintypes.USHORT),("Buffer",wintypes.LPWSTR)]
    class OBJECT_ATTRIBUTES(ctypes.Structure):
        _fields_=[("Length",wintypes.ULONG),("RootDirectory",wintypes.HANDLE),("ObjectName",ctypes.POINTER(UNICODE_STRING)),("Attributes",wintypes.ULONG),("SecurityDescriptor",wintypes.LPVOID),("SecurityQualityOfService",wintypes.LPVOID)]
    class FILE_ATTRIBUTE_TAG_INFO(ctypes.Structure):
        _fields_=[("FileAttributes",wintypes.DWORD),("ReparseTag",wintypes.DWORD)]
    class FILE_RENAME_INFO_HEADER(ctypes.Structure):
        _fields_=[("ReplaceIfExists",wintypes.BYTE),("RootDirectory",wintypes.HANDLE),("FileNameLength",wintypes.DWORD),("FileName",wintypes.WCHAR*1)]

    FILE_LIST_DIRECTORY=0x0001; FILE_READ_ATTRIBUTES=0x0080; FILE_WRITE_DATA=0x0002
    DELETE=0x00010000; SYNCHRONIZE=0x00100000
    SHARE_ALL=0x00000007; FILE_OPEN=1; FILE_CREATE=2
    OPEN_EXISTING=3
    FILE_DIRECTORY_FILE=0x00000001; FILE_SYNCHRONOUS_IO_NONALERT=0x00000020
    FILE_NON_DIRECTORY_FILE=0x00000040; FILE_OPEN_REPARSE_POINT=0x00200000
    OBJ_CASE_INSENSITIVE=0x40; FILE_ATTRIBUTE_REPARSE_POINT=0x400
    FILE_ATTRIBUTE_TAG_INFO_CLASS=9; FILE_RENAME_INFO_CLASS=3
    FILE_RENAME_INFORMATION_CLASS=10

    ntdll.NtCreateFile.argtypes=[ctypes.POINTER(wintypes.HANDLE),wintypes.DWORD,ctypes.POINTER(OBJECT_ATTRIBUTES),ctypes.POINTER(IO_STATUS_BLOCK),ctypes.POINTER(ctypes.c_longlong),wintypes.ULONG,wintypes.ULONG,wintypes.ULONG,wintypes.ULONG,wintypes.LPVOID,wintypes.ULONG]
    ntdll.NtCreateFile.restype=wintypes.LONG
    ntdll.NtSetInformationFile.argtypes=[wintypes.HANDLE,ctypes.POINTER(IO_STATUS_BLOCK),wintypes.LPVOID,wintypes.ULONG,wintypes.INT]
    ntdll.NtSetInformationFile.restype=wintypes.LONG
    kernel32.GetFileInformationByHandleEx.argtypes=[wintypes.HANDLE,wintypes.INT,wintypes.LPVOID,wintypes.DWORD]
    kernel32.GetFileInformationByHandleEx.restype=wintypes.BOOL
    kernel32.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    kernel32.CreateFileW.restype=wintypes.HANDLE
    kernel32.SetFileInformationByHandle.argtypes=[wintypes.HANDLE,wintypes.INT,wintypes.LPVOID,wintypes.DWORD]
    kernel32.SetFileInformationByHandle.restype=wintypes.BOOL
    kernel32.CloseHandle.argtypes=[wintypes.HANDLE]

def _nt_open(parent,name,access,disposition,options):
    buffer=ctypes.create_unicode_buffer(name); encoded=name.encode("utf-16-le")
    unicode=UNICODE_STRING(len(encoded),len(encoded),ctypes.cast(buffer,wintypes.LPWSTR))
    attributes=OBJECT_ATTRIBUTES(ctypes.sizeof(OBJECT_ATTRIBUTES),parent,ctypes.pointer(unicode),OBJ_CASE_INSENSITIVE,None,None)
    handle=wintypes.HANDLE(); iosb=IO_STATUS_BLOCK(); allocation=ctypes.c_longlong(0)
    status=ntdll.NtCreateFile(ctypes.byref(handle),access,ctypes.byref(attributes),ctypes.byref(iosb),ctypes.byref(allocation),0,SHARE_ALL,disposition,options,None,0)
    if status<0: raise OSError("WINDOWS_SAFE_OPEN_FAILED: 0x%08X" % (status & 0xffffffff))
    return handle

def _reject_reparse(handle):
    info=FILE_ATTRIBUTE_TAG_INFO()
    if not kernel32.GetFileInformationByHandleEx(handle,FILE_ATTRIBUTE_TAG_INFO_CLASS,ctypes.byref(info),ctypes.sizeof(info)): raise ctypes.WinError(ctypes.get_last_error())
    if info.FileAttributes & FILE_ATTRIBUTE_REPARSE_POINT: raise ValueError("PATH_UNSAFE")

def open_parent(root,relative):
    root_handle=kernel32.CreateFileW(root,FILE_LIST_DIRECTORY|FILE_READ_ATTRIBUTES|SYNCHRONIZE,SHARE_ALL,None,OPEN_EXISTING,0x02000000|FILE_OPEN_REPARSE_POINT,None)
    if root_handle==wintypes.HANDLE(-1).value: raise ctypes.WinError(ctypes.get_last_error())
    handles=[root_handle]
    try:
        _reject_reparse(handles[-1])
        components=["files"]+[part for part in os.path.dirname(relative).replace("\\","/").split("/") if part]
        for component in components:
            handle=_nt_open(handles[-1],component,FILE_LIST_DIRECTORY|FILE_READ_ATTRIBUTES|SYNCHRONIZE,FILE_OPEN,FILE_DIRECTORY_FILE|FILE_OPEN_REPARSE_POINT|FILE_SYNCHRONOUS_IO_NONALERT)
            _reject_reparse(handle); handles.append(handle)
        parent=handles.pop(); return parent
    finally:
        for handle in handles: kernel32.CloseHandle(handle)

def create_part(parent,leaf):
    handle=_nt_open(parent,leaf+".part",FILE_WRITE_DATA|FILE_READ_ATTRIBUTES|DELETE|SYNCHRONIZE,FILE_CREATE,FILE_NON_DIRECTORY_FILE|FILE_OPEN_REPARSE_POINT|FILE_SYNCHRONOUS_IO_NONALERT)
    _reject_reparse(handle)
    fd=msvcrt.open_osfhandle(handle.value,os.O_WRONLY|os.O_BINARY)
    return os.fdopen(fd,"wb")

def rename_part(file_object,parent,leaf):
    file_object.flush(); os.fsync(file_object.fileno())
    handle=wintypes.HANDLE(msvcrt.get_osfhandle(file_object.fileno()))
    encoded=leaf.encode("utf-16-le"); filename_offset=FILE_RENAME_INFO_HEADER.FileName.offset; size=filename_offset+len(encoded)
    buffer=ctypes.create_string_buffer(size); header=ctypes.cast(buffer,ctypes.POINTER(FILE_RENAME_INFO_HEADER)).contents
    header.ReplaceIfExists=False; header.RootDirectory=parent; header.FileNameLength=len(encoded)
    ctypes.memmove(ctypes.addressof(buffer)+filename_offset,encoded,len(encoded))
    iosb=IO_STATUS_BLOCK(); status=ntdll.NtSetInformationFile(handle,ctypes.byref(iosb),buffer,size,FILE_RENAME_INFORMATION_CLASS)
    if status<0: raise OSError("WINDOWS_SAFE_RENAME_FAILED: 0x%08X" % (status & 0xffffffff))

def close_handle(handle): kernel32.CloseHandle(handle)
