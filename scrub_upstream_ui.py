from pathlib import Path
import re

root = Path("/opt/agnes-base")
static = root / "static"

# Remove upstream author-owned labels/URLs from source templates and compiled assets.
bad_strings = [
    "支持项目", "快速入口", "更多资源", "给个 Star", "在线体验",
    "Prompt 技巧", "API 文档", "模型概览", "Demo", "Guides", "FAQ",
    "video.lichuanyang.top", "github.com/lcy362/agnes-video-generator",
    "lcy362/agnes-video-generator", "lichuanyang.top",
    "Agnes Video Generator",
]
for p in list(root.rglob("*.vue")) + list(root.rglob("*.js")) + list(root.rglob("*.html")):
    try:
        s = p.read_text()
    except Exception:
        continue
    old = s
    for x in bad_strings:
        s = s.replace(x, "")
    if s != old:
        p.write_text(s)

# Compiled frontend can still contain the original strings after npm build.
# Scrub static text after build as the final build-stage operation.
for p in static.rglob("*"):
    if not p.is_file() or p.suffix.lower() not in {".js", ".html", ".css", ".map"}:
        continue
    try:
        s = p.read_text()
    except Exception:
        continue
    old = s
    for x in bad_strings:
        s = s.replace(x, "")
    if s != old:
        p.write_text(s)

# Strong runtime selector: hide likely upstream promotion containers even if
# a future upstream release changes the exact wording.
css = static / "night-agency-cleanup.css"
css.write_text("""
/* Night Agency: upstream author promotion is removed, not merely relabeled. */
a[href*="lichuanyang.top"],
a[href*="lcy362/agnes-video-generator"],
[href*="支持项目"],
[href*="快速入口"],
[href*="更多资源"] {
  display:none !important;
}
""")
