"""Durable original-group/original-requester notifications after confirmed delivery.

No model calls or private-message copies. The external recovery sender writes the
same jobs.state='sent', so its successful retries are picked up as well.
"""
import hashlib
import json
from image_delivery import ImageDelivery


class Completions:
    def __init__(self, ledger):
        self.ledger=ledger
        self.delivery=ImageDelivery(ledger)
        with ledger.transaction() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS media_completions (
                job TEXT PRIMARY KEY, session TEXT NOT NULL, owner TEXT NOT NULL,
                group_id TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0, updated REAL NOT NULL)''')

    def remember(self, message, kind, operation):
        if kind!='image' or operation not in ('generate','edit'):return
        info=message.get('message_info') or {}
        owner=str((info.get('user_info') or {}).get('user_id') or '')
        group=str((info.get('group_info') or {}).get('group_id') or '')
        session=str(message.get('session_id') or '')
        mid=str(message.get('message_id') or '')
        if message.get('platform')!='qq' or not owner.isdigit() or (group and not group.isdigit()) or not session or not mid:return
        jid=hashlib.sha256(f'{session}\0{mid}\0{kind}'.encode()).hexdigest()[:32]
        with self.ledger.transaction() as db:
            db.execute('INSERT OR IGNORE INTO media_completions(job,session,owner,group_id,updated) VALUES(?,?,?,?,?)',
                       (jid,session,owner,group,self.ledger.clock()))

    def due(self):
        now=self.ledger.clock()
        with self.ledger.transaction() as db:
            return [dict(row) for row in db.execute('''SELECT c.* FROM media_completions c
                JOIN jobs j ON j.id=c.job AND j.session=c.session
                WHERE j.state='sent' AND c.state!='sent' AND c.attempts<1
                  AND c.updated<? AND j.updated>? ORDER BY c.updated LIMIT 10''',(now-5,now-86400))]

    def claim(self,jid):
        now=self.ledger.clock()
        with self.ledger.transaction() as db:
            row=db.execute('SELECT * FROM media_completions WHERE job=?',(jid,)).fetchone()
            if not row or row['state']=='sent' or row['attempts']>=1 or row['updated']>now-5:return False
            if row['state']=='sending' and row['updated']>now-60:return False
            db.execute("UPDATE media_completions SET state='sending',attempts=attempts+1,updated=? WHERE job=?",(now,jid))
            return True

    def finish(self,jid,sent):
        with self.ledger.transaction() as db:
            db.execute('UPDATE media_completions SET state=?,updated=? WHERE job=?',('sent' if sent else 'pending',self.ledger.clock(),jid))

    async def flush_pending(self, sender):
        delivery = self.delivery
        now = self.ledger.clock()
        with self.ledger.transaction() as db:
            rows = [dict(r) for r in db.execute("""SELECT j.id,j.session,d.status FROM jobs j
                JOIN image_deliveries d ON d.job=j.id
                JOIN media_completions c ON c.job=j.id
                WHERE j.kind='image' AND j.state!='sent' AND d.status!='sent'
                  AND d.first_queued<=? AND d.first_queued>? LIMIT 20""", (now-60,now-86400))]
        for row in rows:
            if not delivery.claim_notice(row["id"], "delivery_failed"):
                continue
            text = ("图片已保存，但这次未能完成交付；可以稍后要求重发，不会重新画或再扣次数。"
                    if row["status"] == "paused" else
                    "图片已经画好并保存，QQ 的发送结果还未确认。本鱼会先核对记录，确认未发出再补发，不会重新画或再扣次数。")
            try:
                await sender([{'type':'text','data':text}],row["session"],return_details=True)
            except Exception:
                pass  # At most one notice attempt across restarts.

    async def flush(self,sender):
        for job in self.due():
            if not self.claim(job['job']):continue
            record = self.delivery.record(job["job"]) or {}
            is_file = record.get("channel") == "file"
            group_text = " 画好啦，图片已作为文件发在这个群里啦！" if is_file else " 画好啦，图片已经发在这个群里啦！"
            private_text = "画好啦，图片已作为文件发给你啦！" if is_file else "画好啦，图片已经发给你啦！"
            segments = ([{'type':'at','data':{'target_user_id':job['owner']}},
                         {'type':'text','data':group_text}] if job['group_id'] else
                        [{'type':'text','data':private_text}])
            try:
                result=await sender(segments,job['session'],return_details=True)
                sent=result.get('sent') is True if isinstance(result,dict) else result is True
            except Exception:sent=False
            self.finish(job['job'],sent)
