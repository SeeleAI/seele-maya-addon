import os
import json
import platform
import uuid

HOST = "127.0.0.1"
PORT = int(os.environ.get("SEELE_MAYA_PORT", "9879"))
MAX_BODY_BYTES = 2 * 1024 * 1024
CHALLENGE_TTL_SECONDS = 60
MAX_FILES = 128
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
ALLOWED_ORIGINS = tuple(x.strip() for x in os.environ.get("SEELE_ALLOWED_ORIGINS", "").split(",") if x.strip())
ALLOWED_DOWNLOAD_HOSTS = tuple(x.strip().lower() for x in os.environ.get("SEELE_ALLOWED_DOWNLOAD_HOSTS", "").split(",") if x.strip())

def data_dir():
    if platform.system() == "Windows":
        base=os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base,"Seele","MayaTransfer")
    return os.path.expanduser("~/Library/Application Support/Seele/MayaTransfer")

def receiver_id():
    root=data_dir(); path=os.path.join(root,"receiver.json")
    try:
        with open(path,"r",encoding="utf-8") as stream: return json.load(stream)["receiverId"]
    except (OSError, ValueError, KeyError):
        value="maya-"+str(uuid.uuid4())
        try:
            os.makedirs(root,exist_ok=True)
            with open(path,"w",encoding="utf-8") as stream: json.dump({"receiverId":value},stream)
        except OSError: pass
        return value
