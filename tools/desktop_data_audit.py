"""Capture/check real data during desktop acceptance; remove only our test row."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from storage import TaskStore

TEST_NAME="桌面应用验收临时任务·关闭重开检查"
AUDIT=ROOT/'acceptance'/'desktop-data-baseline.json'

def rows():
    with closing(sqlite3.connect(ROOT/'tasks.db')) as c:
        return [list(r) for r in c.execute('SELECT id,position,name,done,due_date,uid,version FROM tasks ORDER BY position')]

if sys.argv[1]=='capture':
    AUDIT.write_text(json.dumps(rows(),ensure_ascii=False,indent=2),encoding='utf-8')
    print('Captured original desktop acceptance data')
elif sys.argv[1]=='clean-check':
    before=json.loads(AUDIT.read_text(encoding='utf-8'))
    store=TaskStore(ROOT/'tasks.db',ROOT/'tasks.json')
    tasks,_=store.snapshot()
    old_uids={r[5] for r in before}
    for task in tasks:
        if task.name==TEST_NAME and task.uid not in old_uids:
            store.apply('desktop-acceptance-cleanup-'+task.uid,'delete',task.uid,task.version)
    after=rows()
    assert before==after,'Live task data changed; preserve it and inspect instead of restoring blindly'
    print('Original data exactly preserved; own desktop test task cleaned')
    print('Total:',len(after),'Done:',sum(r[3] for r in after))
