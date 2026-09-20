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
# Allow long episodic scripts. The backend guard is patched below to 50k.
backend_route = Path('/opt/agnes-base/web/routes/task_creation_routes.py')
if backend_route.exists():
    br = backend_route.read_text()
    br = br.replace('if len(idea) > 10000:', 'if len(idea) > 50000:')
    br = br.replace('idea 最多 10000 字符', 'idea 最多 50000 字符')
    backend_route.write_text(br)

# Make the creative script box import .txt/.md files directly into the textarea.

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

# Add a local script-file loader without introducing a new backend upload protocol.
cf_text = cf_text.replace(
    "function onRefImageChange(e: Event) {",
    """async function onScriptFileChange(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  const text = await file.text()
  form.idea = text
}

function onRefImageChange(e: Event) {"""
)
cf_text = cf_text.replace(
    '''      <div class="mb-4">
        <label class="block text-sm text-muted mb-1.5">{{ t('ideaLabel') }} (idea) <span class="text-red-400">*</span></label>''',
    '''      <div class="mb-4">
        <div class="flex items-center justify-between mb-1.5">
          <label class="block text-sm text-muted">剧本 <span class="text-red-400">*</span></label>
          <label class="cursor-pointer text-xs text-accent hover:underline">
            导入 TXT / MD
            <input type="file" accept=".txt,.md,text/plain,text/markdown" class="hidden" @change="onScriptFileChange" />
          </label>
        </div>'''
)
cf_text = cf_text.replace('rows="4"', 'rows="18"')
cf.write_text(cf_text)


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

# Strengthen character consistency: generate a reusable multi-character reference sheet
# instead of describing only the protagonist. The same sheet is then reused by all scenes.
char_file = Path('/opt/agnes-base/core/screenwriter/characters.py')
if char_file.exists():
    cs = char_file.read_text()
    cs = cs.replace(
        "Extract ONLY the main protagonist's physical appearance from this story.",
        "Extract ALL recurring named characters from this story and describe their fixed physical appearance for a reusable character reference sheet."
    )
    cs = cs.replace(
        "仅从此故事中提取主要角色的物理外貌。",
        "从此故事中提取所有反复出现的具名角色，并为每个角色整理固定物理外貌，用于可复用的角色参考设定。"
    )
    cs = cs.replace(
        "Output a CONCISE paragraph describing their fixed look — include EVERY detail:",
        "For EACH recurring named character, output a clearly separated character block with the name and fixed look — include EVERY detail:"
    )
    cs = cs.replace(
        "输出一段简洁的描述，概括其固定外观——包含所有细节：",
        "对每个反复出现的具名角色输出独立的角色块，先写角色姓名，再写固定外观——包含所有细节："
    )
    cs = cs.replace(
        "Write as a single descriptive paragraph, 3-5 sentences.",
        "Write 2-4 sentences per character. Keep each character clearly separated."
    )
    cs = cs.replace(
        "以一段描述性文字输出，3-5句话。",
        "每个角色用2-4句话描述，并明确分隔不同角色。"
    )
    char_file.write_text(cs)

# Build a cache-busting marker into the generated page.
static_index = Path('/opt/agnes-base/static/index.html')
if static_index.exists():
    html = static_index.read_text()
    html = html.replace('night-agency-ui-v3', 'night-agency-ui-v4')
    static_index.write_text(html)
