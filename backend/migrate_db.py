import sqlite3
import os

# Path to your database file - dynamically resolved from environment
db_url = os.getenv("DATABASE_URL", "sqlite:///./data/ze_dashboard.db")
if db_url.startswith("sqlite:///"):
    DB_PATH = db_url.replace("sqlite:///", "")
else:
    DB_PATH = "data/ze_dashboard.db"

def migrate():
    print(f"Connecting to database at {DB_PATH}...")
    
    if not os.path.exists(DB_PATH):
        print(f"Error: Database file not found at {DB_PATH}")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if column exists
        cursor.execute("PRAGMA table_info(contract)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if "is_protected" in columns:
            print("Column 'is_protected' already exists. No action needed.")
        else:
            print("Adding column 'is_protected'...")
            # Add column with default value 0 (False)
            cursor.execute("ALTER TABLE contract ADD COLUMN is_protected BOOLEAN DEFAULT 0")
            print("Migration successful: Added 'is_protected' column.")
            
        if "annual_value" in columns:
            print("Column 'annual_value' already exists. No action needed.")
        else:
            print("Adding column 'annual_value'...")
            cursor.execute("ALTER TABLE contract ADD COLUMN annual_value FLOAT")
            print("Migration successful: Added 'annual_value' column.")
            
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"Migration failed: {e}")

if __name__ == "__main__":
    migrate()
