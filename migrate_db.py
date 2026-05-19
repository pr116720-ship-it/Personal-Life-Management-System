from app import app
from database import mysql

def migrate():
    with app.app_context():
        cur = mysql.connection.cursor()
        print("Starting database migration...")
        
        # 1. Add missing columns to users table
        columns_to_add = [
            ("full_name", "VARCHAR(100) DEFAULT NULL"),
            ("phone", "VARCHAR(20) DEFAULT NULL"),
            ("dob", "DATE DEFAULT NULL"),
            ("gender", "VARCHAR(20) DEFAULT NULL"),
            ("profile_pic", "VARCHAR(255) DEFAULT 'default_profile.png'"),
            ("theme", "VARCHAR(20) DEFAULT 'dark'"),
            ("notifications_enabled", "TINYINT(1) DEFAULT 1"),
            ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        ]
        
        # Fetch existing columns in users table
        cur.execute("DESCRIBE users")
        existing_cols = [row[0] for row in cur.fetchall()]
        
        for col_name, col_def in columns_to_add:
            if col_name not in existing_cols:
                print(f"Adding column '{col_name}' to 'users' table...")
                cur.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}")
            else:
                print(f"Column '{col_name}' already exists.")
                
        # 2. Create activity_log table if it doesn't exist
        print("Creating 'activity_log' table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                activity VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        
        mysql.connection.commit()
        cur.close()
        print("Migration completed successfully!")

if __name__ == "__main__":
    migrate()
