"""Loopback-only single-user UI. Not a public multi-tenant upload server."""
import json
import re
import secrets
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .core import IMAGE_EXTENSIONS, SamecutError, run, write_json

MAX_FILE = 250 * 1024 * 1024


class App:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        self.token = secrets.token_urlsafe(32)
        self.jobs = {}
        self.lock = threading.Lock()
        self.render_lock = threading.Lock()

    def create(self):
        ident = secrets.token_hex(12)
        path = self.root/ident
        (path/"photos").mkdir(parents=True)
        self.jobs[ident] = {"status":"uploading","message":"Waiting for files","reference":None,
                            "photos":[],"path":path}
        return ident

    def start(self, ident, options):
        job = self.jobs[ident]
        if job["status"] != "uploading":
            raise SamecutError("Job already started.")
        if not job["photos"]:
            raise SamecutError("Select at least one photo.")
        if options.get("reviewed_clean") is not True:
            raise SamecutError("Please check your photos for watermarks first.")
        if not job["reference"] and not options.get("reference"):
            raise SamecutError("Upload a reference video or paste its share link.")
        aliases = options.get("aliases",[])
        if not isinstance(aliases,list) or not aliases or not all(isinstance(a,str) and 0<len(a)<=60 for a in aliases):
            raise SamecutError("Enter at least one name, at most 60 characters each.")
        meta = options.get("metadata",{})
        if not isinstance(meta,dict):
            raise SamecutError("Invalid photo metadata.")
        manifest = {}
        for name in job["photos"]:
            data = meta.get(name,{})
            published = data.get("published_at")
            if published:
                date.fromisoformat(published)
            manifest[name] = {"watermark":"clean","published_at":published,"source_url":data.get("source_url")}
        write_json(job["path"]/"assets.json",manifest)
        job["status"] = "queued"
        def worker():
            with self.render_lock:
                job["status"] = "running"
                try:
                    def progress(msg):
                        job["message"] = msg
                    run(str(job["reference"] or options["reference"]),job["path"]/"photos",job["path"]/"output",
                        aliases=aliases,manifest=job["path"]/"assets.json",width=int(options.get("width",1280)),
                        recent_days=2 if options.get("require_recent") else None,
                        as_of=options.get("as_of") or None,progress=progress)
                    job["status"] = "complete"
                except Exception as exc:
                    job["status"] = "error"
                    job["message"] = str(exc)
        threading.Thread(target=worker,daemon=True).start()


def handler_for(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass

        def send(self,status,body,kind="application/json; charset=utf-8"):
            if isinstance(body,(dict,list)):
                body = json.dumps(body,ensure_ascii=False).encode("utf-8")
            elif isinstance(body,str):
                body = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type",kind)
            self.send_header("Content-Length",str(len(body)))
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Cache-Control","no-store")
            self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' blob:; media-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get("Host") in {f"127.0.0.1:{self.server.server_port}",f"localhost:{self.server.server_port}"}

        def authorized(self):
            if not self.valid_host():
                return False
            origin = self.headers.get("Origin")
            if origin and origin not in {f"http://127.0.0.1:{self.server.server_port}",f"http://localhost:{self.server.server_port}"}:
                return False
            return secrets.compare_digest(self.headers.get("X-Samecut-Token",""),app.token)

        def do_GET(self):
            if not self.valid_host():
                self.send(403,{"error":"Invalid host"}); return
            parts = urlsplit(self.path).path.strip("/").split("/")
            if parts == [""]:
                html = (Path(__file__).parent/"static"/"index.html").read_text(encoding="utf-8")
                self.send(200,html.replace("__TOKEN__",app.token),"text/html; charset=utf-8")
            elif len(parts)==3 and parts[0]=="jobs" and parts[1] in app.jobs:
                job = app.jobs[parts[1]]
                if parts[2]=="status":
                    self.send(200,{k:job[k] for k in ["status","message"]})
                elif parts[2] in {"video.mp4","report.json","recipe.json"} and job["status"]=="complete":
                    p = job["path"]/"output"/parts[2]
                    # Single byte ranges support browser video seeking without loading everything.
                    size = p.stat().st_size
                    start,end = 0,size-1
                    range_header = self.headers.get("Range")
                    if range_header:
                        match = re.fullmatch(r"bytes=(\d*)-(\d*)",range_header)
                        if not match or not any(match.groups()):
                            self.send(416,{"error":"Invalid byte range"}); return
                        first,last = match.groups()
                        if first:
                            start = int(first)
                            end = min(int(last),size-1) if last else size-1
                        else:
                            start = max(0,size-int(last))
                        if start >= size or end < start:
                            self.send(416,{"error":"Unsatisfiable byte range"}); return
                    self.send_response(206 if range_header else 200)
                    self.send_header("Content-Type","video/mp4" if p.suffix==".mp4" else "application/json")
                    self.send_header("Content-Length",str(end-start+1))
                    self.send_header("Accept-Ranges","bytes")
                    if range_header:
                        self.send_header("Content-Range",f"bytes {start}-{end}/{size}")
                    self.send_header("X-Content-Type-Options","nosniff")
                    self.end_headers()
                    with p.open("rb") as src:
                        src.seek(start)
                        remaining = end-start+1
                        while remaining and (chunk := src.read(min(1024*1024,remaining))):
                            self.wfile.write(chunk)
                            remaining -= len(chunk)
                else:
                    self.send(404,{"error":"Not found"})
            else:
                self.send(404,{"error":"Not found"})

        def do_POST(self):
            if not self.authorized():
                self.send(403,{"error":"Invalid origin or session token"}); return
            try:
                parts = urlsplit(self.path).path.strip("/").split("/")
                length = int(self.headers.get("Content-Length","0"))
                limit = MAX_FILE if len(parts)==4 and parts[2]=="upload" else 65536
                if not 0 <= length <= limit:
                    self.send(413,{"error":"File too large (250 MB per file)"}); return
                if parts==["jobs"]:
                    self.rfile.read(length)
                    with app.lock:
                        if len(app.jobs) >= 50:
                            raise SamecutError("Session job limit reached. Restart the local server.")
                        ident = app.create()
                    self.send(200,{"id":ident}); return
                if len(parts) < 3 or parts[0]!="jobs" or parts[1] not in app.jobs:
                    self.send(404,{"error":"Not found"}); return
                job = app.jobs[parts[1]]
                if len(parts)==4 and parts[2]=="upload":
                    with app.lock:
                        if job["status"] != "uploading":
                            raise SamecutError("Uploads are closed for this job.")
                        name = parts[3]
                        # Client uses generated numeric names, never trusts a filesystem path.
                        if not name or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for c in name):
                            raise SamecutError("Invalid filename.")
                        is_ref = name == "reference.mp4"
                        if not is_ref and Path(name).suffix not in IMAGE_EXTENSIONS:
                            raise SamecutError("Unsupported photo type.")
                        if len(job["photos"]) >= 120:
                            raise SamecutError("Maximum 120 photos per job.")
                        destination = job["path"]/name if is_ref else job["path"]/"photos"/name
                        remaining = length
                        with destination.open("xb") as dest:
                            while remaining:
                                chunk = self.rfile.read(min(1024*1024,remaining))
                                if not chunk:
                                    raise SamecutError("Incomplete upload.")
                                dest.write(chunk)
                                remaining -= len(chunk)
                        if is_ref:
                            job["reference"] = destination
                        else:
                            job["photos"].append(name)
                    self.send(200,{"file":name}); return
                if len(parts)==3 and parts[2]=="start":
                    options = json.loads(self.rfile.read(length))
                    with app.lock:
                        app.start(parts[1],options)
                    self.send(202,{"status":"queued"}); return
                self.send(404,{"error":"Not found"})
            except (SamecutError,ValueError,OSError,KeyError,TypeError) as exc:
                self.send(400,{"error":str(exc)})
    return Handler


def serve(port=8765,workdir="runs"):
    app = App(workdir)
    server = ThreadingHTTPServer(("127.0.0.1",port),handler_for(app))
    server.daemon_threads = True
    print(f"Samecut → http://127.0.0.1:{server.server_port} (Ctrl+C to stop)",flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
