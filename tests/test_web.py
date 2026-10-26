import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from samecut.web import App, handler_for


class WebTests(unittest.TestCase):
    def setUp(self):
        Path("runs").mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir="runs")
        self.app=App(self.tmp.name)
        self.server=ThreadingHTTPServer(("127.0.0.1",0),handler_for(self.app))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.base=f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self,path,data=None,token=True,extra=None):
        headers={"X-Samecut-Token":self.app.token} if token else {}
        headers.update(extra or {})
        return urlopen(Request(self.base+path,data=data,headers=headers),timeout=5)

    def test_page_and_csrf_protection(self):
        with self.request("/") as r: self.assertIn(b"samecut",r.read())
        for extra,token in [({},False),({"Origin":"https://evil.example"},True),({"Host":"evil.example"},True)]:
            with self.assertRaises(HTTPError) as ctx: self.request("/jobs",b"",token,extra)
            self.assertEqual(ctx.exception.code,403)

    def test_upload_and_no_traversal(self):
        with self.request("/jobs",b"") as r: ident=json.load(r)["id"]
        with self.request(f"/jobs/{ident}/upload/photo-0.png",b"placeholder") as r: self.assertEqual(r.status,200)
        self.assertEqual((self.app.jobs[ident]["path"]/"photos"/"photo-0.png").read_bytes(),b"placeholder")
        with self.assertRaises(HTTPError): self.request(f"/jobs/{ident}/upload/..%2fsecret.png",b"x")
        with self.assertRaises(HTTPError): self.request(f"/jobs/{ident}/upload/code.py",b"x")

    def test_start_requires_review(self):
        with self.request("/jobs",b"") as r: ident=json.load(r)["id"]
        with self.request(f"/jobs/{ident}/upload/photo-0.png",b"x"): pass
        with self.assertRaises(HTTPError) as ctx: self.request(f"/jobs/{ident}/start",b'{}')
        self.assertEqual(ctx.exception.code,400)

    def test_video_byte_ranges_for_browser_seeking(self):
        ident=self.app.create()
        job=self.app.jobs[ident]
        job["status"]="complete"
        (job["path"]/"output").mkdir()
        (job["path"]/"output"/"video.mp4").write_bytes(b"0123456789")
        for byte_range,expected in [("bytes=2-5",b"2345"),("bytes=-3",b"789"),("bytes=7-",b"789")]:
            with self.request(f"/jobs/{ident}/video.mp4",extra={"Range":byte_range}) as r:
                self.assertEqual(r.status,206)
                self.assertEqual(r.read(),expected)
        with self.assertRaises(HTTPError) as ctx:
            self.request(f"/jobs/{ident}/video.mp4",extra={"Range":"bytes=20-"})
        self.assertEqual(ctx.exception.code,416)


if __name__=="__main__": unittest.main()
