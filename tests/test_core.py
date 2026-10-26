import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw

from samecut.core import (SamecutError, inventory, normalize_cuts, plan, probe,
                          resolve_reference, share_url, validate_plan)
from samecut.demo import demo


class CoreTests(unittest.TestCase):
    def setUp(self):
        # Keep temporary test data inside the project, on the user's selected disk.
        Path("runs").mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir="runs")
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def image(self,name,color="red"):
        image=Image.new("RGB",(160,120),color)
        ImageDraw.Draw(image).rectangle((30,20,80,90),fill="white")
        image.save(self.root/name)

    def test_share_text_and_domain_boundary(self):
        self.assertEqual(share_url("分享 https://v.douyin.com/abc/ 复制链接"),"https://v.douyin.com/abc/")
        for bad in ["https://douyin.com.evil.test/x","https://127.0.0.1/","https://user@douyin.com/a"]:
            with self.assertRaises(SamecutError): share_url(bad)

    def test_cut_quantization_has_no_gaps_or_tiny_tail(self):
        self.assertEqual(normalize_cuts([.1,.4,.41,1.98],60,30),[0,12,60])

    def test_decoded_and_reencoded_duplicates_removed(self):
        self.image("a.png")
        with Image.open(self.root/"a.png") as im: im.save(self.root/"b.jpg",quality=85)
        self.image("c.png","blue")
        accepted,rejected=inventory(self.root,reviewed_clean=True)
        self.assertEqual(len(accepted),2)
        self.assertEqual(rejected[0]["reason"],"duplicate")

    def test_explicit_watermark_not_overridden_and_unknown_excluded(self):
        self.image("a.png")
        with self.assertRaises(SamecutError): inventory(self.root)
        manifest=self.root/"meta.json"
        manifest.write_text(json.dumps({"a.png":{"watermark":"present"}}))
        with self.assertRaises(SamecutError): inventory(self.root,manifest,reviewed_clean=True)

    def test_recent_dates_inclusive_no_mtime_or_future(self):
        self.image("a.png")
        manifest=self.root/"meta.json"
        for day,ok in [("2026-10-25",True),("2026-10-26",True),("2026-10-24",False),("2026-10-27",False),(None,False)]:
            manifest.write_text(json.dumps({"a.png":{"watermark":"clean","published_at":day}}))
            if ok:
                self.assertTrue(inventory(self.root,manifest,as_of="2026-10-26",recent_days=2)[0][0]["recent"])
            else:
                with self.assertRaises(SamecutError): inventory(self.root,manifest,as_of="2026-10-26",recent_days=2)

    def test_recent_photo_is_used_not_only_collected(self):
        self.image("a.png")
        self.image("z.png","blue")
        manifest=self.root/"meta.json"
        manifest.write_text(json.dumps({"z.png":{"watermark":"clean","published_at":"2026-10-25"}}))
        photos,_=inventory(self.root,manifest,reviewed_clean=True,as_of="2026-10-26",recent_days=2)
        a={"cuts":[0,30],"warnings":[],"width":1920,"height":1080,"fps":30,"total_frames":30}
        recipe=plan(a,photos,["chance","QIANCHENG"])
        self.assertEqual(recipe["scenes"][0]["asset"]["name"],"z.png")

    def test_scarce_assets_merge_cuts_without_repetition(self):
        a={"cuts":[0,15,30,45,60],"warnings":[],"width":1920,"height":1080,"fps":30,"total_frames":60}
        p=plan(a,[{"sha256":"a"},{"sha256":"b"}],["chance","QIANCHENG"])
        validate_plan(p)
        self.assertEqual([s["text"] for s in p["scenes"]],["chance","QIANCHENG"])
        self.assertEqual(len(p["scenes"]),2)
        self.assertTrue(p["warnings"])
        p["scenes"][-1]["end_frame"]-=1
        with self.assertRaises(SamecutError): validate_plan(p)

    def test_duplicate_timeline_rejected(self):
        with self.assertRaises(SamecutError):
            validate_plan({"total_frames":20,"scenes":[
                {"start_frame":0,"end_frame":10,"asset":{"sha256":"x"}},
                {"start_frame":10,"end_frame":20,"asset":{"sha256":"x"}}]})

    def test_failed_download_is_explicit(self):
        with patch("samecut.core.command",side_effect=SamecutError("login needed")):
            with self.assertRaisesRegex(SamecutError,"Upload the reference MP4"):
                resolve_reference("https://v.douyin.com/demo/",self.root)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),"FFmpeg required")
    def test_real_end_to_end_export_has_audio_full_duration_and_final_frame(self):
        output=demo(self.root/"demo")
        result=probe(output)
        self.assertTrue(result["has_audio"])
        self.assertAlmostEqual(result["duration"],4,places=2)
        self.assertTrue((output.parent/"last-frame.jpg").is_file())
        report=json.loads((output.parent/"report.json").read_text())
        self.assertEqual(report["scenes"],4)
        self.assertTrue(report["no_repeated_photos"])


if __name__=="__main__": unittest.main()
