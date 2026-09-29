"""Durable parent experiments, separate from removable queue history."""
import json


class ResearchExperimentRepository:
    def __init__(self,database):
        self.database=database
        with database.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS research_experiments (
                experiment_group TEXT PRIMARY KEY, document TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')

    def get(self,group):
        with self.database.connect() as db:
            row=db.execute('SELECT document FROM research_experiments WHERE experiment_group=?',(group,)).fetchone()
        return json.loads(row['document']) if row else None

    def save(self,document):
        with self.database.connect() as db:
            db.execute('''INSERT INTO research_experiments(experiment_group,document) VALUES(?,?)
                       ON CONFLICT(experiment_group) DO UPDATE SET document=excluded.document,updated_at=CURRENT_TIMESTAMP''',
                       (document['experiment_group'],json.dumps(document,default=str)))

    def list(self):
        with self.database.connect() as db:
            rows=db.execute('SELECT document FROM research_experiments ORDER BY updated_at DESC LIMIT 100').fetchall()
        return [json.loads(row['document']) for row in rows]
