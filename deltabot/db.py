from sqlite3 import connect, Row
from datetime import datetime, timedelta

class DatabaseManager():
  def __init__(self, filepath):
    self.db = connect(filepath)
    self.db.row_factory = Row
    with self.db as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS awards 
            (submission_id TEXT, submission_title TEXT, submission_self_text TEXT, 
                submission_author TEXT, submission_url TEXT, submission_time ,
             awarded_comment_id TEXT, awarded_comment_text TEXT, awarded_comment_author TEXT, 
                awarded_comment_url TEXT, awarded_comment_time REAL,
             awarding_comment_id TEXT, awarding_comment_text TEXT, awarding_comment_author TEXT, 
                awarding_comment_url TEXT, awarding_comment_time REAL)""")

        conn.execute("""CREATE TABLE IF NOT EXISTS dispo_log
            (comment_id TEXT PRIMARY KEY, dispo INT, reply_id TEXT, comment_time REAL)""")
        

  def award_point(self, awarded_comment, awarding_comment):
    submission = awarded_comment.submission
    with self.db as conn:
      conn.execute("""INSERT INTO awards VALUES
        (
          ?, ?, ?, ?, ?, ?,
          ?, ?, ?, ?, ?,
          ?, ?, ?, ?, ?
        )""", 
        (
          submission.id, submission.title, submission.selftext, 
            submission.author.name, submission.permalink, submission.created_utc,
          awarded_comment.id, awarded_comment.body, awarded_comment.author.name, 
            awarded_comment.permalink, awarded_comment.created_utc,
          awarding_comment.id, awarding_comment.body, awarding_comment.author.name, 
            awarding_comment.permalink, awarding_comment.created_utc
        )
      )

  def previous_awards_in_submission(self, awarded_comment, awarding_comment):
    with self.db:
      cur = self.db.cursor()
      cur.execute('''SELECT awarding_comment_id FROM awards where submission_id = ? 
        and awarding_comment_author = ? and awarded_comment_author = ?''',
        (awarded_comment.submission.id, awarding_comment.author.name, 
         awarded_comment.author.name))
      previous_awards = cur.fetchall()
    return previous_awards

  def already_awarded_by_bot(self, awarding_comment):
    with self.db:
      cur = self.db.cursor()
      cur.execute('SELECT * FROM awards WHERE awarding_comment_id = ?', (awarding_comment.id,))
      rows = cur.fetchall()
    return bool(rows)

  def fetch_awards_by_month(self, year, month):
    next_month = (month + 1) if (month < 12) else 1
    next_year = year if (next_month > 1) else (year + 1)
    with self.db:
      cur = self.db.cursor()
      cur.execute('''SELECT * FROM awards WHERE 
        (awarding_comment_time >= ? 
        AND awarding_comment_time < ?)''', 
        (datetime.timestamp(datetime(year, month, 1, 0, 0, 0)), 
         datetime.timestamp(datetime(next_year, next_month, 1, 0, 0, 0))))
    awards = cur.fetchall()
    return [dict(award) for award in awards]


  def fetch_awards_by_awardee(self, awardee):
      with self.db:
          cur = self.db.cursor()
          cur.execute('''SELECT * FROM awards WHERE 
              awarded_comment_author = ?''', (awardee,))
          awards = cur.fetchall()
      return [dict(award) for award in awards]

  def log_dispo(self, comment, dispo, reply):
    with self.db as conn:
      conn.execute('''INSERT OR REPLACE INTO dispo_log 
        (comment_id, dispo, reply_id, comment_time) 
        VALUES (?, ?, ?, ?)''',
        (comment.id, dispo, reply.id, comment.created_utc))

  def fetch_dispo_log_by_comment(self, comment):
    with self.db:
      cur = self.db.cursor()
      cur.execute('SELECT * FROM dispo_log WHERE comment_id = ?', (comment.id,))
      row = cur.fetchone()
    return dict(row) if row else None

  def fetch_recent_dispo_logs(self, days):
    with self.db:
      cur = self.db.cursor()
      cur.execute('SELECT * FROM dispo_log WHERE comment_time > ?', 
        (datetime.timestamp(datetime.utcnow() - timedelta(days=days)),))
      rows = cur.fetchall()
    return [dict(row) for row in rows]

  def delete_dispo_log(self, comment):
    with self.db as conn:
        conn.execute('DELETE FROM dispo_log WHERE comment_id = ?', (comment.id,))


