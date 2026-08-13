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
MAX_MANIFEST_TTL_SECONDS = 3600
MAX_INFLIGHT_TRANSFERS = 8
MAX_HTTP_THREADS = 16
REQUEST_TIMEOUT_SECONDS = 10
DEFAULT_ALLOWED_ORIGINS = (
    "https://code4agent-feature-maya-dcc-server-web.seele.chat",
)
_configured_origins = tuple(x.strip() for x in os.environ.get("SEELE_ALLOWED_ORIGINS", "").split(",") if x.strip())
ALLOWED_ORIGINS = tuple(dict.fromkeys(DEFAULT_ALLOWED_ORIGINS + _configured_origins))
DEFAULT_ALLOWED_DOWNLOAD_HOSTS = (
    "static.seeles.ai",
    "seele-asset-public-1.s3.ap-southeast-1.amazonaws.com",
    "d3lzqljvieno0e.cloudfront.net",
    "seelemedia.s3.us-east-1.amazonaws.com",
    "seelemedia.s3.amazonaws.com",
    "seeleh5.blob.core.windows.net",
    "d3vhd1f81y5p6c.cloudfront.net",
)
_configured_download_hosts = tuple(x.strip().lower() for x in os.environ.get("SEELE_ALLOWED_DOWNLOAD_HOSTS", "").split(",") if x.strip())
ALLOWED_DOWNLOAD_HOSTS = tuple(dict.fromkeys(DEFAULT_ALLOWED_DOWNLOAD_HOSTS + _configured_download_hosts))

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
