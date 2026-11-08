"""Durable global quotas and media lifecycle. No network or SDK dependency."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import io
import os
from pathlib import Path
import re
import sqlite3
import time
import wave

from image_delivery import ImageDelivery

LIMITS = {"image": (10, 20), "audio": (20, 40), "video": (2, 4)}
BJT = timezone(timedelta(hours=8))


class MediaError(Exception):
    """Only fixed, safe messages should cross the tool boundary."""


class GenerationError(MediaError):
    def __init__(self, message="生成失败", *, retryable=False, uncertain=False):
        super().__init__(message)
        self.retryable = retryable
        self.uncertain = uncertain


def beijing_day(now=None):
    return datetime.fromtimestamp(time.time() if now is None else now, BJT).date().isoformat()


def explicit_request(text, kind, operation):
    """Conservative lexical gate over host-fetched text, never model-supplied evidence."""
    text = text.strip()
    if not text or re.search(r"不要|别(?:给我)?(?:画|生成|发|读|说)|不用|无需|不需要|禁止|取消|do not|don't", text, re.I):
        return False
    if operation == "quota":
        return bool(re.search(r"额度|配额|剩余|次数|quota|limit", text, re.I))
    if operation == "resend":
        return bool(re.search(r"重发|再发|重新发送|resend", text, re.I))
    if re.search(r"(?:举例|示例|原理|功能介绍|如果|假如|他说|她说)|(?:怎么|如何).*(?:画|生成|合成|朗读|语音)|(?:会|支持).*(?:画|生成|语音).*[吗？?]$", text):
        return False
    if kind == "image":
        from media_intent import image_intent
        return image_intent(text) == "generate"
    return bool(re.search(r"语音(?:读|说|回复|回答|念|播报)|(?:发|生成|合成|来|用).{0,12}语音|朗读|念(?:一下|一遍|出来)|读(?:一下|一遍|出来)|/vertex_tts\b|text.to.speech|read\s+aloud", text, re.I)) and not bool(re.search(r"(?:怎么|如何).*(?:语音|朗读)|语音.*(?:原理|支持吗)", text))


def wav_audio(data: bytes, mime: str):
    """Return a validated WAV and actual duration; reject >60s without truncation."""
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        output = data
    elif mime.split(";", 1)[0].lower() in {"audio/l16", "audio/pcm"}:
        params = dict(re.findall(r"(rate|channels)\s*=\s*(\d+)", mime))
        rate, channels = int(params.get("rate", 24000)), int(params.get("channels", 1))
        if rate not in {16000, 22050, 24000, 44100, 48000} or channels not in {1, 2} or len(data) % (2 * channels):
            raise MediaError("音频格式无效")
        out = io.BytesIO()
        with wave.open(out, "wb") as w:
            w.setnchannels(channels)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(data)
        output = out.getvalue()
    else:
        raise MediaError("仅接受可校验时长的 WAV 或 PCM 音频")
    try:
        with wave.open(io.BytesIO(output), "rb") as w:
            frames, rate = w.getnframes(), w.getframerate()
            duration = frames / rate
            if w.getcomptype() != "NONE" or len(w.readframes(frames)) != frames * w.getnchannels() * w.getsampwidth():
                raise MediaError("音频数据不完整")
    except (wave.Error, EOFError, ZeroDivisionError) as exc:
        raise MediaError("音频格式无效") from exc
    if not 0 < duration <= 60:
        raise MediaError("实际语音时长超过60秒或音频为空，未发送；请缩短文本后提出新请求")
    return output, duration


def image_data(data: bytes):
    from PIL import Image
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
        with Image.open(io.BytesIO(data)) as im:
            if im.width * im.height > 4_500_000 or min(im.size) < 128:
                raise MediaError("返回图片尺寸异常")
            im.thumbnail((1024, 1024))
            out = io.BytesIO()
            im.convert("RGB").save(out, "PNG")
            return out.getvalue()
    except MediaError:
        raise
    except Exception as exc:
        raise MediaError("返回图片无效") from exc


class Ledger:
    def __init__(self, root, clock=time.time):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "quota.sqlite3"
        self.clock = clock
        with self.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                  id TEXT PRIMARY KEY, session TEXT NOT NULL, message TEXT NOT NULL,
                  kind TEXT NOT NULL, day TEXT NOT NULL, state TEXT NOT NULL,
                  attempts INTEGER NOT NULL DEFAULT 0, asset TEXT NOT NULL DEFAULT '',
                  updated REAL NOT NULL, error TEXT NOT NULL DEFAULT '',
                  UNIQUE(session,message,kind));
                CREATE TABLE IF NOT EXISTS attempts (
                  job TEXT NOT NULL, day TEXT NOT NULL, kind TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS attempts_day ON attempts(day,kind);
                CREATE TABLE IF NOT EXISTS seeds (
                  seed_id TEXT PRIMARY KEY, day TEXT NOT NULL, kind TEXT NOT NULL,
                  successes INTEGER NOT NULL, attempts INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS audio_claims (
                  token TEXT PRIMARY KEY, day TEXT NOT NULL, state TEXT NOT NULL,
                  updated REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS audio_claims_day ON audio_claims(day, state);
            """)

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA busy_timeout=15000")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _usage(self, db, day, kind):
        used, held = db.execute("""SELECT
          coalesce(sum(state IN ('ready','sent','delivery_failed')),0),
          coalesce(sum(state IN ('reserved','generating','uncertain')),0)
          FROM jobs WHERE day=? AND kind=?""", (day, kind)).fetchone()
        seeds = db.execute("SELECT coalesce(sum(successes),0), coalesce(sum(attempts),0) FROM seeds WHERE day=? AND kind=?", (day, kind)).fetchone()
        attempts = db.execute("SELECT count(*) FROM attempts WHERE day=? AND kind=?", (day, kind)).fetchone()[0]
        claim_used = claim_held = 0
        if kind == "audio":
            claim_used, claim_held = db.execute("""SELECT
              coalesce(sum(state='used'),0), coalesce(sum(state='pending'),0)
              FROM audio_claims WHERE day=?""", (day,)).fetchone()
        return {"used": used + seeds[0] + claim_used, "reserved": held + claim_held,
                "attempts": attempts + seeds[1],
                "limit": LIMITS[kind][0], "attempt_limit": LIMITS[kind][1], "enabled": kind != "video"}

    def quota(self):
        with self.transaction() as db:
            day = beijing_day(self.clock())
            return {"day": day, "timezone": "Asia/Shanghai", **{k: self._usage(db, day, k) for k in LIMITS}}

    def seed_usage(self, seed_id, day, kind, successes, attempts):
        """Offline administrative import, idempotent by seed_id; no public Tool."""
        if kind not in LIMITS or type(successes) is not int or type(attempts) is not int or not 0 <= successes <= attempts:
            raise MediaError("导入额度参数无效")
        if not seed_id or datetime.strptime(day, "%Y-%m-%d").date().isoformat() != day:
            raise MediaError("导入标识或日期无效")
        values = (seed_id, day, kind, successes, attempts)
        with self.transaction() as db:
            existing = db.execute("SELECT * FROM seeds WHERE seed_id=?", (seed_id,)).fetchone()
            if existing:
                if tuple(existing) != values:
                    raise MediaError("相同导入标识的内容不一致")
                return False
            usage = self._usage(db, day, kind)
            if usage["used"] + usage["reserved"] + successes > LIMITS[kind][0] or usage["attempts"] + attempts > LIMITS[kind][1]:
                raise MediaError("导入将超过当日上限，请核对已有记录")
            db.execute("INSERT INTO seeds VALUES (?,?,?,?,?)", values)
            return True

    def reserve(self, session, message, kind):
        if kind not in {"image", "audio"}:
            raise MediaError("本期未启用视频")
        job_id = hashlib.sha256(f"{session}\0{message}\0{kind}".encode()).hexdigest()[:32]
        with self.transaction() as db:
            old = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if old:
                return dict(old), False
            day = beijing_day(self.clock())
            usage = self._usage(db, day, kind)
            if usage["used"] + usage["reserved"] >= usage["limit"] or usage["attempts"] >= usage["attempt_limit"]:
                raise MediaError("今日全局额度或尝试次数已用完")
            db.execute("INSERT INTO jobs(id,session,message,kind,day,state,updated) VALUES (?,?,?,?,?,'reserved',?)",
                       (job_id, session, message, kind, day, self.clock()))
            return dict(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()), True

    def start_attempt(self, job_id):
        with self.transaction() as db:
            job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            day = beijing_day(self.clock())
            if job["state"] not in {"reserved", "generating"} or job["attempts"] >= 2:
                raise MediaError("任务不可再次生成")
            if self._usage(db, day, job["kind"])["attempts"] >= LIMITS[job["kind"]][1]:
                raise MediaError("今日全局尝试次数已用完")
            db.execute("INSERT INTO attempts VALUES (?,?,?)", (job_id, day, job["kind"]))
            db.execute("UPDATE jobs SET state='generating',attempts=attempts+1,updated=? WHERE id=?", (self.clock(), job_id))

    def finish(self, job_id, state, *, asset="", error=""):
        with self.transaction() as db:
            db.execute("UPDATE jobs SET state=?,asset=CASE WHEN ?='' THEN asset ELSE ? END,error=?,updated=? WHERE id=?",
                       (state, asset, asset, error, self.clock(), job_id))

    def get(self, job_id, session):
        with self.transaction() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=? AND session=?", (job_id, session)).fetchone()
            return dict(row) if row else None

    def latest(self, session, kind):
        with self.transaction() as db:
            row = db.execute("SELECT * FROM jobs WHERE session=? AND kind=? AND asset!='' AND state IN ('ready','sent','delivery_failed') ORDER BY updated DESC LIMIT 1", (session, kind)).fetchone()
            return dict(row) if row else None

    def claim_shared_audio(self, token):
        """Hold one shared daily voice slot for Unified TTS. Pending claims reserve capacity."""
        token = str(token or "").strip()
        if not token or len(token) > 240:
            raise MediaError("语音额度标识无效")
        with self.transaction() as db:
            now = self.clock()
            db.execute("DELETE FROM audio_claims WHERE state='pending' AND updated < ?", (now - 180,))
            row = db.execute("SELECT state FROM audio_claims WHERE token=?", (token,)).fetchone()
            if row and row["state"] == "used":
                return {"ok": False, "duplicate": True}
            if row and row["state"] == "pending":
                return {"ok": False, "pending": True, "duplicate": False}
            day = beijing_day(now)
            usage = self._usage(db, day, "audio")
            if usage["used"] + usage["reserved"] >= usage["limit"] or usage["attempts"] >= usage["attempt_limit"]:
                raise MediaError("今天的语音额度已经用完了，所有群和私聊每天一共20条，明天再试。")
            db.execute("INSERT INTO audio_claims(token, day, state, updated) VALUES (?,?, 'pending', ?)", (token, day, now))
            db.execute("INSERT INTO attempts VALUES (?,?,?)", (token, day, "audio"))
            return {"ok": True, "duplicate": False}

    def settle_shared_audio(self, token, sent):
        """Keep a successful send in the daily total; release the slot when nothing was delivered."""
        token = str(token or "").strip()
        if not token:
            return
        with self.transaction() as db:
            if sent:
                db.execute("UPDATE audio_claims SET state='used', updated=? WHERE token=? AND state='pending'", (self.clock(), token))
            else:
                db.execute("DELETE FROM audio_claims WHERE token=? AND state='pending'", (token,))


class MediaService:
    def __init__(self, ledger, backend, sender, notifier=None):
        self.ledger, self.backend, self.sender = ledger, backend, sender
        self.notifier = notifier
        self.active = set()
        self.sending = set()
        self.image_delivery = ImageDelivery(ledger)

    def asset_path(self, job):
        return self.ledger.root / (job["id"] + (".png" if job["kind"] == "image" else ".wav"))

    async def notify(self, kind, session, event, *, job_id=''):
        if kind == 'image' and job_id and not self.image_delivery.claim_notice(job_id, event):
            return
        if self.notifier is not None:
            try:
                await self.notifier(kind, session, event)
            except Exception:
                pass

    async def _deliver_saved_image(self, job, *, explicit_resend=False):
        with self.image_delivery.lock(job['id']) as acquired:
            if not acquired:
                return {'success': False, 'job_id': job['id'], 'generated': True, 'content': '图片正在发送，请勿重复提交'}
            record = self.image_delivery.record(job['id'])
            if record and record['status'] in ('pending', 'sending') and record['attempts']:
                return {'success': False, 'generated': True, 'job_id': job['id'],
                        'delivery_status': 'awaiting_confirmation', 'notification_owner': 'media_plugin',
                        'content': '已保存，正在核对发送记录；不立即重发，不再生成。插件负责通知，不要重复发等待说明。'}
            self.image_delivery.enqueue(job, explicit_resend=explicit_resend)
            if not self.image_delivery.begin(job['id']):
                current = self.ledger.get(job['id'], job['session'])
                return {'success': current['state'] == 'sent', 'generated': True, 'job_id': job['id'], 'content': '已处理；成品已保存，不会重新生成'}
            try:
                result = await self.sender('image', self.asset_path(job), job['session'])
                sent = result.get('sent') is True and bool(result.get('message_id')) if isinstance(result, dict) else result is True
                receipt = result.get('message_id', '') if isinstance(result, dict) else ''
            except Exception:
                sent, receipt = False, ''
            self.image_delivery.finish(job['id'], sent, receipt=receipt)
            # The durable poller owns the delayed (60s) exception notice.
            return {'success': sent, 'generated': True, 'job_id': job['id'],
                    'delivery_status': 'confirmed' if sent else 'awaiting_confirmation',
                    'notification_owner': 'media_plugin',
                    'content': '插件负责完成提醒，不要另发重复说明。' + ('图片发送已确认。' if sent else
                               '成品已保存，发送回执未确认，后台将先核对记录；这不等于断线或生成失败，不要承诺已经送达。')}

    async def deliver(self, job, *, explicit_resend=False):
        if job['kind'] == 'image':
            return await self._deliver_saved_image(job, explicit_resend=explicit_resend)
        if job["id"] in self.sending:
            return {"success": False, "job_id": job["id"], "content": "正在发送，请勿重复提交"}
        self.sending.add(job["id"])
        try:
            path = self.asset_path(job)
            try:
                sent = await self.sender(job["kind"], path, job["session"])
            except Exception:
                sent = False
            self.ledger.finish(job["id"], "sent" if sent else "delivery_failed")
            if not sent:
                await self.notify(job['kind'], job['session'], 'delivery_failed')
            return {"success": bool(sent), "generated": True, "job_id": job["id"], "content": "已发送" if sent else "生成成功，发送失败或回执不明；资产已保留，请查看会话后要求重发，不要重新生成"}
        finally:
            self.sending.discard(job["id"])

    async def run(self, kind, session, message, text, *, operation="generate", reference=None, job_id=""):
        if operation == "quota":
            return {"success": True, "quota": self.ledger.quota()}
        if operation == "resend":
            job = self.ledger.get(job_id, session) if job_id else self.ledger.latest(session, kind)
            if not job or job["kind"] != kind or job["state"] not in {"ready", "sent", "delivery_failed"}:
                raise MediaError("当前会话没有可重发的成品")
            return await self.deliver(job, explicit_resend=True)
        if operation not in {"generate", "edit"} or (operation == "edit" and (kind != "image" or not reference)):
            raise MediaError("操作无效或缺少原图")
        if not isinstance(text, str) or not text.strip() or len(text) > (300 if kind == "audio" else 2000):
            raise MediaError("文本为空或过长（图片2000字，语音300字）")
        job, fresh = self.ledger.reserve(session, message, kind)
        if not fresh:
            if job["id"] in self.active:
                return {"success": True, "job_id": job["id"], "content": "当前请求正在生成，不要重复提交"}
            if job["state"] in {"ready", "sent", "delivery_failed"}:
                return {"success": job["state"] == "sent", "generated": True, "job_id": job["id"], "content": "请求已处理；若未收到，请明确要求重发"}
            # Crash after fsync but before DB commit: recover the finished asset only.
            path = self.asset_path(job)
            if path.exists() and job["state"] in {"generating", "uncertain"}:
                data = path.read_bytes()
                image_data(data) if kind == "image" else wav_audio(data, "audio/wav")
                self.ledger.finish(job["id"], "ready", asset=path.name)
                return {"success": False, "generated": True, "job_id": job["id"], "content": "已恢复成品，请明确要求重发"}
            return {"success": False, "job_id": job["id"], "content": "请求已处理或结果不明，禁止自动重新生成；新请求须由用户另发消息明确提出"}
        self.active.add(job["id"])
        try:
            await self.notify(kind, session, 'start', job_id=job['id'])
            for attempt in range(2):
                try:
                    self.ledger.start_attempt(job["id"])
                    data, mime = await self.backend.generate(kind, text, reference=reference)
                    if len(data) > 25 * 1024 * 1024:
                        raise MediaError("返回资产过大")
                    data = image_data(data) if kind == "image" else wav_audio(data, mime)[0]
                    path = self.asset_path(job)
                    staging = path.with_suffix(".part")
                    with staging.open("wb") as f:
                        f.write(data)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(staging, path)
                    self.ledger.finish(job["id"], "ready", asset=path.name)
                    break
                except GenerationError as exc:
                    if exc.uncertain:
                        self.ledger.finish(job["id"], "uncertain", error=str(exc))
                        raise
                    if exc.retryable and attempt == 0:
                        await asyncio.sleep(0.5)
                        continue
                    self.ledger.finish(job["id"], "failed", error=str(exc))
                    raise
                except MediaError:
                    self.ledger.finish(job["id"], "failed", error="生成或资产校验失败")
                    raise
            return await self.deliver(job)
        except asyncio.CancelledError:
            self.ledger.finish(job["id"], "uncertain", error="执行被中断，禁止自动重试")
            raise
        except MediaError:
            await self.notify(kind, session, 'generation_failed', job_id=job['id'])
            raise
        except Exception as exc:
            # Never print upstream exceptions: they may include auth headers/URLs.
            self.ledger.finish(job["id"], "uncertain", error="内部错误，结果不明")
            await self.notify(kind, session, 'generation_failed', job_id=job['id'])
            raise MediaError("内部错误，结果不明；禁止自动重新生成") from None
        finally:
            self.active.discard(job["id"])
