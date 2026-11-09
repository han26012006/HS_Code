"""Source-cited local FTS. Search relevance never proves legal applicability."""
from pathlib import Path
import hashlib,json,re,sqlite3,unicodedata

def fold(s):return ''.join(c for c in unicodedata.normalize('NFD',str(s))if unicodedata.category(c)!='Mn').replace('đ','d').replace('Đ','D').lower()
def build_index(root):
 root=Path(root);tmp=root/'knowledge.building.sqlite';tmp.unlink(missing_ok=True);c=sqlite3.connect(tmp);c.executescript('CREATE VIRTUAL TABLE chunks USING fts5(id UNINDEXED,document_sha256 UNINDEXED,source_name UNINDEXED,unit UNINDEXED,unit_kind UNINDEXED,sheet UNINDEXED,roles UNINDEXED,text,folded);CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);')
 with(root/'knowledge_chunks.jsonl').open()as f:
  for line in f:
   r=json.loads(line);c.execute('INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?,?)',(r['id'],r['document_sha256'],r.get('source_name',''),r['unit'],r.get('unit_kind','page'),r.get('sheet'),json.dumps(r['roles']),r['text'],fold(r['text'])))
 h=hashlib.sha256((root/'knowledge_chunks.jsonl').read_bytes()).hexdigest();c.execute('INSERT INTO metadata VALUES(?,?)',('chunks_sha256',h));c.commit();n=c.execute('SELECT COUNT(*) FROM chunks').fetchone()[0];c.close();tmp.replace(root/'knowledge.sqlite');return {'indexed_chunks':n,'chunks_sha256':h,'verified_legal_applicability':False}
class ProjectKnowledge:
 def __init__(self,root):
  self.db=Path(root)/'knowledge.sqlite'
  if not self.db.is_file():raise ValueError('Build knowledge.sqlite before enabling project knowledge')
 def search(self,q,limit=12):
  tokens=list(dict.fromkeys(re.findall(r'\w+',fold(q))))[:20]
  if not tokens:return []
  query=' OR '.join('"'+t+'"'for t in tokens)
  with sqlite3.connect(self.db.resolve().as_uri()+'?mode=ro',uri=True)as c:
   c.row_factory=sqlite3.Row;rows=c.execute('SELECT id,document_sha256,source_name,unit,unit_kind,sheet,roles,text,bm25(chunks) retrieval_score FROM chunks WHERE chunks MATCH ? ORDER BY retrieval_score LIMIT ?',(query,max(1,min(int(limit),30)))).fetchall()
  return [dict(dict(r),roles=json.loads(r['roles']),source_applicability='requires_human_review',score_is_probability=False)for r in rows]
