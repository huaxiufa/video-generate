from pathlib import Path
import re

root = Path('/opt/agnes-base/frontend/src')
app = root / 'App.vue'
s = app.read_text()
# Remove original promotional/support sidebars and external resource navigation.
s = re.sub(r'\n\s*<!-- Left sidebar -->.*?\n\s*<!-- Main content -->', '\n    <!-- Main content -->', s, flags=re.S)
s = re.sub(r'\n\s*<!-- Resource links（窄屏可换行） -->.*?</nav>', '', s, flags=re.S)
s = re.sub(r'\n\s*<!-- Footer -->.*?</footer>', '', s, flags=re.S)
s = re.sub(r'\n\s*<!-- Right sidebar -->.*?</aside>', '', s, flags=re.S)
s = s.replace('Agnes Video Generator', '夜行事务所')
s = s.replace("{{ t('subtitle') }}", '都市悬疑动画 · 剧本成片工作台')
app.write_text(s)

cf = root / 'components/forms/CreativeForm.vue'
s = cf.read_text()
s = re.sub(r'\n\s*<div class="flex items-center gap-2 mb-4 text-xs text-muted">.*?</div>\n\n\s*<div class="glass-card', '\n    <div class="glass-card', s, count=1, flags=re.S)
s = s.replace("{{ t('creativeSettings') }}", '剧本与分镜')
s = s.replace("{{ t('taskName') }}", '剧集名称')
s = s.replace("{{ t('taskNamePlaceholder') }}", '例如：夜行事务所 EP01《凌晨三点的死者》')
s = s.replace("{{ t('ideaLabel') }} (idea)", '剧本')
s = s.replace(":placeholder=\"t('ideaPlaceholder')\"", ":placeholder=\"'在这里粘贴《夜行事务所》剧本……\\n\\n建议格式：场景 / 时间 / 人物 / 动作 / 对白。\\n系统会根据剧本生成分镜、视频、角色配音和字幕。'\"")
s = s.replace('rows="4"', 'rows="14"')
cf.write_text(s)
