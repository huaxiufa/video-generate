from pathlib import Path
import re

BASE = Path("/opt/agnes-base")

p = BASE / "core/pipelines/creative/steps_video.py"
s = p.read_text()
start = s.find("    async def _generate_keyframe_scenes(")
if start >= 0:
    new_fn = '''    async def _generate_keyframe_scenes(
        self, scenes: list, reference_image: str, end_frame_prompts: list,
        pregenerated_end_frames: dict, vw: int, vh: int, end_frame_images: list,
    ) -> list:
        """Sequential keyframe generation with durable per-scene checkpoints."""
        current_first_frame = reference_image
        total = len(scenes)
        all_video_paths: List[str] = []

        for scene_idx, scene_text in enumerate(scenes):
            if self._is_shutdown():
                raise PipelineShutdown(f"interrupted during keyframe scene {scene_idx}")

            user_ref = self._user_scene_ref(scene_idx)
            if user_ref:
                logger.info(f"[Pipeline] Scene {scene_idx}: using user reference image as first frame")
                current_first_frame = user_ref

            scene_dir = os.path.join(self.working_dir, f"scene_{scene_idx}")
            os.makedirs(scene_dir, exist_ok=True)
            video_path = os.path.join(scene_dir, "video.mp4")
            end_frame_path = os.path.join(scene_dir, "end_frame.png")

            # Completed scene: never regenerate.
            if os.path.exists(video_path):
                all_video_paths.append(video_path)
                if os.path.exists(end_frame_path):
                    current_first_frame = end_frame_path
                await self._emit("video_gen", "running",
                    f"场景 {scene_idx+1}/{total}: 已缓存，跳过生成",
                    _PROGRESS_CACHED_START + _PROGRESS_CACHED_SPAN * (scene_idx + 1) / total)
                continue

            # End frame is a checkpoint too.
            if not os.path.exists(end_frame_path):
                if str(scene_idx) in pregenerated_end_frames:
                    end_frame_path = pregenerated_end_frames[str(scene_idx)]
                else:
                    user_ef = (
                        end_frame_images[scene_idx]
                        if end_frame_images and scene_idx < len(end_frame_images) and end_frame_images[scene_idx]
                        else None
                    )
                    if user_ef and os.path.exists(user_ef):
                        await _run_ffmpeg_async([
                            "ffmpeg", "-y", "-i", user_ef,
                            "-vf", f"scale={vw}:{vh}:force_original_aspect_ratio=decrease,pad={vw}:{vh}:(ow-iw)/2:(oh-ih)/2",
                            end_frame_path,
                        ], timeout=30)
                    else:
                        end_frame_prompt = (
                            end_frame_prompts[scene_idx]
                            if scene_idx < len(end_frame_prompts)
                            else _fallback_end_frame(scene_text)
                        )
                        use_i2i = self._state.generate_end_frames_from_ref and reference_image
                        if use_i2i:
                            if self._state.character_appearance and not self._state.reference_image:
                                tags = _localize_preserve_tags(scene_text)
                                end_frame_prompt = (
                                    f"{tags['preserve']}{chr(10)}{self._state.character_appearance}{chr(10)}"
                                    f"{tags['keep_identity']}{chr(10)}{chr(10)}{tags['change']}{chr(10)}{end_frame_prompt}"
                                )
                            normalized_ref = await self._get_normalized_character_ref(reference_image)
                            img_output = await self.image_generator.generate_single_image(
                                prompt=end_frame_prompt, reference_image_paths=[normalized_ref],
                                size=f"{vw}x{vh}")
                        else:
                            img_output = await self.image_generator.generate_single_image(
                                prompt=end_frame_prompt, size=f"{vw}x{vh}")
                        await img_output.save(end_frame_path)

            first_frame_url = await self.video_generator._resolve_image_ref(current_first_frame)
            end_frame_url = await self.video_generator._resolve_image_ref(end_frame_path)

            # Existing video_id means POST already happened. Resume polling only.
            existing_video_id = self._load_scene_task(scene_dir)
            if existing_video_id:
                video_id = existing_video_id
                logger.info(f"[Pipeline] Scene {scene_idx}: resuming existing video task {video_id[:16]}...")
                await self._emit("video_gen", "running",
                    f"场景 {scene_idx+1}/{total}: 续传已提交任务...",
                    _PROGRESS_KEYFRAME_WAIT_START)
            else:
                await self._emit("video_gen", "running",
                    f"场景 {scene_idx+1}/{total}: 提交任务 (keyframe)...",
                    _PROGRESS_KEYFRAME_SUBMIT_START)
                video_id = await self.video_generator.submit_video(
                    prompt=scene_text,
                    reference_image_paths=[first_frame_url, end_frame_url],
                    duration=self._scene_duration(scene_idx),
                    width=vw, height=vh)
                # Persist immediately after successful POST.
                self._save_scene_task(scene_dir, video_id)

            try:
                await self._emit("video_gen", "running",
                    f"场景 {scene_idx+1}/{total}: 等待生成中...",
                    _PROGRESS_KEYFRAME_WAIT_START)
                video_output = await self.video_generator.wait_for_video(video_id)
                await video_output.save(video_path)
            except Exception as e:
                logger.error(f"Scene {scene_idx} video failed: {e}")
                if is_remote_video_failure(e):
                    task_file = os.path.join(scene_dir, "task.json")
                    if os.path.exists(task_file):
                        os.remove(task_file)
                raise

            all_video_paths.append(video_path)
            if scene_idx + 1 < total and os.path.exists(end_frame_path):
                current_first_frame = end_frame_path

            await self._emit("video_gen", "running",
                f"场景 {scene_idx+1}/{total}: 完成",
                _PROGRESS_KEYFRAME_WAIT_START + _PROGRESS_KEYFRAME_WAIT_SPAN * (scene_idx + 1) / total)

        return all_video_paths
'''
    s = s[:start] + new_fn + "\\n"
    p.write_text(s)

# Ensure 2.5 requests explicitly ask for one output.
v = BASE / "core/api/agnes_video.py"
vs = v.read_text()
needle = '"aspect_ratio": aspect_ratio,\\n        }'
if needle in vs:
    vs = vs.replace(needle, '"aspect_ratio": aspect_ratio,\\n            "n": 1,\\n        }', 1)
v.write_text(vs)
