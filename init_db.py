from app import app
from database import mysql

def initialize_database():
    with app.app_context():
        cur = mysql.connection.cursor()
        
        print("Creating tables...")
        
        # We drop existing tables to ensure a clean schema creation
        cur.execute("DROP TABLE IF EXISTS activity_log;")
        cur.execute("DROP TABLE IF EXISTS notes;")
        cur.execute("DROP TABLE IF EXISTS user_tasks;")
        cur.execute("DROP TABLE IF EXISTS users;")
        
        # Users Table
        cur.execute("""
            CREATE TABLE users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(100) NOT NULL,
                email VARCHAR(120) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                full_name VARCHAR(100) DEFAULT NULL,
                phone VARCHAR(20) DEFAULT NULL,
                dob DATE DEFAULT NULL,
                gender VARCHAR(20) DEFAULT NULL,
                profile_pic VARCHAR(255) DEFAULT 'default_profile.png',
                theme VARCHAR(20) DEFAULT 'dark',
                notifications_enabled TINYINT(1) DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Tasks Table
        cur.execute("""
            CREATE TABLE user_tasks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                task_name VARCHAR(255) NOT NULL,
                due_date DATE NOT NULL,
                status VARCHAR(50) DEFAULT 'Pending',
                priority VARCHAR(50) DEFAULT 'Medium',
                category VARCHAR(100) DEFAULT 'General',
                description TEXT DEFAULT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        # Notes Table
        cur.execute("""
            CREATE TABLE notes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        # Activity Log Table
        cur.execute("""
            CREATE TABLE activity_log (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                activity VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        mysql.connection.commit()
        cur.close()
        print("Database schema successfully created!")

if __name__ == "__main__":
    initialize_database()
