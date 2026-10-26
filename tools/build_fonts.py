#!/usr/bin/env python3
"""결 고운 하루 홈페이지 웹폰트 빌드 스크립트

사이트의 모든 HTML·llms.txt에 실제로 쓰인 글자만 골라 폰트를 작게 잘라(subset)
fonts/ 폴더에 woff2로 저장하고, 모든 HTML의 폰트 블록을 새 버전으로 바꾼다.

새 노트를 추가하거나 글을 고친 뒤 배포 전에 한 번 실행한다:
    python3 tools/build_fonts.py

원본 폰트(구글 폰트와 같은 파일, SIL OFL 라이선스)는 npm의 @expo-google-fonts
패키지에서 임시 폴더로 받아 쓴다. 필요 도구: node(npm), pip의 fonttools·brotli.
"""
import glob
import hashlib
import html
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(ROOT, "fonts")

# (출력 파일명, npm 패키지, 패키지 안 ttf 경로, CSS family, weight)
# 본문 글꼴은 휴대폰 속도를 위해 웹 글꼴을 쓰지 않고 기기 기본 글꼴을 쓴다(2026-10-26 사용자 결정).
# 웹 글꼴은 제목용 고운돋움과 영문 라벨용 IBM Plex Mono만 받는다.
FONTS = [
    ("gowun-dodum-400", "gowun-dodum", "400Regular/GowunDodum_400Regular.ttf", "Gowun Dodum", 400),
    ("ibm-plex-mono-400", "ibm-plex-mono", "400Regular/IBMPlexMono_400Regular.ttf", "IBM Plex Mono", 400),
    ("ibm-plex-mono-500", "ibm-plex-mono", "500Medium/IBMPlexMono_500Medium.ttf", "IBM Plex Mono", 500),
]
# 첫 화면에 바로 필요한 폰트만 미리 불러온다
PRELOAD = ["gowun-dodum-400"]

START, END = "<!--fonts:start-->", "<!--fonts:end-->"
GOOGLE_BLOCK = re.compile(
    r'<link rel="preconnect" href="https://fonts\.googleapis\.com">\s*'
    r'<link rel="preconnect" href="https://fonts\.gstatic\.com" crossorigin>\s*'
)
GOOGLE_CSS = re.compile(
    r'<link rel="preload" as="style" href="https://fonts\.googleapis\.com[^>]*>\s*'
    r'<noscript><link rel="stylesheet" href="https://fonts\.googleapis\.com[^>]*></noscript>\s*'
)


def html_files():
    files = glob.glob(os.path.join(ROOT, "*.html")) + glob.glob(os.path.join(ROOT, "notes", "*.html"))
    return [f for f in files if not os.path.basename(f).startswith("google")]


def collect_chars():
    text = ""
    for f in html_files() + [os.path.join(ROOT, "llms.txt")]:
        t = open(f, encoding="utf-8").read()
        t = re.sub(r"<style.*?</style>", "", t, flags=re.S)
        text += html.unescape(t)
    chars = set(text)
    chars |= {chr(i) for i in range(0x20, 0x7F)}  # 영문·숫자·기호 전체
    chars |= set("·•—–…“”‘’「」『』《》〈〉→←↑↓×÷±°※★☆○●◎□■△▲▽▼◇◆♪♩♬✓①②③④⑤⑥⑦⑧⑨⑩")
    return "".join(sorted(c for c in chars if c >= " "))


EXTRA = {chr(i) for i in range(0x20, 0x7F)} | set("·•—–…“”‘’「」『』《》〈〉→←↑↓×♪✓")


def collect_rendered_chars(family):
    """페이지를 실제로 열어 이 글꼴로 그려지는 글자만 모은다(제목용 글꼴을 작게 만들기 위함).
    playwright(크로미움)가 없으면 None을 돌려주고, 그때는 사이트 전체 글자를 쓴다."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    import functools, http.server, threading
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT)
    handler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/"
    pages = [os.path.relpath(f, ROOT) for f in html_files()]
    js = """(fam)=>{const s=new Set();const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n;
      while(n=w.nextNode()){const el=n.parentElement;if(!el)continue;
        const f=getComputedStyle(el).fontFamily.replace(/["']/g,'').trim();
        if(f.startsWith(fam)){for(const c of n.textContent)s.add(c);}}
      return [...s].join('');}"""
    chars = set()
    try:
        with sync_playwright() as p:
            exe = next(iter(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux64/chrome")), None)
            browser = p.chromium.launch(**({"executable_path": exe} if exe else {}))
            for width in (390, 1350):
                page = browser.new_page(viewport={"width": width, "height": 900})
                page.route(lambda u: not u.startswith(base), lambda r: r.abort())
                for u in pages:
                    page.goto(base + u.replace(os.sep, "/"))
                    chars |= set(page.evaluate(js, family))
                    for btn in page.query_selector_all(".note-tabs button"):  # 노트 분류 탭마다 카드 제목
                        btn.click()
                        chars |= set(page.evaluate(js, family))
            browser.close()
    except Exception as e:  # 브라우저를 못 띄우면 안전하게 전체 글자로
        print("렌더링 글자 수집 실패, 전체 글자 사용:", e)
        return None
    finally:
        srv.shutdown()
    return "".join(sorted(c for c in chars | EXTRA if c >= " "))


def fetch_sources(tmp):
    pkgs = sorted({f"@expo-google-fonts/{p}" for _, p, _, _, _ in FONTS})
    subprocess.run(["npm", "i", "--silent", "--prefix", tmp, *pkgs], check=True)
    return os.path.join(tmp, "node_modules", "@expo-google-fonts")


def build(chars):
    os.makedirs(FONT_DIR, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = fetch_sources(tmp)
        rendered = {}
        for name, pkg, path, fam, _ in FONTS:
            out = os.path.join(FONT_DIR, name + ".woff2")
            if fam not in rendered:
                rendered[fam] = collect_rendered_chars(fam) or chars
                print(f"{fam}: 글자 {len(rendered[fam])}개")
            textfile = os.path.join(tmp, name + ".txt")
            open(textfile, "w", encoding="utf-8").write(rendered[fam])
            subprocess.run([
                sys.executable, "-m", "fontTools.subset", os.path.join(src, pkg, path),
                f"--text-file={textfile}", "--flavor=woff2", f"--output-file={out}",
                "--layout-features=kern,liga,calt,ccmp,locl", "--no-hinting", "--desubroutinize",
            ], check=True)
            print(f"{name}.woff2  {os.path.getsize(out)/1024:.0f} KB")


def version():
    h = hashlib.sha1()
    for name, *_ in FONTS:
        h.update(open(os.path.join(FONT_DIR, name + ".woff2"), "rb").read())
    return h.hexdigest()[:8]


def font_block(ver):
    lines = [START]
    for name in PRELOAD:
        lines.append(f'<link rel="preload" href="/fonts/{name}.woff2?v={ver}" as="font" type="font/woff2" crossorigin>')
    faces = "".join(
        f'@font-face{{font-family:"{fam}";font-style:normal;font-weight:{w};font-display:swap;'
        f'src:url(/fonts/{name}.woff2?v={ver}) format("woff2")}}'
        for name, _, _, fam, w in FONTS
    )
    lines.append(f"<style>{faces}</style>")
    lines.append(END)
    return "\n".join(lines) + "\n"


BODY_OLD = '--body:"Noto Sans KR",system-ui,-apple-system,"Apple SD Gothic Neo",sans-serif;'
BODY_NEW = '--body:"Noto Sans KR","Apple SD Gothic Neo","Malgun Gothic",system-ui,-apple-system,sans-serif;'


def patch_html(ver):
    block = font_block(ver)
    for f in html_files():
        t = open(f, encoding="utf-8").read()
        orig = t
        t = t.replace(BODY_OLD, BODY_NEW)
        if START in t:
            t = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n?", lambda m: block, t, flags=re.S)
        elif GOOGLE_CSS.search(t):
            t = GOOGLE_BLOCK.sub("", t)
            t = GOOGLE_CSS.sub(lambda m: block, t)
        else:
            continue
        if t != orig:
            open(f, "w", encoding="utf-8").write(t)
            print("updated", os.path.relpath(f, ROOT))


if __name__ == "__main__":
    chars = collect_chars()
    print(f"글자 수: {len(chars)}")
    build(chars)
    patch_html(version())
