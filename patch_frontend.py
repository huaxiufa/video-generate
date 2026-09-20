from pathlib import Path
import re

root = Path('/opt/agnes-base/frontend/src')
app = root / 'App.vue'
s = app.read_text()

# Remove original support/project navigation, resource links, footer and quick-entry sidebars.
patterns = [
    (r'\n\s*<!-- Left sidebar -->.*?\n\s*<!-- Main content -->', '\n    <!-- Main content -->'),
    (r'\n\s*<!-- Resource links（窄屏可换行） -->.*?</nav>', ''),
    (r'\n\s*<!-- Footer -->.*?</footer>', ''),
    (r'\n\s*<!-- Right sidebar -->.*?</aside>', ''),
]
for pattern, replacement in patterns:
    s = re.sub(pattern, replacement, s, flags=re.S)

# Remove common promotional/link blocks even when upstream markup changes slightly.
s = re.sub(r'\n\s*<(?:nav|footer|aside)[^>]*>.*?(?:支持项目|快速入口|给个 Star|更多资源|在线体验|Prompt 技巧|API 文档|模型概览).*?</(?:nav|footer|aside)>', '', s, flags=re.S)

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

# Simplify CreativeForm advanced settings: keep only aspect ratio.
cf_text = cf.read_text()
cf_text = cf_text.replace("resolution: '768x1152'", "resolution: '1152x768'")
adv_start = cf_text.index("    <!-- Advanced Config -->")
adv_end = cf_text.index("    <!-- Audio & Subtitle -->")
simple_advanced = """    <!-- Video Format -->
    <div class="glass-card rounded-2xl p-6 mb-4">
      <h2 class="text-lg font-semibold text-accent mb-4">画面比例</h2>
      <div>
        <label class="block text-sm text-muted mb-1.5">视频画面比例</label>
        <select v-model="form.resolution" class="w-full glass-input rounded-lg px-3 py-2.5 text-sm text-ink">
          <option value="1152x768">横屏 16:9</option>
          <option value="768x1152">竖屏 9:16</option>
          <option value="1024x1024">方形 1:1</option>
        </select>
        <p class="text-xs text-muted mt-2">角色参考图、场景图、尾帧和视频串联方式由系统自动处理。</p>
      </div>
    </div>

"""
cf_text = cf_text[:adv_start] + simple_advanced + cf_text[adv_end:]
cf.write_text(cf_text)

static_index = Path('/opt/agnes-base/static/index.html')
if static_index.exists():
    html = static_index.read_text()
    html = html.replace('<head>', '<head>\n<meta name="night-agency-ui" content="night-agency-ui-v3">')
    static_index.write_text(html)

# Replace the original audio configuration with Night Agency's own voice workflow.
sub = root / 'components/shared/SubtitleConfig.vue'
ss = sub.read_text()
ss = ss.replace("import VoiceSelector from './VoiceSelector.vue'\n", "")
audio_start = ss.index("  <!-- Audio Config -->")
audio_end = ss.index("  <!-- Subtitle Config -->")
night_audio = """  <!-- Night Agency Voice Config -->
  <div class="glass-card rounded-2xl p-6 mb-4">
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-lg font-semibold text-accent">夜行事务所语音</h2>
        <p class="text-xs text-muted mt-1">角色首次对白由 Gemini 建立声音，之后自动使用该角色的声音克隆。</p>
      </div>
      <span class="text-xs text-muted">Gemini → MOSS</span>
    </div>
    <div class="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
      <div class="rounded-xl bg-paper-2/30 border border-rule/50 p-4">
        <p class="text-sm font-medium text-ink-2">角色声音</p>
        <p class="text-xs text-muted mt-1">系统会根据剧本人物自动匹配 Gemini 音色，无需使用原项目音色选择器。</p>
      </div>
      <div class="rounded-xl bg-paper-2/30 border border-rule/50 p-4">
        <p class="text-sm font-medium text-ink-2">声音记忆</p>
        <p class="text-xs text-muted mt-1">第一次生成保存角色声音母版；后续对白直接克隆，不重复调用 Gemini。</p>
      </div>
    </div>
    <div class="mt-4 flex items-center gap-3">
      <label class="flex items-center gap-2 text-sm text-ink-2 cursor-pointer">
        <input v-model="audioEnabled" type="checkbox" class="rounded bg-paper-2 border-rule" />
        <span>启用角色配音</span>
      </label>
      <label class="text-sm text-muted">基础语速</label>
      <select v-model="rate" class="glass-input rounded-lg px-3 py-2 text-sm text-ink">
        <option value="-30%">0.8×</option>
        <option value="-15%">0.9×</option>
        <option value="+0%">1.0×</option>
        <option value="+15%">1.1×</option>
        <option value="+30%">1.2×</option>
      </select>
    </div>
  </div>

"""
ss = ss[:audio_start] + night_audio + ss[audio_end:]
sub.write_text(ss)

# Build a cache-busting marker into the generated page.
static_index = Path('/opt/agnes-base/static/index.html')
if static_index.exists():
    html = static_index.read_text()
    html = html.replace('night-agency-ui-v3', 'night-agency-ui-v4')
    static_index.write_text(html)
