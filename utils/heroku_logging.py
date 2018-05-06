import os
from datetime import datetime
import psycopg2

class DBLogger:
    def __init__(self, db_url):
        self.db_url = db_url
        self.conn = None

    def get_connection(self):
        if self.conn is None or self.conn.closed:
            try:
                self.conn = psycopg2.connect(self.db_url)
                cur = self.conn.cursor()
                cur.execute("CREATE TABLE IF NOT EXISTS dialog(chat_id varchar, user_name varchar, query varchar, response varchar, actualtime timestamp)")
                self.conn.commit()
            except Exception:
                self.conn = None
        return self.conn

    def log_message(self, message, response=None):
        conn = self.get_connection()
        if conn is not None:
            cur = conn.cursor()
            query = "INSERT INTO dialog VALUES('{}', '{}', '{}', '{}', TIMESTAMP '{}')".format(
                message.chat.id, 
                message.chat.username, 
                message.text, 
                response, 
                datetime.now()
            )
            cur.execute(query)
            conn.commit()
