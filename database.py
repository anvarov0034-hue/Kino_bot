import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL')
        # Connection Pool yaratish (Tezlik uchun eng muhim qism)
        # Min: 1, Max: 10 ta ulanish ochib qo'yadi
        try:
            self.pool = psycopg2.pool.SimpleConnectionPool(
                1, 20,
                self.database_url
            )
            if self.pool:
                logger.info("Connection Pool created successfully")
            self.init_db()
        except Exception as e:
            logger.error(f"Database connection error: {e}")

    def get_connection(self):
        """Pool dan ulanish olish"""
        return self.pool.getconn()

    def return_connection(self, conn):
        """Ulanishni Pool ga qaytarish"""
        if conn:
            self.pool.putconn(conn)

    def init_db(self):
        """Jadvallarni yaratish va yangilash"""
        conn = self.get_connection()
        try:
            cur = conn.cursor()

            # Movies jadvali (caption ustuni qo'shildi)
            cur.execute('''
                CREATE TABLE IF NOT EXISTS movies (
                    id SERIAL PRIMARY KEY,
                    movie_code VARCHAR(50) UNIQUE NOT NULL,
                    video_id VARCHAR(255) NOT NULL,
                    video_name VARCHAR(500),
                    caption TEXT,
                    views INTEGER DEFAULT 0,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Agar eski baza bo'lsa va caption ustuni yo'q bo'lsa, uni qo'shamiz
            try:
                cur.execute("ALTER TABLE movies ADD COLUMN IF NOT EXISTS caption TEXT")
            except Exception as e:
                logger.warning(f"Column update warning: {e}")

            # Users jadvali
            cur.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_blocked BOOLEAN DEFAULT FALSE
                )
            ''')

            # Channels jadvali
            cur.execute('''
                CREATE TABLE IF NOT EXISTS channels (
                    id SERIAL PRIMARY KEY,
                    channel_id BIGINT UNIQUE,
                    channel_username VARCHAR(255),
                    required BOOLEAN DEFAULT TRUE,
                    is_active BOOLEAN DEFAULT TRUE
                )
            ''')

            conn.commit()
            cur.close()
        except Exception as e:
            logger.error(f"Init DB error: {e}")
            conn.rollback()
        finally:
            self.return_connection(conn)

    # ===== MOVIES OPERATIONS =====

    def add_movie(self, movie_code, video_id, video_name, caption=None):
        """Kino qo'shish (caption bilan)"""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                '''INSERT INTO movies (movie_code, video_id, video_name, caption)
                   VALUES (%s, %s, %s, %s)''',
                (movie_code, video_id, video_name, caption)
            )
            conn.commit()
            cur.close()
            return True
        except psycopg2.IntegrityError:
            conn.rollback()
            return False
        except Exception as e:
            logger.error(f"Add movie error: {e}")
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)

    def delete_movie(self, movie_code):
        """Kino kodini bo'yicha o'chirish"""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            # Avval bor yoki yo'qligini tekshirmaymiz, to'g'ridan-to'g'ri o'chiramiz
            cur.execute('DELETE FROM movies WHERE movie_code = %s', (movie_code,))
            conn.commit()

            # Nechta qator o'chganini bilish (agar 0 bo'lsa, demak kino topilmagan)
            deleted_count = cur.rowcount
            cur.close()
            return deleted_count > 0
        except Exception as e:
            logger.error(f"Delete movie error: {e}")
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)


    def get_movie_by_code(self, movie_code):
        """Kod bo'yicha kinoni olish"""
        conn = self.get_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('SELECT * FROM movies WHERE movie_code = %s', (movie_code,))
            movie = cur.fetchone()
            cur.close()
            return movie
        except Exception as e:
            logger.error(f"Get movie error: {e}")
            return None
        finally:
            self.return_connection(conn)

    def search_movie_by_name(self, name):
        """Nom bo'yicha qidirish"""
        conn = self.get_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(
                'SELECT * FROM movies WHERE video_name ILIKE %s LIMIT 10',
                (f'%{name}%',)
            )
            movies = cur.fetchall()
            cur.close()
            return movies
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []
        finally:
            self.return_connection(conn)

    def increment_views(self, movie_code):
        """Ko'rishlar sonini oshirish"""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute('UPDATE movies SET views = views + 1 WHERE movie_code = %s', (movie_code,))
            conn.commit()
            cur.close()
        except Exception:
            conn.rollback()
        finally:
            self.return_connection(conn)

    def get_all_movies(self, limit=50):
        """Kinolar ro'yxati"""
        conn = self.get_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            # Raqam bo'yicha to'g'ri tartiblash (Kodesiz, shunchaki id yoki added_at)
            cur.execute('SELECT * FROM movies ORDER BY id DESC LIMIT %s', (limit,))
            movies = cur.fetchall()
            cur.close()
            return movies
        except Exception as e:
            logger.error(f"All movies error: {e}")
            return []
        finally:
            self.return_connection(conn)

    def get_movies_count(self):
        """Jami kinolar soni"""
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute('SELECT COUNT(*) FROM movies')
            count = cur.fetchone()[0]
            cur.close()
            return count
        except Exception:
            return 0
        finally:
            self.return_connection(conn)
    def get_last_code(self):
            """Bazadagi eng katta raqamli kodni topish"""
            conn = self.get_connection()
            try:
                cur = conn.cursor()
                # Kodlarni raqamga aylantirib, eng kattasini olamiz
                cur.execute("SELECT MAX(CAST(movie_code AS INTEGER)) FROM movies")
                max_val = cur.fetchone()[0]
                cur.close()
                return max_val if max_val is not None else 0
            except Exception:
                return 0
            finally:
                self.return_connection(conn)
    # ===== USERS OPERATIONS =====

    def add_user(self, user_id):
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                'INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING',
                (user_id,)
            )
            conn.commit()
            cur.close()
        except Exception:
            conn.rollback()
        finally:
            self.return_connection(conn)

    def update_user_activity(self, user_id):
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                'UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = %s',
                (user_id,)
            )
            conn.commit()
            cur.close()
        except Exception:
            conn.rollback()
        finally:
            self.return_connection(conn)

    def get_users_count(self):
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute('SELECT COUNT(*) FROM users')
            count = cur.fetchone()[0]
            cur.close()
            return count
        except Exception:
            return 0
        finally:
            self.return_connection(conn)

    def get_active_users_today(self):
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM users WHERE last_active::date = CURRENT_DATE")
            count = cur.fetchone()[0]
            cur.close()
            return count
        except Exception:
            return 0
        finally:
            self.return_connection(conn)

    # ===== CHANNELS OPERATIONS =====

    def add_channel(self, channel_id, channel_username, required=True):
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                'INSERT INTO channels (channel_id, channel_username, required, is_active) VALUES (%s, %s, %s, TRUE)',
                (channel_id, channel_username, required)
            )
            conn.commit()
            cur.close()
            return True
        except psycopg2.IntegrityError:
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)

    def get_required_channels(self):
        conn = self.get_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('SELECT * FROM channels WHERE required = TRUE AND is_active = TRUE')
            channels = cur.fetchall()
            cur.close()
            return channels
        except Exception:
            return []
        finally:
            self.return_connection(conn)

    def delete_channel(self, channel_id):
        conn = self.get_connection()
        try:
            cur = conn.cursor()
            cur.execute('DELETE FROM channels WHERE channel_id = %s', (channel_id,))
            conn.commit()
            affected = cur.rowcount
            cur.close()
            return affected > 0
        except Exception:
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)

    def get_all_channels(self):
        conn = self.get_connection()
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute('SELECT * FROM channels ORDER BY id')
            channels = cur.fetchall()
            cur.close()
            return channels
        except Exception:
            return []
        finally:
            self.return_connection(conn)
