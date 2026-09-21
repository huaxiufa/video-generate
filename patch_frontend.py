from pathlib import Path
import re

root = Path('/opt/agnes-base/frontend/src')
app = root / 'App.vue'
s = app.read_text()

# Remove upstream author UI blocks by their stable Vue comments.
def _remove_between(text, start_marker, end_marker):
    a = text.find(start_marker)
    if a < 0:
        return text
    b = text.find(end_marker, a)
    if b < 0:
        return text
    return text[:a] + text[b:]

s = _remove_between(s, '<!-- Left sidebar -->', '<!-- Main content -->')
s = _remove_between(s, '<!-- Resource links（窄屏可换行） -->', '<!-- Config Panel -->')
s = _remove_between(s, '<!-- Footer -->', '<!-- Right sidebar -->')
s = _remove_between(s, '<!-- Right sidebar -->', '<!-- Voice Picker Modal -->')

# Fallback for upstream wording changes.
s = re.sub(
    r'\\n\\s*<(?:nav|footer|aside)[^>]*>.*?(?:支持项目|快速入口|给个 Star|更多资源|在线体验|Prompt 技巧|API 文档|模型概览|Demo|Guides|FAQ|GitHub).*?</(?:nav|footer|aside)>',
    '',
    s,
    flags=re.S,
)

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
    html = html.replace('<head>', '<head>\n<meta name="night-agency-ui" content="night-agency-ui-v5">')
    static_index.write_text(html)

# Final exact cleanup after all App.vue edits.
app_after = app.read_text()
app_after = _remove_between(app_after, '<!-- Left sidebar -->', '<!-- Main content -->')
app_after = _remove_between(app_after, '<!-- Resource links（窄屏可换行） -->', '<!-- Config Panel -->')
app_after = _remove_between(app_after, '<!-- Footer -->', '<!-- Right sidebar -->')
app_after = _remove_between(app_after, '<!-- Right sidebar -->', '<!-- Voice Picker Modal -->')
app.write_text(app_after)

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

# Make failed-task recovery explicit: this is a checkpoint resume, not a full regeneration.
progress = root / 'components/ProgressPage.vue'
if progress.exists():
    ps = progress.read_text()
    ps = ps.replace("{{ t('fbRetryHint') }}", "已有场景、参考图、尾帧和已提交的 Agnes 视频任务会保留；点击继续生成时从失败位置恢复，不会从头重做。")
    ps = ps.replace("↻ {{ t('fbRetryBtn') }}", "↻ 继续生成（从断点恢复）")
    ps = ps.replace(
        '''        <!-- 任务信息（用户输入提示词 + 各项配置，v6.1） -->''',
        '''        <!-- Night Agency checkpoint resume status -->
        <div v-if="taskInfo && taskInfo.scenes && taskInfo.scenes.length" class="glass-card rounded-2xl p-4 mb-4">
          <div class="flex items-center justify-between mb-3">
            <span class="text-sm font-medium text-ink-2">场景断点</span>
            <span class="text-xs text-muted">已生成的不重复生成</span>
          </div>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
            <div v-for="(scene, idx) in taskInfo.scenes" :key="idx"
                 class="rounded-lg border border-rule/50 bg-paper-2/20 px-3 py-2">
              <div class="text-xs text-muted">Scene {{ Number(idx) + 1 }}</div>
              <div class="text-xs mt-1"
                   :class="scene.video_file ? 'text-green-400' : scene.video_id ? 'text-amber-400' : 'text-muted'">
                {{ scene.video_file ? '✓ 已完成' : scene.video_id ? '⏳ 已提交，恢复时继续轮询' : '○ 待生成' }}
              </div>
            </div>
          </div>
        </div>

        <!-- 任务信息（用户输入提示词 + 各项配置，v6.1） -->'''
    )
    progress.write_text(ps)

# Build a cache-busting marker into the generated page.
static_index = Path('/opt/agnes-base/static/index.html')
if static_index.exists():
    html = static_index.read_text()
    html = html.replace('night-agency-ui-v3', 'night-agency-ui-v5')
    static_index.write_text(html)

# --- Night Agency Agnes 503/keyframe retry patch ---
# The upstream lcy client retries 5xx only five times. For Agnes keyframe
# generation we keep the selected model and wait longer for transient queue
# saturation instead of failing the whole scene too early.
video_api = Path('/opt/agnes-base/core/api/agnes_video.py')
if video_api.exists():
    vs = video_api.read_text()
    old = """        max_rotations = len(ring) * self.max_retries
        while attempt < self.max_retries:
"""
    new = """        max_rotations = len(ring) * self.max_retries
        # Night Agency: keyframe submissions can spend longer in transient
        # Agnes queue saturation. Keep the normal retry budget for other modes.
        max_attempts = self.max_retries
        if mode_desc.startswith("keyframe"):
            try:
                max_attempts = max(
                    max_attempts,
                    int(os.getenv("AGNES_VIDEO_KEYFRAME_MAX_RETRIES", "10")),
                )
            except (TypeError, ValueError):
                max_attempts = max(self.max_retries, 10)
        while attempt < max_attempts:
"""
    if old in vs:
        vs = vs.replace(old, new, 1)

    vs = vs.replace(
        'logger.info(f"[AgnesVideo] Submitting {mode_desc} (attempt {attempt + 1}/{self.max_retries})...")',
        'logger.info(f"[AgnesVideo] Submitting {mode_desc} (attempt {attempt + 1}/{max_attempts})...")',
        1,
    )

    old_503 = """                if resp.status_code >= 500:
                    delay = self.retry_base_delay * (attempt + 1)
                    logger.warning(
                        f"[AgnesVideo] {resp.status_code} server error on {mode_desc}, "
                        f"retry {attempt + 1}/{self.max_retries} in {delay:.0f}s..."
                    )
"""
    new_503 = """                if resp.status_code >= 500:
                    try:
                        max_503_delay = float(
                            os.getenv("AGNES_VIDEO_503_MAX_DELAY", "180")
                        )
                    except (TypeError, ValueError):
                        max_503_delay = 180.0
                    delay = min(
                        self.retry_base_delay * (attempt + 1),
                        max_503_delay,
                    )
                    body_hint = (resp.text or "").replace("\\n", " ").replace("\\r", " ")[:300]
                    logger.warning(
                        f"[AgnesVideo] {resp.status_code} server error on {mode_desc}, "
                        f"retry {attempt + 1}/{max_attempts} in {delay:.0f}s; "
                        f"response={body_hint}"
                    )
"""
    if old_503 in vs:
        vs = vs.replace(old_503, new_503, 1)

    vs = vs.replace(
        'f"{mode_desc}: max retries ({self.max_retries}) exceeded"',
        'f"{mode_desc}: max retries ({max_attempts}) exceeded"',
        1,
    )
    vs = vs.replace(
        'retry_count=self.max_retries,\n            extra={"mode": mode_desc},',
        'retry_count=max_attempts,\n            extra={"mode": mode_desc},',
        1,
    )
    vs = vs.replace(
        'f"[AgnesVideo] {mode_desc}: max retries ({self.max_retries}) exceeded"',
        'f"[AgnesVideo] {mode_desc}: max retries ({max_attempts}) exceeded"',
        1,
    )
    # Make the 2.5 request explicit about a single output.
    needle = '''            "aspect_ratio": aspect_ratio,
        }
'''
    repl = '''            "aspect_ratio": aspect_ratio,
            "n": 1,
        }
'''
    if needle in vs and '"n": 1' not in vs[vs.index('async def _submit_video_v25'):vs.index('async def wait_for_video')]:
        vs = vs.replace(needle, repl, 1)
    video_api.write_text(vs)


# --- Night Agency final upstream-author purge ---

# --- Night Agency final upstream-author purge ---
# Do this as the LAST frontend transform so no later edit can reintroduce
# the original author's navigation, promotion, footer, sidebar or branding.
def _strip_html_section(text, start_re, end_re):
    return re.sub(start_re + r".*?" + end_re, "", text, flags=re.S)

app = root / 'App.vue'
app_text = app.read_text()

# Exact upstream sections (also works if comments/spacing change slightly).
app_text = re.sub(r'\s*<!--\s*Left sidebar\s*-->.*?(?=<!--\s*Main content\s*-->)', '\n', app_text, flags=re.S)
app_text = re.sub(r'\s*<!--\s*Resource links[^>]*-->.*?(?=<!--\s*Config Panel\s*-->)', '\n', app_text, flags=re.S)
app_text = re.sub(r'\s*<!--\s*Footer\s*-->.*?(?=<!--\s*Right sidebar\s*-->)', '\n', app_text, flags=re.S)
app_text = re.sub(r'\s*<!--\s*Right sidebar\s*-->.*?(?=<!--\s*Voice Picker Modal\s*-->)', '\n', app_text, flags=re.S)

# Fallback: remove any remaining author-owned navigation/footer/sidebars.
app_text = re.sub(
    r'\s*<(?:nav|footer|aside)\b[^>]*>.*?(?:lichuanyang\.top|lcy362|支持项目|快速入口|更多资源|给个 Star|Demo|Guides|FAQ|GitHub).*?</(?:nav|footer|aside)>',
    '\n',
    app_text,
    flags=re.S | re.I,
)

# Remove original branding wherever it survived.
app_text = app_text.replace('Agnes Video Generator', '夜行事务所')
app_text = app_text.replace('AI 视频，一键生成', '都市悬疑动画 · 剧本成片工作台')
app_text = app_text.replace('{{ t(\'subtitle\') }}', '都市悬疑动画 · 剧本成片工作台')
app.write_text(app_text)

# ConfigPanel contains several original-site promotional links and the
# upstream GA/privacy panel. Keep the useful Agnes key/model/workspace controls,
# but remove the original author's site promotion and analytics UI.
cfg = root / 'components/ConfigPanel.vue'
if cfg.exists():
    c = cfg.read_text()
    c = re.sub(
        r'\s*<div class="flex flex-wrap items-center gap-x-5 gap-y-1\.5 mt-3 text-xs">\s*'
        r'<a href="https://platform\.agnes-ai\.com".*?</div>',
        '\n',
        c,
        flags=re.S,
    )
    # Remove the entire upstream privacy/GA panel by its stable section comment.
    c = re.sub(
        r'\s*<!--\s*隐私设置（3\.4：GA4 配置开关）\s*-->.*?(?=</template>)',
        '\n',
        c,
        flags=re.S,
    )
    # Catch any remaining original-site links inside this panel.
    c = re.sub(
        r'\s*<a\b[^>]*href="https://(?:video\.lichuanyang\.top|github\.com/lcy362)[^"]*"[^>]*>.*?</a>',
        '',
        c,
        flags=re.S | re.I,
    )
    cfg.write_text(c)

# Also remove original external-link labels that can be rendered by any
# remaining footer/nav fragment in the compiled source.
for p in root.rglob('*.vue'):
    try:
        t = p.read_text()
    except Exception:
        continue
    if 'video.lichuanyang.top' in t or 'github.com/lcy362/agnes-video-generator' in t:
        t = re.sub(
            r'\s*<a\b[^>]*(?:video\.lichuanyang\.top|github\.com/lcy362/agnes-video-generator)[^>]*>.*?</a>',
            '',
            t,
            flags=re.S | re.I,
        )
        p.write_text(t)

# Runtime safety net: hide any upstream sidebar/footer that survives a future
# upstream template change.
css = Path('/opt/agnes-base/static/night-agency-cleanup.css')
css.write_text("""
/* Night Agency: no upstream author promotion/branding */
.sidebar-card,
footer:has(a[href*="lichuanyang.top"]),
footer:has(a[href*="github.com/lcy362"]),
nav:has(a[href*="lichuanyang.top"]),
nav:has(a[href*="github.com/lcy362"]),
aside:has(a[href*="lichuanyang.top"]),
aside:has(a[href*="github.com/lcy362"]) {
  display: none !important;
}
""")
