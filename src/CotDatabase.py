import os
import sqlite3

from datetime import datetime

class CotDatabase:
    """Class to manage COT data"""
    def __init__(self, db_name='data/cot_data.db'):
        self.db_name = db_name

        # Ensure directories exist
        os.makedirs(os.path.dirname(self.db_name), exist_ok=True)

        self.setup_database()

    def setup_database(self):
        """Create the database and the necessary table if it doesn't exist."""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS zip_files (
                year INTEGER PRIMARY KEY,
                last_modified TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def update_zip_file(self, year, last_modified):
        """Update the last modified date of the zip file in the database."""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        c.execute('''
            INSERT INTO zip_files (year, last_modified) VALUES (?, ?)
            ON CONFLICT(year) DO UPDATE SET last_modified = ?
        ''', (year, last_modified, last_modified))
        conn.commit()
        conn.close()

    def get_zipfile_last_modified_time(self, year):
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        c.execute('SELECT last_modified FROM zip_files WHERE year = ?', (year,))
        row = c.fetchone()
        conn.close()

        result = None
        if row:
            try:
                result = datetime.strptime(row[0], '%a, %d %b %Y %H:%M:%S %Z')
            except Exception as e:
                try:
                    print(row[0])
                    result = datetime.strptime(row[0], '%Y %H:%M:%S %Z')
                    print(f"2nd time worked {result}")
                except Exception as e:
                    print(f"Exception in date format {result}. {e}")
                    return None
                print(f"Exception in date format {result}. {e}")
                return None
        return result

    def latest_update_timestamp(self):
        # TODO retrieve this year based on current time
        year = "2025"
        result = self.get_zipfile_last_modified_time(year)
        if result is None:
            result = "Unknown"
        return result
