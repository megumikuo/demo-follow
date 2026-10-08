#!/usr/bin/env python3
"""Write a portable video player beside demo.mp4 and poster.jpg; WebM is optional."""
import argparse
import html
from pathlib import Path

HTML = '''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>body{margin:0;background:#f3efe5;color:#29213a;font:16px system-ui;padding:32px}main{max-width:1200px;margin:auto}h1{font-size:28px;font-weight:650}video{width:100%;border-radius:16px;background:#e8e2d5}p{line-height:1.6}a{color:inherit}</style>
<main><h1>__TITLE__</h1>
<video controls muted playsinline preload="metadata" poster="poster.jpg" aria-label="Recorded website walkthrough">
__WEBM_SOURCE__<source src="demo.mp4" type="video/mp4">
<a href="demo.mp4">Download the walkthrough</a></video>
<p>__DESCRIPTION__</p>
<p><a href="demo.mp4" download>Download MP4</a>__WEBM_DOWNLOAD__</p></main>
<script>const v=document.querySelector('video');if(matchMedia('(prefers-reduced-motion: reduce)').matches){v.autoplay=false;v.loop=false}</script></html>
'''


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',default='output/embed.html')
    ap.add_argument('--title',default='Website walkthrough')
    ap.add_argument('--description',default='Recorded from the real website with semantic camera framing.')
    a=ap.parse_args();p=Path(a.out)
    for name in ('demo.mp4','poster.jpg'):
        if not (p.parent/name).is_file():
            ap.error(f'Missing {p.parent/name}; render first')
    has_webm = (p.parent/'demo.webm').is_file()
    page = HTML.replace('__TITLE__',html.escape(a.title)).replace('__DESCRIPTION__',html.escape(a.description))
    page = page.replace('__WEBM_SOURCE__', '<source src="demo.webm" type="video/webm">' if has_webm else '')
    page = page.replace('__WEBM_DOWNLOAD__', ' · <a href="demo.webm" download>Download WebM</a>' if has_webm else '')
    p.write_text(page);print(p)


if __name__=='__main__':
    main()
